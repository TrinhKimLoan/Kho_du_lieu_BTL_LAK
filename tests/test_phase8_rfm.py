import copy
import tempfile
import unittest
from datetime import datetime,timedelta
from decimal import Decimal
from pathlib import Path
import numpy as np
from sklearn.exceptions import NotFittedError
from src.mining.rfm import REFERENCE,from_orders,split_customers,snapshot_id
from src.mining.preprocess import RFMPreprocessor
from src.mining.train import choose
from src.mining.artifacts import build,validate


def orders():
    return [{'order_id':'O'+str(i),'customer_id':'C'+str(i),'packed_at':datetime(2025,12,1),
             'goods_amount':Decimal('0.10'),'quantity':20,'total_paid':Decimal('999.00')} for i in range(30)]


def synthetic():
    rng=np.random.default_rng(42);rows=[]
    for i in range(120):
        high=i%2==0;r=int(rng.integers(5,30) if high else rng.integers(500,1200))
        rows.append({'customer_id':f'C{i:04}','recency_days':r,'frequency':int(rng.integers(6,12) if high else rng.integers(1,3)),
                     'monetary':Decimal(int(rng.integers(1000000,2000000) if high else rng.integers(10000,50000))),
                     'last_packed_at':datetime(2026,1,1)-timedelta(days=r)})
    return split_customers(rows)


class Phase8RfmTests(unittest.TestCase):
    def test_f_is_orders_m_is_exact_goods_and_r_uses_packed_time(self):
        data=orders()+[dict(orders()[0],order_id='EXTRA',packed_at=datetime(2025,12,20,18),goods_amount=Decimal('0.20'))]
        first=next(r for r in from_orders(data) if r['customer_id']=='C0')
        self.assertEqual((first['frequency'],first['monetary'],first['recency_days']),(2,Decimal('0.30'),12))
    def test_reference_boundary_missing_dates_demo_and_deleted_are_excluded(self):
        extra=[dict(orders()[0],order_id='FUTURE',packed_at=datetime(2026,1,1)),
               dict(orders()[0],order_id='MISSING',packed_at=None),dict(orders()[0],order_id='DEMO',is_demo=True),
               dict(orders()[0],order_id='DELETE',is_deleted=True)]
        self.assertEqual(from_orders(orders()),from_orders(orders()+extra))
    def test_duplicate_order_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'Duplicate order'):from_orders(orders()+[orders()[0]])
    def test_split_is_stable_disjoint_and_independent_of_input_order(self):
        a=from_orders(orders());b=from_orders(list(reversed(orders())))
        self.assertEqual(a,b);self.assertEqual({s:sum(r['split']==s for r in a) for s in ['train','validation','test']},{'train':18,'validation':6,'test':6})
        self.assertEqual(len({r['customer_id'] for r in a}),len(a))
    def test_snapshot_identity_changes_with_features_and_source_lineage(self):
        a=from_orders(orders());b=copy.deepcopy(a);b[0]['monetary']+=Decimal('.01')
        self.assertNotEqual(snapshot_id(a),snapshot_id(b));self.assertNotEqual(snapshot_id(a,'a'),snapshot_id(a,'b'))
    def test_preprocessing_does_not_learn_validation_outlier(self):
        train=np.array([[1,1,10],[5,2,20],[10,3,100]],dtype=float);original=train.copy()
        prep=RFMPreprocessor().fit(train);bounds=prep.upper_.copy();means=prep.scaler_.mean_.copy()
        prep.transform([[100000,100000,1e15]])
        np.testing.assert_array_equal(prep.upper_,bounds);np.testing.assert_array_equal(prep.scaler_.mean_,means)
        np.testing.assert_array_equal(train,original);self.assertEqual(prep.fit_rows_,3)
    def test_unfitted_and_invalid_features_fail(self):
        with self.assertRaises(NotFittedError):RFMPreprocessor().transform([[1,1,1]])
        for data in [[[1,0,10]],[[1,1,float('nan')]],[[1,1]],[[1,1,-1]]]:
            with self.assertRaises(ValueError):RFMPreprocessor().fit(data)
    def test_selection_uses_validation_and_eligibility(self):
        records=[{'k':2,'eligible':True,'validation':{'silhouette':.5,'davies_bouldin':.9}},
                 {'k':3,'eligible':True,'validation':{'silhouette':.4,'davies_bouldin':.8}},
                 {'k':4,'eligible':False,'validation':{'silhouette':.9,'davies_bouldin':.1}}]
        self.assertEqual(choose(records),2)
        with self.assertRaises(RuntimeError):choose([dict(r,eligible=False) for r in records])
    def test_artifact_roundtrip_replay_and_corruption_detection(self):
        rows=synthetic()
        with tempfile.TemporaryDirectory() as folder:
            first=build(snapshot_id(rows),rows,folder)
            second=build(snapshot_id(rows),rows,folder)
            self.assertEqual(first[0],second[0]);self.assertFalse(first[-1]);self.assertTrue(second[-1])
            self.assertFalse(first[3]['test_used_for_selection']);self.assertFalse(first[3]['refit_on_all_customers'])
            path=first[1]/'evaluation.json';path.write_bytes(path.read_bytes()+b' ')
            with self.assertRaisesRegex(RuntimeError,'checksum mismatch'):validate(first[1],first[0])


if __name__=='__main__':unittest.main()
