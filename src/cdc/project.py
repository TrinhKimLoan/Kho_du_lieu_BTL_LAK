import time
import unicodedata
from datetime import datetime,timezone,timedelta
from src.source.data import FIELDS,KEYS,fingerprint,canonical
from .codec import typed_values,version,expected_count,assemble,TX_TOPIC
from .store import pg,epoch,heartbeat


class Waiting(Exception):
    pass


def geography(connection,city,district):
    if not city or not district:return 0
    def norm(s):return ' '.join(unicodedata.normalize('NFC',s).split()).casefold()
    code=fingerprint([norm(city),norm(district)])
    connection.execute('INSERT INTO dw.dim_geography(geography_code,city,district) VALUES(%s,%s,%s) ON CONFLICT(geography_code) DO NOTHING',(code,city,district))
    return connection.execute('SELECT geography_key FROM dw.dim_geography WHERE geography_code=%s',(code,)).fetchone()['geography_key']


def category(connection,code):
    if not code or code=='UNKNOWN':return 0
    connection.execute('INSERT INTO dw.dim_category(category_code,display_name) VALUES(%s,%s) ON CONFLICT(category_code) DO NOTHING',(code,code))
    return connection.execute('SELECT category_key FROM dw.dim_category WHERE category_code=%s',(code,)).fetchone()['category_key']


def date_key(connection,stamp):
    if stamp is None:return 0
    key=int(stamp.strftime('%Y%m%d'))
    connection.execute('INSERT INTO dw.dim_date(date_key,full_date) VALUES(%s,%s) ON CONFLICT(date_key) DO NOTHING',(key,stamp.date()))
    return key


def shipping(connection,label):
    code={'Giao hàng nhanh':'FAST','Giao hàng bình thường':'NORMAL','Giao hàng chậm':'SLOW'}.get(label)
    if code is None:return 0
    connection.execute('INSERT INTO dw.dim_shipping_method(shipping_method_code,display_name) VALUES(%s,%s) ON CONFLICT(shipping_method_code) DO NOTHING',(code,label))
    return connection.execute('SELECT shipping_method_key FROM dw.dim_shipping_method WHERE shipping_method_code=%s',(code,)).fetchone()['shipping_method_key']


def project_entity(connection,table,row,deleted,moment,event):
    if table=='customers':
        geo=geography(connection,row['profile_city'],row['profile_district'])
        connection.execute('INSERT INTO dw.dim_customer(customer_id,gender,profile_geography_key,is_demo,is_deleted,updated_at) VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT(customer_id) DO UPDATE SET gender=excluded.gender,profile_geography_key=excluded.profile_geography_key,is_demo=excluded.is_demo,is_deleted=excluded.is_deleted,updated_at=excluded.updated_at',
            (row['customer_id'],row['gender'],geo,row['is_demo'],deleted,moment))
        return
    if table=='products':
        category(connection,row['category_code'])
        old=connection.execute('SELECT * FROM dw.dim_product WHERE product_id=%s AND is_current FOR UPDATE',(row['product_id'],)).fetchone()
        attrs=['product_name','product_group','category_code']
        if old and all(old[k]==row[k] for k in attrs):
            connection.execute('UPDATE dw.dim_product SET is_deleted=%s WHERE product_key=%s',(deleted,old['product_key']))
            return
        if old:
            moment=max(moment,old['valid_from']+timedelta(microseconds=1))
            connection.execute('UPDATE dw.dim_product SET is_current=false,valid_to=%s WHERE product_key=%s',(moment,old['product_key']))
        connection.execute('INSERT INTO dw.dim_product(product_id,product_name,product_group,category_code,valid_from,is_current,is_demo,is_deleted) VALUES(%s,%s,%s,%s,%s,true,%s,%s)',
            (row['product_id'],row['product_name'],row['product_group'],row['category_code'],moment,row['is_demo'],deleted))
        return
    old=connection.execute('SELECT f.*,p.product_id existing_product_id,p.category_code existing_category_code FROM dw.fact_sales f JOIN dw.dim_product p ON p.product_key=f.product_key WHERE f.order_id=%s FOR UPDATE OF f',(row['order_id'],)).fetchone()
    if deleted and old:
        connection.execute('UPDATE dw.fact_sales SET is_deleted=true,last_event_id=%s,projected_at=%s WHERE order_id=%s',(event['event_id'],moment,row['order_id']))
        return
    customer=connection.execute('SELECT customer_key FROM dw.dim_customer WHERE customer_id=%s',(row['customer_id'],)).fetchone()
    if old and old['existing_product_id']==row['product_id']:
        product={'product_key':old['product_key'],'category_code':old['existing_category_code']}
    else:
        product=connection.execute('SELECT product_key,category_code FROM dw.dim_product WHERE product_id=%s AND is_current',(row['product_id'],)).fetchone()
    if not customer or not product:raise Waiting('Order is waiting for customer/product dimension')
    result={k:row[k] for k in ('order_id','quantity','transaction_unit_price','goods_amount','vat_amount','shipping_fee','total_paid','quantity_band','warehouse_name','vehicle_type','packed_at','dispatched_at','expected_at','received_at','is_demo')}
    result.update(customer_key=customer['customer_key'],product_key=product['product_key'],category_key=category(connection,product['category_code']),
        delivery_geography_key=geography(connection,row['delivery_city'],row['delivery_district']),shipping_method_key=shipping(connection,row['shipping_method']),
        is_deleted=deleted,source_epoch=event['source_epoch'],last_event_id=event['event_id'],projected_at=moment)
    for prefix in ('packed','dispatched','expected','received'):
        result[prefix+'_date_key']=date_key(connection,row[prefix+'_at'])
    columns=list(result)
    connection.execute('INSERT INTO dw.fact_sales('+','.join(columns)+') VALUES('+','.join(['%s']*len(columns))+') ON CONFLICT(order_id) DO UPDATE SET '+','.join(k+'=excluded.'+k for k in columns if k!='order_id'),tuple(result[k] for k in columns))


