import hashlib
from datetime import date,datetime
from decimal import Decimal
from src.news.model import digest

REFERENCE=date(2026,1,1)
FEATURES=['recency_days','frequency','monetary']
CONTRACT={'version':'lak-rfm-v1','reference_date':REFERENCE.isoformat(),'window_start':None,
          'time_proxy':'packed_at (not order_created_at)','frequency':'distinct order_id',
          'monetary':'goods_amount VND, excluding VAT/shipping','exclude_demo_deleted':True,
          'missing_time':'exclude from RFM only; preserve financial facts','features':FEATURES,
          'split_seed':'lak-customer-split-v1','split_fractions':[0.6,0.2,0.2]}


def row_payload(row):
    return {'customer_id':row['customer_id'],'recency_days':int(row['recency_days']),
            'frequency':int(row['frequency']),'monetary':format(Decimal(row['monetary']),'.2f'),
            'last_packed_at':row['last_packed_at'].isoformat(timespec='microseconds')}


def validate(rows):
    seen=set()
    for row in rows:
        if row['customer_id'] in seen:raise ValueError('Duplicate customer in RFM snapshot')
        seen.add(row['customer_id'])
        if type(row['recency_days']) is not int or row['recency_days']<1:raise ValueError('Invalid R for exclusive reference date')
        if type(row['frequency']) is not int or row['frequency']<1:raise ValueError('Invalid F')
        money=Decimal(row['monetary'])
        if not money.is_finite() or money<=0 or money!=money.quantize(Decimal('.01')):raise ValueError('Invalid M')
        if row['last_packed_at'].date()>=REFERENCE:raise ValueError('Future transaction leaked into snapshot')
        if row['recency_days']!=(REFERENCE-row['last_packed_at'].date()).days:raise ValueError('R does not match last packed date')
    if len(rows)<30:raise ValueError('At least 30 eligible customers required for fixed holdout evaluation')


def split_customers(rows):
    validate(rows)
    order=sorted(rows,key=lambda row:hashlib.sha256((CONTRACT['split_seed']+'|'+row['customer_id']).encode()).hexdigest())
    train_end=int(len(order)*.6);val_end=train_end+int(len(order)*.2)
    splits={r['customer_id']:'train' if i<train_end else 'validation' if i<val_end else 'test' for i,r in enumerate(order)}
    return [dict(r,split=splits[r['customer_id']]) for r in sorted(rows,key=lambda r:r['customer_id'])]


def snapshot_id(rows,source_sha256=""):
    return 'rfm-'+digest({'contract':CONTRACT,'source_sha256':source_sha256,'rows':[dict(row_payload(r),split=r['split']) for r in sorted(rows,key=lambda r:r['customer_id'])]})[:24]


def from_orders(orders):
    """Reference computation used for offline verification against original LAK."""
    groups={};seen=set()
    for order in orders:
        if order.get('is_demo') or order.get('is_deleted'):continue
        stamp=order.get('packed_at')
        if stamp is None or stamp.date()>=REFERENCE:continue
        key=order['order_id']
        if key in seen:raise ValueError('Duplicate order cannot contribute to F or M twice')
        seen.add(key);customer=order['customer_id']
        item=groups.setdefault(customer,{'customer_id':customer,'frequency':0,'monetary':Decimal('0.00'),'last_packed_at':stamp})
        item['frequency']+=1;item['monetary']+=Decimal(order['goods_amount']);item['last_packed_at']=max(item['last_packed_at'],stamp)
    result=[]
    for customer,row in groups.items():
        row['recency_days']=(REFERENCE-row['last_packed_at'].date()).days;result.append(row)
    return split_customers(result)
