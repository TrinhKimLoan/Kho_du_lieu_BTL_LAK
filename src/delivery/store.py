from datetime import date
from pathlib import Path
import hashlib
import json
import math
import numpy as np
from datetime import datetime
from src.source.data import ROOT
from src.news.model import digest
from src.mining.artifacts import sha
from .features import CONTRACT, construct, identity, matrix
from .artifacts import load
from .train import scores, baseline_predict

SQL='''SELECT f.order_id, f.dispatched_at, f.received_at, f.quantity, f.goods_amount,
 f.quantity_band, f.warehouse_name, f.vehicle_type, s.shipping_method_code AS shipping_method,
 g.district AS delivery_district
 FROM dw.v_sales_analysis f
 JOIN dw.dim_shipping_method s USING(shipping_method_key)
 JOIN dw.dim_geography g ON g.geography_key=f.delivery_geography_key
 ORDER BY f.order_id'''


def acquire(connection):
    if not connection.execute('SELECT pg_try_advisory_lock(274109) AS locked').fetchone()['locked']: raise RuntimeError('Another phase 9 operation is running')
    if not connection.execute("SELECT 1 FROM ml.model_registry WHERE algorithm='kmeans_rfm' AND status='READY'").fetchone(): raise RuntimeError('Phase 8 model registry is required')
    sql=(ROOT/'sql/phase9/001_delivery.sql').read_text(encoding='utf-8');checksum=hashlib.sha256(sql.encode()).hexdigest()
    with connection.transaction():
        connection.execute('CREATE TABLE IF NOT EXISTS audit.delivery_schema_identity(singleton boolean PRIMARY KEY DEFAULT true CHECK(singleton),ddl_sha256 text NOT NULL)')
        old=connection.execute('SELECT ddl_sha256 FROM audit.delivery_schema_identity WHERE singleton').fetchone()
        if old and old['ddl_sha256']!=checksum: raise RuntimeError('Delivery schema fingerprint changed; migration required')
        connection.execute(sql,prepare=False)
        connection.execute('INSERT INTO audit.delivery_schema_identity VALUES(true,%s) ON CONFLICT(singleton) DO NOTHING',(checksum,))


def capture(connection):
    from psycopg.types.json import Jsonb
    with connection.transaction():
        connection.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
        rows,observations=construct(connection.execute(SQL).fetchall());snapshot=identity(rows);dataset_sha=digest(rows)
        old=connection.execute('SELECT * FROM ml.feature_snapshots WHERE snapshot_id=%s',(snapshot,)).fetchone()
        if old:
            if old['dataset_sha256']!=dataset_sha or old['contract']!=CONTRACT or old['row_count']!=len(rows): raise RuntimeError('Immutable snapshot differs')
        else:
            connection.execute('''INSERT INTO ml.feature_snapshots(snapshot_id,feature_type,reference_date,window_start,source_sha256,dataset_sha256,row_count,contract,observations)
                VALUES(%s,'delivery',%s,%s,%s,%s,%s,%s,%s)''',(snapshot,date(2026,1,1),date(2020,1,1),dataset_sha,dataset_sha,len(rows),Jsonb(CONTRACT),Jsonb(observations)))
            with connection.cursor() as cur:
                cur.executemany('INSERT INTO ml.delivery_features VALUES(%s,%s,%s,%s,%s,%s,%s,%s)',
                    [(snapshot,r['order_id'],r['dispatched_at'],r['received_at'],r['split'],r['target_hours'],Jsonb(r['features']),digest(r)) for r in rows])
        stored=read_rows(connection,snapshot)
        if stored!=rows: raise RuntimeError('Stored feature rows differ from warehouse capture')
        return snapshot,rows,observations


def read_rows(connection,snapshot):
    result=[]
    for r in connection.execute('SELECT * FROM ml.delivery_features WHERE snapshot_id=%s ORDER BY dispatched_at,order_id',(snapshot,)).fetchall():
        row={k:r[k] for k in ['order_id','split','target_hours','features']}
        row.update({k:r[k].isoformat(timespec='microseconds') for k in ['dispatched_at','received_at']})
        if r['row_sha256']!=digest(row): raise RuntimeError('Persisted feature row checksum differs')
        result.append(row)
    return result


def register(connection,model_id,snapshot,directory,metadata,report,predictions):
    from psycopg.types.json import Jsonb
    relative='random_forest_delivery/'+model_id;checksum=sha(directory/'manifest.json')
    old=connection.execute('SELECT * FROM ml.model_registry WHERE model_id=%s',(model_id,)).fetchone()
    if old:
        if old['snapshot_id']!=snapshot or old['manifest_sha256']!=checksum or old['artifact_relpath']!=relative: raise RuntimeError('Immutable model registry differs')
        return
    connection.execute("INSERT INTO ml.model_registry(model_id,algorithm,snapshot_id,artifact_relpath,manifest_sha256,metadata,status,active) VALUES(%s,'random_forest_delivery',%s,%s,%s,%s,'READY',false)",(model_id,snapshot,relative,checksum,Jsonb(dict(metadata,evaluation=report))))
    with connection.cursor() as cur:
        cur.executemany('INSERT INTO ml.delivery_predictions(model_id,snapshot_id,order_id,predicted_hours,baseline_hours,actual_hours,error_hours) VALUES(%s,%s,%s,%s,%s,%s,%s)',
            [(model_id,snapshot,p['order_id'],p['predicted_hours'],p['baseline_hours'],p['actual_hours'],p['error_hours']) for p in predictions])


