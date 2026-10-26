import time
import numpy as np
from src.cdc.store import pg,heartbeat
from src.cdc.cli import sanitize
from src.news.model import digest
from src.delivery.features import matrix
from .logic import delivery_input,outcome,stamp
from .models import Models


def rfm(connection,job,models):
    from psycopg.types.json import Jsonb
    customer=int(job['entity_key'])
    facts=connection.execute('''SELECT order_id,packed_at,goods_amount FROM dw.fact_sales
      WHERE customer_key=%s AND is_demo=%s AND NOT is_deleted AND packed_at<%s::date ORDER BY order_id''',
      (customer,job['is_demo'],job['reference_date'])).fetchall()
    inputs={'frequency':len(facts),'monetary':format(sum(r['goods_amount'] for r in facts),'.2f'),
            'reference_date':job['reference_date'].isoformat(),'source_sha256':digest([dict(r,packed_at=r['packed_at'].isoformat(),goods_amount=str(r['goods_amount'])) for r in facts])}
    cluster=None;state='NO_HISTORY'
    if facts:
        inputs['recency_days']=(job['reference_date']-max(r['packed_at'] for r in facts).date()).days
        if float(inputs['monetary'])>0:
            model=models.get(connection,job['model_id'],'RFM')
            cluster=int(model.predict(np.array([[inputs['recency_days'],inputs['frequency'],float(inputs['monetary'])]]))[0]);state='ASSIGNED'
        else:state='NO_POSITIVE_VALUE'
    connection.execute('''INSERT INTO ml.rfm_assignment_history(job_id,customer_key,is_demo,model_id,reference_date,input,input_sha256,cluster_id,state)
      VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)''',(job['job_id'],customer,job['is_demo'],job['model_id'],job['reference_date'],Jsonb(inputs),digest(inputs),cluster,state))
    connection.execute('''INSERT INTO ml.rfm_current_assignments(customer_key,is_demo,model_id,reference_date,job_id) VALUES(%s,%s,%s,%s,%s)
      ON CONFLICT(customer_key,is_demo,model_id,reference_date) DO UPDATE SET job_id=excluded.job_id
      WHERE ml.rfm_current_assignments.job_id<excluded.job_id''',(customer,job['is_demo'],job['model_id'],job['reference_date'],job['job_id']))
    return {'state':state,'cluster_id':cluster,'input_sha256':digest(inputs)}


def delivery(connection,job,models):
    from psycopg.types.json import Jsonb
    payload=job['payload']
    prediction=connection.execute('SELECT * FROM ml.live_delivery_predictions WHERE order_id=%s AND is_demo=%s',(job['entity_key'],job['is_demo'])).fetchone()
    if not prediction:
        if payload['is_deleted']:return {'state':'SKIPPED_DELETED'}
        if payload.get('dispatched_at') is None:return {'state':'WAITING_FOR_DISPATCH'}
        if payload.get('received_at') is not None:return {'state':'SKIPPED_ALREADY_RECEIVED','live_prediction_created':False}
        inputs=delivery_input(payload);model=models.get(connection,job['model_id'],'DELIVERY')
        value=float(model.predict(matrix([inputs]))[0])
        if not np.isfinite(value) or value<0:raise RuntimeError('Invalid live prediction')
        prediction=connection.execute('''INSERT INTO ml.live_delivery_predictions(order_id,is_demo,model_id,job_id,dispatched_at,input,input_sha256,predicted_hours,observed_at)
          VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *''',(job['entity_key'],job['is_demo'],job['model_id'],job['job_id'],stamp(payload['dispatched_at']),Jsonb(inputs),digest(inputs),value,stamp(payload['observed_at']))).fetchone()
    result=outcome(prediction,payload)
    connection.execute('INSERT INTO ml.delivery_outcome_history(job_id,prediction_id,received_at,state,actual_hours,error_hours) VALUES(%s,%s,%s,%s,%s,%s)',
        (job['job_id'],prediction['prediction_id'],stamp(payload.get('received_at')),result['state'],result['actual_hours'],result['error_hours']))
    return dict(result,prediction_id=prediction['prediction_id'],original_prediction_preserved=True)


def step(connection,models):
    from psycopg.types.json import Jsonb
    job=None
    try:
        with connection.transaction():
            job=connection.execute("SELECT * FROM ml.inference_jobs WHERE state IN ('PENDING','RETRY') AND available_at<=now() ORDER BY job_id FOR UPDATE SKIP LOCKED LIMIT 1").fetchone()
            if not job:return False
            old=connection.execute('SELECT 1 FROM ml.inference_receipts WHERE job_id=%s',(job['job_id'],)).fetchone()
            if not old:
                result=rfm(connection,job,models) if job['kind']=='RFM' else delivery(connection,job,models)
                connection.execute('INSERT INTO ml.inference_receipts(job_id,result) VALUES(%s,%s)',(job['job_id'],Jsonb(result)))
            connection.execute("UPDATE ml.inference_jobs SET state='DONE',attempts=attempts+1,safe_error=NULL,finished_at=now() WHERE job_id=%s",(job['job_id'],))
    except Exception as exc:
        if not job:raise
        connection.execute("""UPDATE ml.inference_jobs SET attempts=attempts+1,state=CASE WHEN attempts+1>=5 THEN 'FAILED' ELSE 'RETRY' END,
           available_at=now()+interval '5 seconds',safe_error=%s WHERE job_id=%s""",(sanitize(type(exc).__name__+': '+str(exc))[:1200],job['job_id']))
    return True


def run(once=False):
    models=Models()
    with pg() as connection:
        if not connection.execute('SELECT pg_try_advisory_lock(274111) AS locked').fetchone()['locked']:raise RuntimeError('Inference worker already running')
        if not connection.execute('SELECT 1 FROM ml.inference_config WHERE singleton').fetchone():raise RuntimeError('Initialize Phase 10 before worker')
        while True:
            processed=step(connection,models)
            failed=connection.execute("SELECT count(*) AS n FROM ml.inference_jobs WHERE state='FAILED'").fetchone()['n']
            heartbeat(connection,'ml-inference','Failed inference jobs: '+str(failed) if failed else None)
            if once and not processed:break
            if not processed:time.sleep(1)
