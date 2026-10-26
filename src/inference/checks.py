import time
import uuid
from datetime import timedelta
from src.cdc.store import pg
from src.source.runtime import connect
from src.source.demo import action
from src.source.data import fingerprint
from .store import advance


def wait(connection,query,params,predicate,seconds=240):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        row=connection.execute(query,params).fetchone()
        if row and predicate(row):return row
        time.sleep(.5)
    raise RuntimeError('Timeout waiting for CDC/inference result')


def status(connection,wait_for_idle=False):
    deadline=time.monotonic()+300
    while True:
        counts={r['state']:r['n'] for r in connection.execute('SELECT state,count(*) AS n FROM ml.inference_jobs GROUP BY state').fetchall()}
        if counts.get('FAILED',0):
            failed=connection.execute("SELECT job_id,safe_error FROM ml.inference_jobs WHERE state='FAILED' ORDER BY job_id LIMIT 1").fetchone()
            raise RuntimeError('Failed inference job: '+str(failed))
        if not wait_for_idle or not counts.get('PENDING',0)+counts.get('RETRY',0):break
        if time.monotonic()>=deadline:raise RuntimeError('Inference queue did not drain')
        time.sleep(1)
    worker=connection.execute("SELECT heartbeat_at>now()-interval '30 seconds' AS fresh,safe_error FROM audit.worker_heartbeats WHERE worker='ml-inference'").fetchone()
    if wait_for_idle and (not worker or not worker['fresh'] or worker['safe_error']):raise RuntimeError('Inference heartbeat not healthy')
    return {'queue':counts,'worker':worker,'model_versions':connection.execute('SELECT rfm_model_id,delivery_model_id,reference_date FROM ml.inference_config WHERE singleton').fetchone()}


def business(connection):
    return fingerprint(connection.execute('SELECT to_jsonb(f) AS state FROM dw.v_sales_analysis f ORDER BY f.order_id').fetchall())


def registry(connection):
    return fingerprint(connection.execute('SELECT model_id,manifest_sha256,created_at FROM ml.model_registry ORDER BY model_id').fetchall())


def seed(connection):
    suffix='ML10_'+uuid.uuid4().hex[:10];order_id='DEMO_'+suffix+'_O'
    before=business(connection);models=registry(connection)
    try:
        with connect() as source:action(source,'insert',suffix)
        fact=wait(connection,'SELECT * FROM dw.fact_sales WHERE order_id=%s',(order_id,),lambda r:r['is_demo'] and not r['is_deleted'])
        pending=connection.execute("SELECT count(*) AS n FROM ml.inference_jobs WHERE entity_key IN (%s,%s) AND state IN ('PENDING','RETRY')",(order_id,str(fact['customer_key']))).fetchone()['n']
        if pending<2:raise RuntimeError('Expected durable jobs while inference worker was stopped')
        return {'suffix':suffix,'order_id':order_id,'customer_key':fact['customer_key'],'pending_jobs_while_worker_stopped':pending,
                'business_sha256':before,'registry_sha256':models}
    except Exception:
        with connect() as source:action(source,'delete',suffix)
        raise