def apply_event(connection,event,moment):
    table=event['entity_type'];key=KEYS[table];values=typed_values(event);deleted=event['event_type']=='d'
    old=connection.execute('SELECT * FROM staging.'+table+' WHERE '+key+'=%s FOR UPDATE',(event['entity_key'],)).fetchone()
    if old:
        if old['source_epoch']!=event['source_epoch']:raise ValueError('Mixed source epochs in staging')
        old_version=tuple(old[k] for k in ('source_file_number','source_position','source_row_number','tx_total_order'))
        if version(event)<old_version:return
        if version(event)==old_version:
            if fingerprint({k:old[k] for k in FIELDS[table]})!=fingerprint(values) or old['source_is_deleted']!=deleted:
                raise ValueError('Same source version carries conflicting values')
            return
    payload=dict(values,source_is_deleted=deleted,source_epoch=event['source_epoch'],
        source_file_number=version(event)[0],source_position=version(event)[1],source_row_number=version(event)[2],
        tx_total_order=version(event)[3],last_event_id=event['event_id'],observed_at=moment)
    columns=list(payload)
    connection.execute('INSERT INTO staging.'+table+'('+','.join(columns)+') VALUES('+','.join(['%s']*len(columns))+') ON CONFLICT('+key+') DO UPDATE SET '+','.join(k+'=excluded.'+k for k in columns if k!=key),tuple(payload[k] for k in columns))
    project_entity(connection,table,values,deleted,moment,event)


def mark(connection,events):
    if events:connection.execute('UPDATE raw.cdc_events SET processed_at=now() WHERE event_id=ANY(%s)',([e['event_id'] for e in events],))


