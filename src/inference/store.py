import hashlib
from datetime import date
from src.source.data import ROOT
from src.news.model import digest
from src.mining.verify import verify as verify_rfm
from src.delivery.store import verify as verify_delivery


def migrate(connection):
    sql=(ROOT/'sql/phase10/001_inference.sql').read_text(encoding='utf-8');checksum=hashlib.sha256(sql.encode()).hexdigest()
    with connection.transaction():
        connection.execute('SELECT pg_advisory_xact_lock(274110)')
        connection.execute('CREATE TABLE IF NOT EXISTS audit.inference_schema_identity(singleton boolean PRIMARY KEY DEFAULT true CHECK(singleton),ddl_sha256 text NOT NULL)')
        old=connection.execute('SELECT ddl_sha256 FROM audit.inference_schema_identity WHERE singleton').fetchone()
        if old and old['ddl_sha256']!=checksum:raise RuntimeError('Inference schema fingerprint changed')
        connection.execute(sql,prepare=False)
        connection.execute('INSERT INTO audit.inference_schema_identity VALUES(true,%s) ON CONFLICT(singleton) DO NOTHING',(checksum,))


def enqueue_customers(connection,reference,reason,demo_only=False):
    cfg=connection.execute('SELECT * FROM ml.inference_config WHERE singleton').fetchone()
    if not cfg:raise RuntimeError('Inference configuration missing')
    result=connection.execute('''INSERT INTO ml.inference_jobs(event_key,kind,entity_key,is_demo,model_id,reference_date,payload)
      SELECT %s,'RFM',c.customer_key::text,c.is_demo,%s,%s,'{}'::jsonb FROM dw.dim_customer c
      WHERE c.customer_key<>0 AND (NOT %s OR c.is_demo)
      ON CONFLICT DO NOTHING RETURNING job_id''',(reason,cfg['rfm_model_id'],reference,demo_only)).fetchall()
    return len(result)


def initialize(connection):
    migrate(connection)
    old=connection.execute('SELECT * FROM ml.inference_config WHERE singleton').fetchone()
    if old:rfm=old['rfm_model_id'];delivery=old['delivery_model_id']
    else:
        r=connection.execute("SELECT model_id FROM ml.model_registry WHERE algorithm='kmeans_rfm' AND status='READY' ORDER BY active DESC,created_at DESC LIMIT 1").fetchone()
        d=connection.execute("SELECT model_id FROM ml.model_registry WHERE algorithm='random_forest_delivery' AND status='READY' ORDER BY created_at DESC LIMIT 1").fetchone()
        if not r or not d:raise RuntimeError('Verified Phase 8 and 9 models are required')
        rfm=r['model_id'];delivery=d['model_id']
    rcheck=verify_rfm(connection,rfm);dcheck=verify_delivery(connection,delivery)
    with connection.transaction():
        connection.execute('INSERT INTO ml.inference_config(singleton,rfm_model_id,delivery_model_id,reference_date) VALUES(true,%s,%s,%s) ON CONFLICT(singleton) DO NOTHING',(rfm,delivery,date(2026,1,1)))
        cfg=connection.execute('SELECT * FROM ml.inference_config WHERE singleton').fetchone()
        count=enqueue_customers(connection,cfg['reference_date'],'bootstrap:'+rfm+':'+cfg['reference_date'].isoformat())
        pending=connection.execute('''INSERT INTO ml.inference_jobs(event_key,kind,entity_key,is_demo,model_id,reference_date,payload)
          SELECT %s,'DELIVERY',f.order_id,f.is_demo,%s,%s,
          jsonb_build_object('order_id',f.order_id,'is_deleted',f.is_deleted,'dispatched_at',f.dispatched_at,'received_at',f.received_at,'observed_at',now(),
          'features',jsonb_build_object('quantity',f.quantity,'goods_amount',f.goods_amount,'quantity_band',f.quantity_band,'warehouse_name',f.warehouse_name,
          'vehicle_type',f.vehicle_type,'shipping_method',s.shipping_method_code,'delivery_district',g.district))
          FROM dw.fact_sales f JOIN dw.dim_shipping_method s USING(shipping_method_key)
          JOIN dw.dim_geography g ON g.geography_key=f.delivery_geography_key
          WHERE NOT f.is_deleted AND f.dispatched_at IS NOT NULL AND f.received_at IS NULL ON CONFLICT DO NOTHING RETURNING job_id''',
          ('bootstrap:'+delivery,delivery,cfg['reference_date'])).fetchall()
    return {'config':cfg,'phase8_verified':True,'phase9_verified':True,'rfm_bootstrap_jobs':count,'pending_delivery_jobs':len(pending),
            'rf_test':dcheck['test'],'rf_baseline_test':dcheck['baseline_test'],'rf_improvement_small':True,
            'models_retrained':False,'delivery_history_not_backfilled_as_live':True}


def advance(connection,reference,reason,demo_only=False):
    if not reason.strip():raise ValueError('Reference change requires reason')
    with connection.transaction():
        cfg=connection.execute('SELECT * FROM ml.inference_config WHERE singleton FOR UPDATE').fetchone()
        if reference<cfg['reference_date']:raise ValueError('Reference date cannot move backward')
        if reference>cfg['reference_date'] and not demo_only:
            connection.execute('UPDATE ml.inference_config SET reference_date=%s WHERE singleton',(reference,))
            connection.execute('INSERT INTO ml.rfm_reference_history(reference_date,previous_date,reason) VALUES(%s,%s,%s)',(reference,cfg['reference_date'],reason))
        count=enqueue_customers(connection,reference,'clock:'+reference.isoformat()+':'+reason,demo_only)
    return {'reference_date':reference,'queued_customers':count,'demo_only':demo_only,'models_retrained':False}
