import hashlib
from datetime import date
from src.source.data import ROOT
from src.news.model import digest
from .rfm import REFERENCE,CONTRACT,split_customers,row_payload,snapshot_id


def acquire(connection):
    if not connection.execute('SELECT pg_try_advisory_lock(274108) locked').fetchone()['locked']:raise RuntimeError('Another phase 8 model operation is running')
    connection.execute("SET TIME ZONE 'UTC'")


def migrate(connection):
    if not connection.execute("SELECT 1 FROM audit.schema_versions WHERE version='lak-phase7-v1'").fetchone():raise RuntimeError('Phase 7 warehouse is required')
    sql=(ROOT/'sql/phase8/001_mining_registry.sql').read_text();sha=hashlib.sha256(sql.encode()).hexdigest()
    with connection.transaction():
        connection.execute('CREATE TABLE IF NOT EXISTS audit.mining_schema_identity(singleton boolean PRIMARY KEY DEFAULT true CHECK(singleton),ddl_sha256 text NOT NULL)')
        previous=connection.execute('SELECT ddl_sha256 FROM audit.mining_schema_identity WHERE singleton').fetchone()
        if previous and previous['ddl_sha256']!=sha:raise RuntimeError('Mining DDL fingerprint changed; explicit migration required')
        connection.execute(sql,prepare=False)
        connection.execute('INSERT INTO audit.mining_schema_identity VALUES(true,%s) ON CONFLICT(singleton) DO NOTHING',(sha,))


def capture(connection):
    from psycopg.types.json import Jsonb
    with connection.transaction():
        connection.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
        observations=connection.execute('''SELECT count(*) analytical_orders,
          count(*) FILTER(WHERE packed_at IS NULL) missing_packed_time,
          count(*) FILTER(WHERE packed_at>=%s::date) after_reference
          FROM dw.v_sales_analysis''',(REFERENCE,)).fetchone()
        source=connection.execute('''SELECT f.order_id,c.customer_id,f.packed_at,f.goods_amount
          FROM dw.v_sales_analysis f JOIN dw.dim_customer c USING(customer_key)
          WHERE f.packed_at<%s::date ORDER BY f.order_id''',(REFERENCE,)).fetchall()
        source_sha=digest([{'order_id':r['order_id'],'customer_id':r['customer_id'],
                           'packed_at':r['packed_at'].isoformat(timespec='microseconds'),
                           'goods_amount':format(r['goods_amount'],'.2f')} for r in source])
        rows=connection.execute('''SELECT c.customer_key,c.customer_id,(%s::date-max(f.packed_at)::date)::integer AS recency_days,
          count(DISTINCT f.order_id)::integer AS frequency,sum(f.goods_amount) AS monetary,max(f.packed_at) AS last_packed_at
          FROM dw.v_sales_analysis f JOIN dw.dim_customer c USING(customer_key)
          WHERE f.packed_at<%s::date GROUP BY c.customer_key,c.customer_id ORDER BY c.customer_id''',(REFERENCE,REFERENCE)).fetchall()
        rows=split_customers(rows);snapshot=snapshot_id(rows,source_sha)
        dataset_sha=digest([dict(row_payload(r),split=r['split']) for r in rows])
        if sum(r['frequency'] for r in rows)!=len(source) or sum(r['monetary'] for r in rows)!=sum(r['goods_amount'] for r in source):raise RuntimeError('RFM F/M reconciliation failed')
        observations.update(eligible_orders=len(source),eligible_customers=len(rows),eligible_monetary_vnd=format(sum(r['monetary'] for r in rows),'.2f'))
        old=connection.execute('SELECT * FROM ml.feature_snapshots WHERE snapshot_id=%s',(snapshot,)).fetchone()
        if old:
            if old['source_sha256']!=source_sha or old['dataset_sha256']!=dataset_sha:raise RuntimeError('Existing immutable feature snapshot differs')
        else:
            connection.execute('''INSERT INTO ml.feature_snapshots(snapshot_id,feature_type,reference_date,window_start,source_sha256,dataset_sha256,row_count,contract,observations)
              VALUES(%s,'rfm',%s,NULL,%s,%s,%s,%s,%s)''',(snapshot,REFERENCE,source_sha,dataset_sha,len(rows),Jsonb(CONTRACT),Jsonb(observations)))
            values=[(snapshot,r['customer_key'],r['customer_id'],r['recency_days'],r['frequency'],r['monetary'],r['last_packed_at'],r['split'],digest(row_payload(r))) for r in rows]
            with connection.cursor() as cur:
                cur.executemany('INSERT INTO ml.rfm_features VALUES('+','.join(['%s']*9)+')',values)
        stored=connection.execute('SELECT * FROM ml.rfm_features WHERE snapshot_id=%s ORDER BY customer_id',(snapshot,)).fetchall()
        if len(stored)!=len(rows) or any(any(a[k]!=b[k] for k in ['customer_key','customer_id','recency_days','frequency','monetary','last_packed_at','split']) or b['row_sha256']!=digest(row_payload(a)) for a,b in zip(rows,stored)):
            raise RuntimeError('Persisted feature snapshot does not match capture')
        return snapshot,rows,{'source_sha256':source_sha,'dataset_sha256':dataset_sha,'observations':observations}


def register(connection,model_id,snapshot,relative_path,manifest_sha,metadata,rows,profiles,assignments):
    from psycopg.types.json import Jsonb
    keys={r['customer_id']:r['customer_key'] for r in rows}
    with connection.transaction():
        old=connection.execute('SELECT * FROM ml.model_registry WHERE model_id=%s',(model_id,)).fetchone()
        if old:
            if old['snapshot_id']!=snapshot or old['manifest_sha256']!=manifest_sha or old['artifact_relpath']!=relative_path:raise RuntimeError('Immutable model registry differs from artifact manifest')
        else:
            has_active=connection.execute("SELECT 1 FROM ml.model_registry WHERE algorithm='kmeans_rfm' AND active").fetchone()
            connection.execute('INSERT INTO ml.model_registry(model_id,algorithm,snapshot_id,artifact_relpath,manifest_sha256,metadata,status,active) VALUES(%s,\'kmeans_rfm\',%s,%s,%s,%s,\'READY\',%s)',(model_id,snapshot,relative_path,manifest_sha,Jsonb(metadata),not bool(has_active)))
            with connection.cursor() as cur:
                cur.executemany('INSERT INTO ml.customer_segments(model_id,snapshot_id,customer_key,cluster_id,distance,business_segment) VALUES(%s,%s,%s,%s,%s,%s)',[(model_id,snapshot,keys[a['customer_id']],a['cluster_id'],a['distance'],a['business_segment']) for a in assignments])
                cur.executemany('INSERT INTO ml.segment_profiles VALUES(%s,%s,%s,%s,%s)',[(model_id,p['cluster_id'],p['name'],p['customers'],Jsonb(p)) for p in profiles])
