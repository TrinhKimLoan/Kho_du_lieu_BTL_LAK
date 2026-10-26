import unittest
from datetime import datetime,timedelta
from unittest.mock import Mock
import numpy as np
from src.inference.logic import delivery_input,outcome,stamp
from src.inference.models import Models
from src.delivery.features import construct,matrix
from src.news.model import digest


def payload():
    return {'order_id':'DEMO_TEST','dispatched_at':'2025-12-21T09:00:00','received_at':None,'is_deleted':False,
            'features':{'quantity':2,'goods_amount':200000,'shipping_method':'FAST','quantity_band':'Hàng ít',
                        'warehouse_name':'WH','vehicle_type':'VAN','delivery_district':'D1'}}


class InferenceTests(unittest.TestCase):
    def test_live_features_equal_training_features(self):
        p=payload();source=[]
        for year in [2023,2024,2025]:
            for i in range(30):
                start=datetime(year,2,1)+timedelta(days=i)
                source.append(dict(p['features'],order_id=str(year)+'-'+str(i),dispatched_at=start,received_at=start+timedelta(hours=27)))
        rows,_=construct(source)
        p['dispatched_at']=rows[0]['dispatched_at']
        np.testing.assert_array_equal(matrix([delivery_input(p)]),matrix([rows[0]]))

    def test_actual_outcome_never_enters_predictors(self):
        a=payload();b=dict(a,received_at='2025-12-22T12:00:00',expected_at='2025-12-23',phone='private')
        self.assertEqual(delivery_input(a),delivery_input(b))
        self.assertNotIn('received_at',delivery_input(b)['features'])

    def test_outcome_uses_original_prediction(self):
        p=payload();p['received_at']='2025-12-22T12:00:00'
        prediction={'dispatched_at':p['dispatched_at'],'predicted_hours':30.0}
        self.assertEqual(outcome(prediction,p),{'state':'RECEIVED','actual_hours':27.,'error_hours':3.})
        self.assertEqual(prediction['predicted_hours'],30.)

    def test_dispatch_correction_is_not_scored_as_original(self):
        p=payload();prediction={'dispatched_at':'2025-12-20T09:00:00','predicted_hours':30}
        self.assertEqual(outcome(prediction,p)['state'],'DISPATCH_CORRECTED')

    def test_pending(self):
        p=payload();self.assertEqual(outcome({'dispatched_at':p['dispatched_at'],'predicted_hours':30},p)['state'],'PENDING')

    def test_deleted_order_retains_prediction(self):
        p=payload();p['is_deleted']=True
        self.assertEqual(outcome({'dispatched_at':None},p)['state'],'DELETED')

    def test_negative_duration_is_not_evaluated(self):
        p=payload();p['received_at']='2025-01-01T09:00:00'
        result=outcome({'dispatched_at':p['dispatched_at'],'predicted_hours':1},p)
        self.assertEqual(result['state'],'INVALID_TIME');self.assertIsNone(result['error_hours'])

    def test_unknown_missing_category_has_training_representation(self):
        p=payload();p['features']['warehouse_name']=None;p['features']['vehicle_type']='NEW'
        row=delivery_input(p);self.assertIsNone(row['features']['warehouse_name']);self.assertEqual(row['features']['vehicle_type'],'NEW')
        self.assertEqual(matrix([row])[0,7],'__MISSING__')

    def test_nonfinite_live_feature_rejected(self):
        p=payload();p['features']['goods_amount']=float('inf')
        with self.assertRaises(ValueError):delivery_input(p)

    def test_input_identity_changes_only_for_input(self):
        p=payload();old=digest(delivery_input(p));p['received_at']='2025-12-22T12:00:00'
        self.assertEqual(old,digest(delivery_input(p)));p['features']['quantity']=3
        self.assertNotEqual(old,digest(delivery_input(p)))

    def test_unready_model_rejected_before_load(self):
        connection=Mock();connection.execute.return_value.fetchone.return_value={'algorithm':'kmeans_rfm','status':'RETIRED'}
        with self.assertRaises(RuntimeError):Models().get(connection,'x','RFM')

    def test_wrong_algorithm_rejected(self):
        connection=Mock();connection.execute.return_value.fetchone.return_value={'algorithm':'kmeans_rfm','status':'READY'}
        with self.assertRaises(RuntimeError):Models().get(connection,'x','DELIVERY')
