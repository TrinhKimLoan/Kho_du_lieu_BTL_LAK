from datetime import datetime
from collections import Counter
import math
from src.news.model import digest

REFERENCE = datetime(2026, 1, 1)
NUMERIC = ['quantity', 'goods_amount', 'dispatch_month', 'dispatch_weekday', 'dispatch_hour']
CATEGORICAL = ['shipping_method', 'quantity_band', 'warehouse_name', 'vehicle_type', 'delivery_district']
FEATURES = NUMERIC + CATEGORICAL
CONTRACT = {
    'version': 'lak-delivery-v1', 'prediction_time': 'dispatched_at', 'unit': 'hours',
    'target': '(received_at-dispatched_at).total_seconds()/3600',
    'reference_date': '2026-01-01', 'features': FEATURES,
    'train': '2020-2023 dispatch; received before 2024-01-01',
    'validation': '2024 dispatch; received before 2025-01-01',
    'test': '2025 dispatch; received before 2026-01-01',
    'availability_assumption': 'All predictors must be entered by dispatch; original Excel has no event-time input log to prove this.',
    'excluded': ['received_at', 'expected_at', 'packed_at', 'delivery_hours', 'customer_id', 'product_id', 'order_id', 'driver', 'full_address', 'phone', 'shipping_fee'],
    'source': 'current warehouse historical state; not reconstructed point-in-time CDC versions',
    'missing_predictors': 'numeric median and categorical constant fitted on train only',
    'excluded_demo_deleted': True,
}


def construct(source):
    rows = []; counts = Counter(); seen = set()
    for order in sorted(source, key=lambda r: r['order_id']):
        if order['order_id'] in seen: raise ValueError('Duplicate order')
        seen.add(order['order_id']); counts['source_orders'] += 1
        reason = None
        start, end = order.get('dispatched_at'), order.get('received_at')
        if order.get('is_demo') or order.get('is_deleted'): reason = 'demo_or_deleted'
        elif start is None or end is None: reason = 'missing_label_time'
        elif end < start: reason = 'negative_duration'
        elif not datetime(2020,1,1) <= start < REFERENCE: reason = 'outside_window'
        else:
            split = 'train' if start.year < 2024 else 'validation' if start.year == 2024 else 'test'
            cutoff = datetime(2024,1,1) if split == 'train' else datetime(2025,1,1) if split == 'validation' else REFERENCE
            if end >= cutoff: reason = 'label_not_available_' + split
        if reason:
            counts[reason] += 1; continue
        features = {k: None if order.get(k) is None else float(order[k]) for k in ['quantity','goods_amount']}
        features.update(dispatch_month=start.month, dispatch_weekday=start.weekday(), dispatch_hour=start.hour)
        features.update({k: str(order[k]) if order.get(k) is not None and str(order[k]).strip() else None for k in CATEGORICAL})
        if any(v is not None and not math.isfinite(v) for v in [features[k] for k in NUMERIC]): raise ValueError('Nonfinite predictor')
        if features['quantity'] is not None and (features['quantity'] <= 0 or features['quantity'] % 1): raise ValueError('Invalid quantity')
        if features['goods_amount'] is not None and features['goods_amount'] < 0: raise ValueError('Invalid goods amount')
        rows.append({'order_id':order['order_id'], 'dispatched_at':start.isoformat(timespec='microseconds'),
                     'received_at':end.isoformat(timespec='microseconds'), 'split':split,
                     'target_hours':(end-start).total_seconds()/3600, 'features':features})
        counts['eligible_' + split] += 1
    rows.sort(key=lambda r:(r['dispatched_at'],r['order_id']))
    for split in ['train','validation','test']:
        if counts['eligible_' + split] < 30: raise ValueError('At least 30 eligible orders per chronological split required: ' + split)
    if len(rows) + sum(v for k,v in counts.items() if not k.startswith('eligible_') and k != 'source_orders') != counts['source_orders']: raise RuntimeError('Cohort accounting differs')
    return rows, dict(counts)


def identity(rows):
    return 'delivery-' + digest({'contract':CONTRACT, 'rows':rows})[:24]


def matrix(rows):
    import numpy as np
    return np.array([[float(r['features'][k]) if r['features'][k] is not None else np.nan for k in NUMERIC] +
                     [r['features'][k] if r['features'][k] is not None else '__MISSING__' for k in CATEGORICAL] for r in rows], dtype=object)