def finish(connection,seed):
    order=seed['order_id'];customer=seed['customer_key']
    cfg=connection.execute('SELECT * FROM ml.inference_config WHERE singleton').fetchone();reference=cfg['reference_date']
    def assignment(ref,condition):
        return wait(connection,'''SELECT h.* FROM ml.rfm_current_assignments c JOIN ml.rfm_assignment_history h USING(job_id)
         WHERE c.customer_key=%s AND c.is_demo AND c.model_id=%s AND c.reference_date=%s''',(customer,cfg['rfm_model_id'],ref),condition)
    initial=wait(connection,'SELECT * FROM ml.live_delivery_predictions WHERE order_id=%s AND is_demo',(order,),lambda r:True)
    if initial['input']['features']['quantity']!=2 or initial['model_id']!=cfg['delivery_model_id']:raise RuntimeError('Initial frozen prediction input differs')
    original=fingerprint(initial)
    first=assignment(reference,lambda r:r['state']=='ASSIGNED' and float(r['input']['monetary'])==200000)
    advance(connection,reference+timedelta(days=1),'demo-preview-'+seed['suffix'],True)
    tomorrow=assignment(reference+timedelta(days=1),lambda r:r['state']=='ASSIGNED')
    if tomorrow['input']['recency_days']!=first['input']['recency_days']+1:raise RuntimeError('RFM reference tick did not increment recency')
    if connection.execute('SELECT reference_date FROM ml.inference_config WHERE singleton').fetchone()['reference_date']!=reference:raise RuntimeError('Demo tick altered business reference')
    with connect() as source:action(source,'update',seed['suffix'])
    changed=assignment(reference,lambda r:r['state']=='ASSIGNED' and float(r['input']['monetary'])==300000)
    outcome=wait(connection,"SELECT * FROM ml.delivery_outcome_history WHERE prediction_id=%s AND state='RECEIVED' ORDER BY job_id DESC LIMIT 1",(initial['prediction_id'],),lambda r:True)
    if outcome['actual_hours']!=27 or abs(outcome['error_hours']-(initial['predicted_hours']-27))>1e-9:raise RuntimeError('Received outcome differs')
    # Assert the DB itself refuses to mutate the original prediction.
    immutable=False
    try:
        with connection.transaction():
            connection.execute('UPDATE ml.live_delivery_predictions SET predicted_hours=predicted_hours+1 WHERE prediction_id=%s',(initial['prediction_id'],))
    except Exception as exc:
        if 'Initial prediction is immutable' not in str(exc):raise
        immutable=True
    if not immutable:raise RuntimeError('DB accepted overwrite of original prediction')
    with connect() as source:action(source,'delete',seed['suffix'])
    deleted=assignment(reference,lambda r:r['state']=='NO_HISTORY')
    wait(connection,"SELECT * FROM ml.delivery_outcome_history WHERE prediction_id=%s AND state='DELETED'",(initial['prediction_id'],),lambda r:True)
    status(connection,True)
    original_after=connection.execute('SELECT * FROM ml.live_delivery_predictions WHERE prediction_id=%s',(initial['prediction_id'],)).fetchone()
    if fingerprint(original_after)!=original:raise RuntimeError('Original delivery prediction changed')
    history_count=connection.execute('SELECT count(*) AS n FROM ml.rfm_assignment_history WHERE customer_key=%s',(customer,)).fetchone()['n']
    outcomes_count=connection.execute('SELECT count(*) AS n FROM ml.delivery_outcome_history WHERE prediction_id=%s',(initial['prediction_id'],)).fetchone()['n']
    connection.execute("UPDATE ml.inference_jobs SET state='PENDING',available_at=now() WHERE is_demo AND entity_key IN (%s,%s) AND state='DONE'",(order,str(customer)))
    status(connection,True)
    if history_count!=connection.execute('SELECT count(*) AS n FROM ml.rfm_assignment_history WHERE customer_key=%s',(customer,)).fetchone()['n'] or outcomes_count!=connection.execute('SELECT count(*) AS n FROM ml.delivery_outcome_history WHERE prediction_id=%s',(initial['prediction_id'],)).fetchone()['n']:raise RuntimeError('Queue replay duplicated ML history')
    if fingerprint(connection.execute('SELECT * FROM ml.live_delivery_predictions WHERE prediction_id=%s',(initial['prediction_id'],)).fetchone())!=original:raise RuntimeError('Replay changed original prediction')
    if business(connection)!=seed['business_sha256'] or registry(connection)!=seed['registry_sha256']:raise RuntimeError('Demo altered business facts or model versions')
    return {'order_id':order,'source_to_ml_insert_update_delete':True,'durable_queue_survived_worker_restart':True,
            'rfm_monetary_before':first['input']['monetary'],'rfm_monetary_after':changed['input']['monetary'],
            'rfm_no_history_after_delete':deleted['state']=='NO_HISTORY','reference_tick_without_new_transaction':True,
            'reference_tick_demo_only':True,'initial_prediction_immutable':True,'actual_hours':outcome['actual_hours'],
            'predicted_hours':initial['predicted_hours'],'queue_replay_idempotent':True,'historical_business_facts_unchanged':True,'no_retraining':True}


def cleanup(connection,seed):
    with connect() as source:action(source,'delete',seed['suffix'])
    wait(connection,'SELECT * FROM dw.fact_sales WHERE order_id=%s',(seed['order_id'],),lambda r:r['is_deleted'])
    return {'demo_source_removed':True,'evidence_and_prediction_history_preserved':True}
