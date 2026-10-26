import json
import tempfile
import unittest
from datetime import datetime,timedelta
from pathlib import Path
from unittest.mock import patch
import numpy as np
from src.delivery.features import construct,identity,matrix,FEATURES
from src.delivery.train import fit,CONFIG,baseline_fit,baseline_predict,scores,estimator
from src.delivery.artifacts import build,load


def source():
    rows=[]
    for year in [2023,2024,2025]:
        for i in range(60):
            start=datetime(year,2,1)+timedelta(days=i)
            rows.append({'order_id':str(year)+'-'+str(i),'dispatched_at':start,'received_at':start+timedelta(hours=24+12*(i%3)),
                'quantity':1+i%4,'goods_amount':1000*(1+i%4),'shipping_method':['FAST','NORMAL','SLOW'][i%3],
                'quantity_band':'SMALL','warehouse_name':'WH1','vehicle_type':'VAN','delivery_district':'D1'})
    return rows


class DeliveryTests(unittest.TestCase):
    def test_chronology_and_label_cutoffs(self):
        data=source();extra=dict(data[0],order_id='cross',dispatched_at=datetime(2023,12,31),received_at=datetime(2024,1,1))
        rows,counts=construct(data+[extra]);self.assertEqual(counts['label_not_available_train'],1)
        self.assertEqual({r['dispatched_at'][:4] for r in rows if r['split']=='test'},{'2025'})
        self.assertEqual(len(rows),180)

    def test_exclusions_and_accounting(self):
        data=source();extras=[dict(data[0],order_id='demo',is_demo=True),dict(data[0],order_id='missing',received_at=None),
                              dict(data[0],order_id='negative',received_at=datetime(2000,1,1))]
        rows,counts=construct(data+extras);self.assertEqual(counts['source_orders']-len(rows),3)
        self.assertEqual(counts['negative_duration'],1)

    def test_duplicate_rejected(self):
        data=source()
        with self.assertRaises(ValueError):construct(data+[data[0]])

    def test_no_future_or_personal_predictors(self):
        data=source();rows,_=construct(data)
        changed=[dict(r,received_at=r['received_at']+timedelta(hours=1),phone='secret',expected_at=datetime(2026,1,1)) for r in data]
        other,_=construct(changed)
        np.testing.assert_array_equal(matrix(rows),matrix(other));self.assertNotEqual(identity(rows),identity(other))
        self.assertEqual(set(rows[0]['features']),set(FEATURES))

    def test_train_only_imputation_and_unknown_category(self):
        rows,_=construct(source());train=[r for r in rows if r['split']=='train']
        train[0]['features']['goods_amount']=None
        model=estimator(3,5).fit(matrix(train),[r['target_hours'] for r in train])
        expected=np.nanmedian(np.array(matrix(train)[:,:5],dtype=float),axis=0)
        np.testing.assert_allclose(model['preprocess'].named_transformers_['numeric'].statistics_,expected)
        unseen=[dict(rows[-1],features=dict(rows[-1]['features'],delivery_district='UNSEEN',warehouse_name=None))]
        self.assertTrue(np.isfinite(model.predict(matrix(unseen))).all())

    def test_baseline_fallback_and_metric_units(self):
        rows,_=construct(source());baseline=baseline_fit(rows[:60]);r=dict(rows[0],features=dict(rows[0]['features'],shipping_method='UNSEEN'))
        self.assertEqual(baseline_predict(baseline,[r])[0],baseline['global_median'])
        self.assertEqual(scores([1,3],[2,5])['mae_hours'],1.5)
        self.assertAlmostEqual(scores([1,3],[2,5])['rmse_hours'],(2.5)**.5)

    def test_test_labels_cannot_change_model_selection(self):
        rows,_=construct(source());changed=[dict(r,target_hours=9999) if r['split']=='test' else r for r in rows]
        with patch.dict(CONFIG,n_estimators=8,permutation_repeats=1):
            m,a,_=fit(rows);n,b,_=fit(changed)
        self.assertEqual(a['selected_candidate'],b['selected_candidate']);self.assertEqual(a['candidates'],b['candidates'])
        np.testing.assert_array_equal(m.predict(matrix(rows)),n.predict(matrix(rows)))
        self.assertFalse(a['test_used_for_selection']);self.assertEqual(a['preprocessing_fit_rows'],60)

    def test_artifact_reload_replay_and_tamper(self):
        rows,_=construct(source());snapshot=identity(rows)
        with tempfile.TemporaryDirectory() as temp,patch.dict(CONFIG,n_estimators=8,permutation_repeats=1):
            a=build(snapshot,rows,Path(temp));self.assertFalse(a[-1]);b=build(snapshot,rows,Path(temp));self.assertTrue(b[-1]);self.assertEqual(a[0],b[0])
            load(a[1],a[0]);(a[1]/'evaluation.json').write_text('{}')
            with self.assertRaises(RuntimeError):load(a[1],a[0])

    def test_validation_and_test_straddles(self):
        data=source()
        for year in [2024,2025]:data.append(dict(data[0],order_id='late'+str(year),dispatched_at=datetime(year,12,31),received_at=datetime(year+1,1,1)))
        _,counts=construct(data)
        self.assertEqual(counts['label_not_available_validation'],1);self.assertEqual(counts['label_not_available_test'],1)

    def test_reject_nonfinite_inputs(self):
        data=source();data[0]['goods_amount']=float('inf')
        with self.assertRaises(ValueError):construct(data)
