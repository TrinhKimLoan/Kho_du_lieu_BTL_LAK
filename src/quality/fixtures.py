import uuid
from src.cdc.store import pg,epoch
from .retry import request_retry,resolve_processed


def check():
    """Real PostgreSQL negative cases, all data fixtures rolled back."""
    import psycopg
    passed=[];token='DEMO_SQL5_'+uuid.uuid4().hex[:8]
    with pg() as target:
        # An explicit outer rollback keeps successful fixtures invisible to the workers.
        with target.transaction(force_rollback=True):
            target.execute("INSERT INTO dw.dim_product(product_id,product_name,valid_from,valid_to,is_current,is_demo) VALUES(%s,'fixture','2025-01-01','2025-02-01',false,true)",(token,))
            target.execute("INSERT INTO dw.dim_product(product_id,product_name,valid_from,is_current,is_demo) VALUES(%s,'fixture','2025-02-01',true,true)",(token,))
            passed.append('adjacent_scd2_bounds_accepted')
            cases=[
                ('overlap_rejected',"INSERT INTO dw.dim_product(product_id,product_name,valid_from,valid_to,is_current,is_demo) VALUES(%s,'fixture','2025-01-15','2025-02-15',false,true)",(token,),'23P01'),
                ('second_current_rejected',"INSERT INTO dw.dim_product(product_id,product_name,valid_from,is_current,is_demo) VALUES(%s,'fixture','2025-03-01',true,true)",(token,),'23'),
                ('bad_money_rejected',"UPDATE dw.fact_sales SET total_paid=1 WHERE sales_key=(SELECT min(sales_key) FROM dw.fact_sales WHERE NOT is_demo)",None,'23514'),
                ('orphan_product_rejected',"UPDATE dw.fact_sales SET product_key=-1 WHERE sales_key=(SELECT min(sales_key) FROM dw.fact_sales WHERE NOT is_demo)",None,'23503'),
                ('wrong_date_role_rejected',"UPDATE dw.fact_sales SET packed_date_key=0 WHERE sales_key=(SELECT min(sales_key) FROM dw.fact_sales WHERE NOT is_demo AND packed_at IS NOT NULL)",None,'23514'),
            ]
            if not target.execute('SELECT 1 FROM dw.fact_sales WHERE NOT is_demo LIMIT 1').fetchone():raise RuntimeError('Historical facts are required for negative fixtures')
            for label,sql,params,expected in cases:
                try:
                    with target.transaction():
                        result=target.execute(sql,params)
                        if result.rowcount==0:raise RuntimeError('Negative fixture affected no rows')
                except psycopg.Error as exc:
                    if not exc.sqlstate.startswith(expected):raise
                    passed.append(label)
                else:raise RuntimeError('Database accepted negative case: '+label)
            unknown=target.execute("SELECT to_jsonb(p)->>'valid_from' AS bound FROM dw.dim_product p WHERE product_key=0").fetchone()
            if not unknown or unknown['bound']!='-infinity':raise RuntimeError('Unknown SCD2 member lost -infinity boundary')
            passed.append('unknown_infinite_boundary_preserved')
            event=target.execute("INSERT INTO raw.cdc_events(source_epoch,topic,partition_id,kafka_offset,event_type,content_sha256) VALUES(%s,%s,0,0,'tombstone',%s) RETURNING event_id",(epoch(target),'phase5-fixture-'+token,'0'*64)).fetchone()['event_id']
            error=target.execute("INSERT INTO audit.projection_errors(event_id,error_code,safe_message,state) VALUES(%s,'PHASE5_FIXTURE','Rollback-only retry lifecycle fixture','OPEN') RETURNING error_id",(event,)).fetchone()['error_id']
            if request_retry(target,error)['state']!='RETRYING':raise RuntimeError('Retry state did not advance')
            if request_retry(target,error)['changed']:raise RuntimeError('Repeated retry request is not idempotent')
            attempts=target.execute('SELECT attempts FROM audit.projection_errors WHERE error_id=%s',(error,)).fetchone()['attempts']
            if attempts!=1:raise RuntimeError('Retry request count should be one')
            target.execute('UPDATE raw.cdc_events SET processed_at=now() WHERE event_id=%s',(event,))
            resolve_processed(target)
            if request_retry(target,error)['state']!='RESOLVED':raise RuntimeError('Processed retry did not resolve')
            passed.append('retry_request_idempotent_and_processed_error_resolves')
        if target.execute('SELECT 1 FROM dw.dim_product WHERE product_id=%s',(token,)).fetchone():raise RuntimeError('SQL fixture was not rolled back')
    return {'passed':True,'cases':passed,'data_fixtures_rolled_back':True,
            'retry_scope':'database lifecycle fixture; not a process crash or poison-event recovery test'}