def verify(connection,model_id):
    registry=connection.execute("SELECT * FROM ml.model_registry WHERE model_id=%s AND algorithm='random_forest_delivery' AND status='READY'",(model_id,)).fetchone()
    if not registry: raise RuntimeError('Ready delivery model missing')
    if registry['artifact_relpath']!='random_forest_delivery/'+model_id: raise RuntimeError('Unexpected artifact path')
    directory=ROOT/'data/models'/registry['artifact_relpath']
    if sha(directory/'manifest.json')!=registry['manifest_sha256']: raise RuntimeError('Registry manifest checksum differs')
    manifest,model,report,rows,predictions=load(directory,model_id);snapshot=registry['snapshot_id']
    if registry['metadata'].get('evaluation')!=report: raise RuntimeError('Registry evaluation differs')
    saved=read_rows(connection,snapshot)
    if rows!=saved or identity(saved)!=snapshot or manifest['snapshot_id']!=snapshot: raise RuntimeError('Snapshot identity/rows differ')
    snap=connection.execute('SELECT * FROM ml.feature_snapshots WHERE snapshot_id=%s',(snapshot,)).fetchone()
    if snap['dataset_sha256']!=digest(rows) or snap['row_count']!=len(rows) or snap['contract']!=CONTRACT: raise RuntimeError('Snapshot metadata differs')
    train=[r for r in rows if r['split']=='train']
    expected=np.nanmedian(np.array(matrix(train)[:,:5],dtype=float),axis=0)
    expected=np.nan_to_num(expected,nan=0.0)
    fitted=model['preprocess'].named_transformers_['numeric'].statistics_
    if not np.array_equal(expected,fitted): raise RuntimeError('Preprocessing was not fitted on train only')
    selected=min(range(len(report['candidates'])),key=lambda i:(report['candidates'][i]['validation']['mae_hours'],report['candidates'][i]['validation']['rmse_hours'],i))
    if selected!=report['selected_candidate'] or report['test_used_for_selection'] or report['refit_on_holdout']: raise RuntimeError('Model selection protocol differs')
    for r in rows:
        start=datetime.fromisoformat(r['dispatched_at']);end=datetime.fromisoformat(r['received_at'])
        split='train' if start.year<2024 else 'validation' if start.year==2024 else 'test'
        cutoff=datetime(2024,1,1) if split=='train' else datetime(2025,1,1) if split=='validation' else datetime(2026,1,1)
        if r['split']!=split or not datetime(2020,1,1)<=start<datetime(2026,1,1) or not start<=end<cutoff: raise RuntimeError('Temporal holdout or label availability differs')
        if not math.isclose(r['target_hours'],(end-start).total_seconds()/3600,rel_tol=0,abs_tol=1e-9): raise RuntimeError('Target differs from source timestamps')
    from .train import baseline_fit
    if baseline_fit(train)!=report['baseline']: raise RuntimeError('Baseline was not fitted on train only')
    if not np.array_equal(baseline_predict(report['baseline'],rows),[p['baseline_hours'] for p in predictions]): raise RuntimeError('Baseline predictions differ')
    lookup={p['order_id']:p for p in predictions}
    stored=connection.execute('SELECT * FROM ml.delivery_predictions WHERE model_id=%s',(model_id,)).fetchall()
    if len(stored)!=len(predictions): raise RuntimeError('Prediction count differs')
    for p in stored:
        if p['snapshot_id']!=snapshot or p['order_id'] not in lookup: raise RuntimeError('Prediction identity differs')
        for k in ['actual_hours','predicted_hours','baseline_hours','error_hours']:
            if not math.isclose(p[k],lookup[p['order_id']][k],rel_tol=0,abs_tol=1e-9): raise RuntimeError('Stored prediction differs: '+k)
    test=[p for p in predictions if p['split']=='test'];metrics=scores([p['actual_hours'] for p in test],[p['predicted_hours'] for p in test])
    if any(not math.isclose(metrics[k],report['test'][k],rel_tol=0,abs_tol=1e-9) for k in metrics): raise RuntimeError('Test metrics differ')
    return {'model_id':model_id,'snapshot_id':snapshot,'rows':len(rows),'split_counts':report['split_counts'],'test':report['test'],
            'baseline_test':report['baselines']['test'],'beats_baseline':report['beats_shipping_baseline_test_mae'],
            'artifact_relpath':registry['artifact_relpath'],'checksums_verified':True,'database_predictions_verified':True,'active':registry['active']}
