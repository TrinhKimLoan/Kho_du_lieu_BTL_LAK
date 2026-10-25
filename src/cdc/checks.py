import json
import time
import uuid
from pathlib import Path
from src.source.data import FIELDS,KEYS,prepare,table_digest,fingerprint,canonical
from src.source.runtime import connect
from src.source.demo import action
from .store import pg,epoch,caught_up,consumer,persist
from .codec import TOPICS
from .admin import connector_running


def errors(connection):
    finding=connection.execute("SELECT error_code,safe_message FROM audit.projection_errors WHERE state='OPEN' ORDER BY error_id DESC LIMIT 1").fetchone()
    if finding:raise RuntimeError('Projector error: '+finding['error_code']+': '+finding['safe_message'])
    worker=connection.execute('SELECT worker,safe_error FROM audit.worker_heartbeats WHERE safe_error IS NOT NULL LIMIT 1').fetchone()
    if worker:raise RuntimeError('Worker '+worker['worker']+': '+worker['safe_error'])


def history(connection,dataset):
    digests={}
    for table,fields in FIELDS.items():
        rows=connection.execute('SELECT '+','.join(fields)+' FROM staging.'+table+' WHERE NOT is_demo AND NOT source_is_deleted').fetchall()
        if len(rows)!=len(dataset[table]):raise ValueError('Staging count differs: '+table)
        digest=table_digest(rows,fields,KEYS[table])
        if digest!=dataset['digests'][table]:raise ValueError('Staging full-field digest differs: '+table)
        digests[table]=digest
    rows=connection.execute('''SELECT f.order_id,c.customer_id,p.product_id,f.quantity,f.transaction_unit_price,
        f.goods_amount,f.vat_amount,f.shipping_fee,f.total_paid,s.display_name AS shipping_method,
        f.quantity_band,f.warehouse_name,f.vehicle_type,g.city AS delivery_city,g.district AS delivery_district,
        f.packed_at,f.dispatched_at,f.expected_at,f.received_at,f.is_demo
        FROM dw.v_sales_analysis f JOIN dw.dim_customer c ON c.customer_key=f.customer_key
        JOIN dw.dim_product p ON p.product_key=f.product_key
        JOIN dw.dim_shipping_method s ON s.shipping_method_key=f.shipping_method_key
        JOIN dw.dim_geography g ON g.geography_key=f.delivery_geography_key''').fetchall()
    if len(rows)!=len(dataset['orders']) or table_digest(rows,FIELDS['orders'],'order_id')!=dataset['digests']['orders']:
        raise ValueError('Warehouse full-field orders differ from source input')
    state=connection.execute('SELECT * FROM dw.v_sales_analysis ORDER BY order_id').fetchall()
    totals=connection.execute('SELECT count(*) orders,sum(goods_amount) goods,sum(vat_amount) vat,sum(shipping_fee) shipping_fee,sum(total_paid) total_paid FROM dw.v_sales_analysis').fetchone()
    return {'counts':{k:len(dataset[k]) for k in FIELDS},'staging_digests':digests,
            'fact_state_sha256':fingerprint(state),'money_totals_vnd':canonical(totals)}


def wait_idle(connection,source_epoch,seconds=240):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        errors(connection)
        pending=connection.execute('SELECT count(*) n FROM raw.cdc_events WHERE source_epoch=%s AND processed_at IS NULL',(source_epoch,)).fetchone()['n']
        workers=connection.execute("SELECT count(*) n FROM audit.worker_heartbeats WHERE worker IN ('collector','applier') AND heartbeat_at>now()-interval '30 seconds' AND safe_error IS NULL").fetchone()['n']
        if pending==0 and workers==2 and connector_running() and caught_up(connection,source_epoch):return
        time.sleep(1)
    raise RuntimeError('Timeout waiting for capture/projection idle and healthy workers')


def snapshot(seconds=240):
    dataset=prepare()
    with pg() as connection:
        source_epoch=epoch(connection)
        deadline=time.monotonic()+seconds
        while True:
            errors(connection)
            counts={table:connection.execute('SELECT count(*) n FROM staging.'+table+' WHERE NOT is_demo AND NOT source_is_deleted').fetchone()['n'] for table in FIELDS}
            if all(counts[table]==len(dataset[table]) for table in FIELDS):break
            if time.monotonic()>=deadline:raise RuntimeError('Snapshot source counts did not converge: '+str(counts))
            time.sleep(1)
        wait_idle(connection,source_epoch,max(1,deadline-time.monotonic()))
        result=history(connection,dataset)
        result.update(source_epoch=str(source_epoch),raw_events=connection.execute('SELECT count(*) n FROM raw.cdc_events').fetchone()['n'],pending=0,
            provenance_rows=connection.execute('SELECT count(*) n FROM raw.import_rows').fetchone()['n'])
        if result['provenance_rows']!=len(dataset['import_rows']):raise RuntimeError('Raw provenance count differs')
        return result


