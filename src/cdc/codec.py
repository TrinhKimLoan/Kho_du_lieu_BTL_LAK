import hashlib
import json
import re
from datetime import datetime,timedelta
from decimal import Decimal,ROUND_HALF_UP
from src.source.data import FIELDS,KEYS,fingerprint

PREFIX='lakanalytics'
DATABASE='lak_source'
TX_TOPIC=PREFIX+'.transaction'
TOPICS=[PREFIX+'.'+DATABASE+'.'+name for name in FIELDS]+[TX_TOPIC]
GROUP='lak-raw-v1'
MONEY={'catalog_unit_price','transaction_unit_price','goods_amount','vat_amount','shipping_fee','total_paid'}
TIMES={'packed_at','dispatched_at','expected_at','received_at'}


def unwrap(value):
    return value['payload'] if isinstance(value,dict) and 'schema' in value and 'payload' in value else value


def bytes_hash(key,value):
    h=hashlib.sha256()
    for blob in (key,value):
        h.update(b'N' if blob is None else b'B'+len(blob).to_bytes(8,'big')+blob)
    return h.hexdigest()


def decode(topic,partition,offset,key_bytes,value_bytes):
    row={'topic':topic,'partition_id':partition,'kafka_offset':offset,
         'key_bytes':key_bytes,'value_bytes':value_bytes,'content_sha256':bytes_hash(key_bytes,value_bytes),
         'record_key':None,'record_value':None,'event_type':'invalid','entity_type':None,
         'entity_key':None,'source_tx_id':None,'tx_total_order':None,
         'source_file_number':None,'source_position':None,'source_row_number':None}
    try:
        row['record_key']=json.loads(key_bytes) if key_bytes is not None else None
        row['record_value']=json.loads(value_bytes) if value_bytes is not None else None
        key=unwrap(row['record_key']);body=unwrap(row['record_value'])
        if value_bytes is None:
            row['event_type']='tombstone'
            return row
        if not isinstance(body,dict):raise ValueError('Not a Debezium object')
        if topic==TX_TOPIC:
            if partition!=0 or body.get('status') not in ('BEGIN','END') or not body.get('id'):
                raise ValueError('Invalid transaction metadata')
            row.update(event_type=body['status'],source_tx_id=str(body['id']))
        else:
            table=(body.get('source') or {}).get('table')
            if table not in FIELDS or topic!=PREFIX+'.'+DATABASE+'.'+table:raise ValueError('Unexpected source table')
            op=body.get('op')
            if op not in ('r','c','u','d'):raise ValueError('Unexpected operation')
            if not isinstance(key,dict) or KEYS[table] not in key:raise ValueError('Missing business key')
            source=body.get('source') or {};tx=body.get('transaction') or {}
            file_match=re.search(r'\.(\d+)$',source.get('file') or '')
            if op!='r' and (not file_match or source.get('pos') is None or not tx.get('id') or tx.get('total_order') is None):
                raise ValueError('Missing streaming position/transaction metadata')
            row.update(event_type=op,entity_type=table,entity_key=str(key[KEYS[table]]),
                       source_tx_id=str(tx['id']) if tx.get('id') is not None else None,
                       tx_total_order=int(tx.get('total_order') or 0),
                       source_file_number=int(file_match[1]) if file_match else 0,
                       source_position=int(source.get('pos') or 0),source_row_number=int(source.get('row') or 0))
    except (ValueError,TypeError,KeyError,OverflowError):
        row['event_type']='invalid'
    return row


def typed_values(event):
    table=event['entity_type'];body=unwrap(event['record_value'])
    raw=body.get('before') if event['event_type']=='d' else body.get('after')
    if not isinstance(raw,dict) or any(f not in raw for f in FIELDS[table]):
        raise ValueError('Incomplete row image for '+table)
    values={f:raw[f] for f in FIELDS[table]}
    if str(values[KEYS[table]])!=event['entity_key']:raise ValueError('Key and row image disagree')
    for field,value in values.items():
        if field in MONEY and value is not None:
            if isinstance(value,(float,bool)):raise ValueError('Decimal arrived as floating point')
            amount=Decimal(str(value))
            if not amount.is_finite() or amount!=amount.quantize(Decimal('0.01')):raise ValueError('Invalid money scale')
            values[field]=amount
        elif field in TIMES and value is not None:
            if isinstance(value,int) and not isinstance(value,bool):
                stamp=datetime(1970,1,1)+timedelta(milliseconds=value)
                if not 2000<=stamp.year<=2100:raise ValueError('Unexpected DATETIME precision/range')
                values[field]=stamp
            elif isinstance(value,str):
                stamp=datetime.fromisoformat(value)
                if stamp.tzinfo is not None:raise ValueError('Business DATETIME unexpectedly contains timezone')
                values[field]=stamp
            else:raise ValueError('Invalid business timestamp')
    if values['is_demo'] not in (False,True,0,1):raise ValueError('Invalid demo flag')
    values['is_demo']=bool(values['is_demo'])
    if values['is_demo']!=str(values[KEYS[table]]).startswith('DEMO_'):raise ValueError('Demo namespace mismatch')
    if table=='orders' and event['event_type']!='d':
        q=values['quantity'];unit=values['transaction_unit_price']
        if type(q) is not int or q<=0 or unit<=0:raise ValueError('Invalid quantity/unit price')
        g,v,s,t=[values[k] for k in ('goods_amount','vat_amount','shipping_fee','total_paid')]
        if any(x<0 for x in (g,v,s,t)) or g!=q*unit or v!=(g*Decimal('0.1')).quantize(Decimal('0.01'),rounding=ROUND_HALF_UP) or t!=g+v+s:
            raise ValueError('Order money mismatch')
    return values


def version(event):
    return tuple(int(event.get(k) or 0) for k in ('source_file_number','source_position','source_row_number','tx_total_order'))


def expected_count(end):
    body=unwrap(end['record_value'])
    collections=body.get('data_collections')
    if collections is None:
        if body.get('event_count')==0:return 0
        raise ValueError('Missing transaction data_collections')
    count=sum(int(item['event_count']) for item in collections if item.get('data_collection') in {DATABASE+'.'+name for name in FIELDS})
    if count<0:raise ValueError('Negative transaction count')
    return count


def assemble(events,expected):
    unique={}
    for event in events:
        order=event.get('tx_total_order')
        if type(order) is not int or order<1:raise ValueError('Invalid transaction total_order')
        if order in unique and change_fingerprint(unique[order])!=change_fingerprint(event):
            raise ValueError('Conflicting repeated transaction event')
        unique[order]=event
    if len(unique)>expected:raise ValueError('More transaction events than END declares')
    return [unique[k] for k in sorted(unique)] if len(unique)==expected else None


def change_fingerprint(event):
    body=unwrap(event['record_value'])
    before=None
    if body.get('before') is not None:
        previous=dict(event)
        previous['record_value']=dict(body,op='d')
        previous['event_type']='d'
        before=typed_values(previous)
    return fingerprint([event['entity_type'],event['entity_key'],event['event_type'],
                        version(event),before,typed_values(event)])
