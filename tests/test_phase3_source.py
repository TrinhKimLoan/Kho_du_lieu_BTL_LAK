import json
import unittest
from decimal import Decimal
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.source.data import prepare,FIELDS,PERSONAL_FIELDS,table_digest
from src.source.demo import demo_rows


class Phase3SourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dataset=prepare()

    def test_counts_and_exact_totals(self):
        data=self.dataset
        self.assertEqual([len(data[k]) for k in ('customers','products','orders','import_rows')],[3282,15,10000,43297])
        self.assertEqual(sum(r['goods_amount'] for r in data['orders']),Decimal('618293800000'))
        self.assertEqual(sum(r['total_paid'] for r in data['orders']),Decimal('681261360904'))

    def test_provenance_has_four_rows_for_each_order(self):
        counts={}
        for row in self.dataset['import_rows']:
            if row['entity_type']=='orders':
                counts[row['entity_key']]=counts.get(row['entity_key'],0)+1
        self.assertEqual(len(counts),10000)
        self.assertEqual(set(counts.values()),{4})

    def test_personal_fields_are_removed(self):
        for row in self.dataset['import_rows']:
            self.assertTrue(PERSONAL_FIELDS.isdisjoint(json.loads(row['sanitized_payload'])))
        self.assertNotIn('driver_name',FIELDS['orders'])
        self.assertNotIn('phone',FIELDS['customers'])

    def test_temporal_anomalies_are_preserved(self):
        rows=self.dataset['orders']
        self.assertEqual(sum(r['dispatched_at']<r['packed_at'] for r in rows),880)
        self.assertEqual(sum(r['expected_at']<r['dispatched_at'] for r in rows),118)
        self.assertEqual(sum(r['received_at']<r['dispatched_at'] for r in rows),0)

    def test_digest_matches_mysql_decimal_and_boolean_types(self):
        source=self.dataset['orders'][:2]
        actual=[dict(row,is_demo=0) for row in source]
        for row in actual:
            for key in ('transaction_unit_price','goods_amount','vat_amount','shipping_fee','total_paid'):
                row[key]=row[key].quantize(Decimal('0.01'))
        self.assertEqual(table_digest(source,FIELDS['orders'],'order_id'),table_digest(actual,FIELDS['orders'],'order_id'))
        actual[0]['shipping_fee']+=Decimal('0.01')
        self.assertNotEqual(table_digest(source,FIELDS['orders'],'order_id'),table_digest(actual,FIELDS['orders'],'order_id'))

    def test_demo_is_separate_and_has_no_delivery_target_before_receipt(self):
        customer,product,order=demo_rows()
        for row,key in ((customer,'customer_id'),(product,'product_id'),(order,'order_id')):
            self.assertTrue(row['is_demo'])
            self.assertTrue(row[key].startswith('DEMO_'))
        self.assertIsNone(order['received_at'])
        self.assertEqual(order['total_paid'],order['goods_amount']+order['vat_amount']+order['shipping_fee'])


if __name__=='__main__':
    unittest.main()