def wait_fact(connection,order_id,quantity=None,deleted=False,seconds=120):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        errors(connection)
        row=connection.execute('SELECT * FROM dw.fact_sales WHERE order_id=%s',(order_id,)).fetchone()
        if row and row['is_deleted']==deleted and (quantity is None or row['quantity']==quantity):return row
        time.sleep(0.5)
    raise RuntimeError('Timeout waiting for fact state of demo order '+order_id)


def demo(suffix=None):
    dataset=prepare();suffix=suffix or 'CDC_'+uuid.uuid4().hex[:8]
    order_id='DEMO_'+suffix+'_O';steps=[]
    with pg() as target,connect() as source:
        before=history(target,dataset)
        try:
            for command,quantity,deleted in [('insert',2,False),('update',3,False),('delete',None,True)]:
                step=action(source,command,suffix)
                row=wait_fact(target,order_id,quantity,deleted)
                if not row['is_demo']:raise RuntimeError('Demo lost isolation flag')
                if not deleted and str(row['total_paid'])!=('225000.00' if quantity==2 else '335000.00'):
                    raise RuntimeError('Demo money did not reach warehouse')
                if command=='update' and row['received_at'] is None:raise RuntimeError('Updated delivery timestamp did not reach warehouse')
                steps.append({'action':command,'source_changed':step['changed'],'warehouse_deleted':row['is_deleted'],'warehouse_quantity':row['quantity']})
            wait_idle(target,epoch(target))
            after=history(target,dataset)
            if before['fact_state_sha256']!=after['fact_state_sha256']:raise RuntimeError('Demo modified historical fact state')
            return {'order_id':order_id,'steps':steps,'historical_facts_unchanged':True,'pending':0}
        finally:
            action(source,'delete',suffix)


def replay(seconds=240):
    from confluent_kafka import TopicPartition
    dataset=prepare()
    with pg() as target:
        source_epoch=epoch(target);wait_idle(target,source_epoch)
        before=history(target,dataset)
        product_state=fingerprint(target.execute('SELECT * FROM dw.dim_product ORDER BY product_key').fetchall())
        raw_before=target.execute('SELECT count(*) n FROM raw.cdc_events').fetchone()['n']
        client=consumer('lak-replay-'+uuid.uuid4().hex)
        try:
            positions=[];ends={}
            for topic in TOPICS:
                low,high=client.get_watermark_offsets(TopicPartition(topic,0),timeout=15)
                if low!=0:raise RuntimeError('Replay requires retained Kafka offset 0; no data reset was attempted')
                positions.append(TopicPartition(topic,0,0))
                if high:ends[topic]=high
            client.assign(positions);deadline=time.monotonic()+seconds;new_events=0
            while ends and time.monotonic()<deadline:
                messages=client.consume(num_messages=500,timeout=1)
                if any(m.error() for m in messages):raise RuntimeError('Kafka replay poll error')
                bounded=[m for m in messages if m.topic() in ends and m.offset()<ends[m.topic()]]
                if bounded:
                    inserted,_=persist(target,source_epoch,bounded);new_events+=inserted
                for position in client.position(positions):
                    if position.topic in ends and position.offset>=ends[position.topic]:del ends[position.topic]
            if ends:raise RuntimeError('Replay did not reach captured high watermarks')
        finally:client.close()
        if new_events or target.execute('SELECT count(*) n FROM raw.cdc_events').fetchone()['n']!=raw_before:
            raise RuntimeError('Kafka replay inserted unexpected raw coordinates')
        target.execute('UPDATE raw.cdc_events SET processed_at=NULL WHERE source_epoch=%s',(source_epoch,))
        wait_idle(target,source_epoch,seconds)
        after=history(target,dataset)
        if before['fact_state_sha256']!=after['fact_state_sha256'] or product_state!=fingerprint(target.execute('SELECT * FROM dw.dim_product ORDER BY product_key').fetchall()):
            raise RuntimeError('Raw projection replay changed historical facts or product versions')
        return {'kafka_replay_new_raw_events':new_events,'raw_events':raw_before,
                'projection_replayed':True,'historical_facts_unchanged':True,'product_versions_unchanged':True}


def recovery_seed():
    suffix='RECOVERY_'+uuid.uuid4().hex[:8]
    with connect() as source:result=action(source,'insert',suffix)
    return {'suffix':suffix,'order_id':result['order_id'],'source_insert_committed':result['changed']}


def recovery_finish(seed_path):
    report=json.loads(Path(seed_path).read_text(encoding='utf-8'))
    if not report['passed']:raise RuntimeError('Recovery seed did not pass')
    seed=report['result'];suffix=seed['suffix'];dataset=prepare()
    with pg() as target,connect() as source:
        row=wait_fact(target,seed['order_id'],2,False,180)
        if not row['is_demo']:raise RuntimeError('Recovered order lost demo flag')
        action(source,'update',suffix);wait_fact(target,seed['order_id'],3,False)
        action(source,'delete',suffix);wait_fact(target,seed['order_id'],None,True)
        wait_idle(target,epoch(target));result=history(target,dataset)
    return {'source_change_during_worker_downtime_recovered':True,'insert_update_delete_verified':True,
            'historical_fact_state_sha256':result['fact_state_sha256']}