def step(connection,source_epoch):
    invalid=connection.execute("SELECT event_id FROM raw.cdc_events WHERE source_epoch=%s AND processed_at IS NULL AND event_type='invalid' LIMIT 1",(source_epoch,)).fetchone()
    if invalid:raise ValueError('Invalid captured envelope at event '+str(invalid['event_id']))
    kind=connection.execute("SELECT entity_type FROM raw.cdc_events WHERE source_epoch=%s AND processed_at IS NULL AND event_type='r' ORDER BY CASE entity_type WHEN 'customers' THEN 0 WHEN 'products' THEN 1 ELSE 2 END,event_id LIMIT 1",(source_epoch,)).fetchone()
    if kind:
        events=connection.execute("SELECT * FROM raw.cdc_events WHERE source_epoch=%s AND processed_at IS NULL AND event_type='r' AND entity_type=%s ORDER BY event_id LIMIT 500",(source_epoch,kind['entity_type'])).fetchall()
        with connection.transaction():
            moment=datetime.now(timezone.utc)
            for event in events:apply_event(connection,event,moment)
            mark(connection,events)
        return len(events)
    end=connection.execute("SELECT * FROM raw.cdc_events WHERE source_epoch=%s AND processed_at IS NULL AND event_type='END' ORDER BY kafka_offset LIMIT 1",(source_epoch,)).fetchone()
    if end:
        events=connection.execute('SELECT * FROM raw.cdc_events WHERE source_epoch=%s AND source_tx_id=%s ORDER BY event_id',(source_epoch,end['source_tx_id'])).fetchall()
        ledger=connection.execute('SELECT * FROM audit.applied_source_transactions WHERE source_epoch=%s AND source_tx_id=%s',(source_epoch,end['source_tx_id'])).fetchone()
        data=[e for e in events if e['event_type'] in ('c','u','d')]
        if ledger:
            original=assemble(data,ledger['expected_data_events'])
            if original is None:raise ValueError('Applied ledger has incomplete original raw data')
            for boundary in (e for e in events if e['event_type']=='END'):
                if expected_count(boundary) not in (0,ledger['expected_data_events']):raise ValueError('Restart END conflicts with applied ledger')
            with connection.transaction():mark(connection,[e for e in events if e['processed_at'] is None])
            return 1
        expected=expected_count(end);ordered=assemble(data,expected)
        if ordered is None:raise Waiting('Waiting for complete source transaction')
        latest={}
        for event in ordered:latest[(event['entity_type'],event['entity_key'])]=event
        priority={'customers':0,'products':1,'orders':2}
        with connection.transaction():
            moment=datetime.now(timezone.utc)
            for event in sorted(latest.values(),key=lambda e:(priority[e['entity_type']],e['tx_total_order'])):apply_event(connection,event,moment)
            connection.execute('INSERT INTO audit.applied_source_transactions(source_epoch,source_tx_id,end_event_id,expected_data_events,applied_data_events,end_topic,end_partition,end_offset,applied_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                (source_epoch,end['source_tx_id'],end['event_id'],expected,len(ordered),end['topic'],end['partition_id'],end['kafka_offset'],moment))
            mark(connection,events)
        return len(events)
    tombstones=connection.execute("SELECT event_id FROM raw.cdc_events WHERE source_epoch=%s AND processed_at IS NULL AND event_type='tombstone' LIMIT 500",(source_epoch,)).fetchall()
    with connection.transaction():mark(connection,tombstones)
    return len(tombstones)


def run():
    with pg() as connection:
        if not connection.execute('SELECT pg_try_advisory_lock(274104)').fetchone()['pg_try_advisory_lock']:
            raise RuntimeError('Another LAK projector owns the database lock')
        source_epoch=epoch(connection)
        while True:
            try:
                try:processed=step(connection,source_epoch)
                except Waiting:processed=0
                if processed:
                    connection.execute("UPDATE audit.projection_errors e SET state='RESOLVED',resolved_at=now() FROM raw.cdc_events r WHERE e.event_id=r.event_id AND e.state='OPEN' AND r.processed_at IS NOT NULL")
                heartbeat(connection,'applier')
                if not processed:time.sleep(0.4)
            except Exception as exc:
                message=type(exc).__name__+': '+str(exc)[:1200]
                heartbeat(connection,'applier',message)
                candidate=connection.execute('SELECT event_id FROM raw.cdc_events WHERE processed_at IS NULL ORDER BY event_id LIMIT 1').fetchone()
                if candidate:
                    connection.execute("INSERT INTO audit.projection_errors(event_id,error_code,safe_message,state) SELECT %s,%s,%s,'OPEN' WHERE NOT EXISTS(SELECT 1 FROM audit.projection_errors WHERE event_id=%s AND state='OPEN')",(candidate['event_id'],type(exc).__name__,message,candidate['event_id']))
                raise
