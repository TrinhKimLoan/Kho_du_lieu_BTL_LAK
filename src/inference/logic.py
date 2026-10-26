from datetime import datetime
import math
from src.delivery.features import NUMERIC,CATEGORICAL


def stamp(value):
    return datetime.fromisoformat(value) if isinstance(value,str) else value


def delivery_input(payload):
    start=stamp(payload['dispatched_at']);raw=payload['features']
    features={k:None if raw.get(k) is None else float(raw[k]) for k in ['quantity','goods_amount']}
    features.update(dispatch_month=start.month,dispatch_weekday=start.weekday(),dispatch_hour=start.hour)
    features.update({k:str(raw[k]) if raw.get(k) is not None and str(raw[k]).strip() else None for k in CATEGORICAL})
    if any(v is not None and not math.isfinite(v) for v in [features[k] for k in NUMERIC]):raise ValueError('Nonfinite live predictor')
    if features['quantity'] is not None and (features['quantity']<=0 or features['quantity']%1):raise ValueError('Invalid live quantity')
    if features['goods_amount'] is not None and features['goods_amount']<0:raise ValueError('Invalid live goods amount')
    return {'dispatched_at':start.isoformat(timespec='microseconds'),'features':features}


def outcome(prediction,payload):
    if payload['is_deleted']:return {'state':'DELETED','actual_hours':None,'error_hours':None}
    if stamp(payload['dispatched_at'])!=stamp(prediction['dispatched_at']):return {'state':'DISPATCH_CORRECTED','actual_hours':None,'error_hours':None}
    if payload.get('received_at') is None:return {'state':'PENDING','actual_hours':None,'error_hours':None}
    hours=(stamp(payload['received_at'])-stamp(prediction['dispatched_at'])).total_seconds()/3600
    if hours<0:return {'state':'INVALID_TIME','actual_hours':None,'error_hours':None}
    return {'state':'RECEIVED','actual_hours':hours,'error_hours':prediction['predicted_hours']-hours}
