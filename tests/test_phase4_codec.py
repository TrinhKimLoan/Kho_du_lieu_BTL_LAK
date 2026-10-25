import copy
import json
import unittest
from datetime import datetime
from decimal import Decimal
from src.cdc.codec import decode,typed_values,bytes_hash,version,expected_count,assemble,TX_TOPIC
from src.source.demo import demo_rows


def event(operation='c',order=1):
    row=demo_rows('FIXTURE')[2]
    encoded={k:format(v,'f') if isinstance(v,Decimal) else int((v-datetime(1970,1,1)).total_seconds()*1000) if isinstance(v,datetime) else v for k,v in row.items()}
    body={'op':operation,'before':encoded if operation=='d' else None,'after':None if operation=='d' else encoded,
          'source':{'db':'lak_source','table':'orders','file':'lak-bin.000010','pos':600,'row':0},
          'transaction':{'id':'TX-1','total_order':order}}
    decoded=decode('lakanalytics.lak_source.orders',0,12,json.dumps({'order_id':row['order_id']}).encode(),json.dumps(body).encode())
    return decoded


class Phase4CodecTests(unittest.TestCase):
    def test_money_stays_exact_decimal(self):
        values=typed_values(event())
        self.assertEqual(values['total_paid'],Decimal('225000.00'))
        self.assertIsInstance(values['transaction_unit_price'],Decimal)

    def test_datetime_milliseconds_and_unreceived_null(self):
        values=typed_values(event())
        self.assertEqual(values['dispatched_at'],datetime(2025,12,21,9))
        self.assertIsNone(values['received_at'])

    def test_delete_uses_full_before_image(self):
        values=typed_values(event('d'))
        self.assertEqual(values['quantity'],2)

    def test_floating_point_money_is_rejected(self):
        row=event();row['record_value']['after']['goods_amount']=200000.0
        with self.assertRaises(ValueError):typed_values(row)

    def test_bad_money_formula_is_rejected(self):
        row=event();row['record_value']['after']['total_paid']='1.00'
        with self.assertRaises(ValueError):typed_values(row)

    def test_wrong_datetime_precision_is_rejected(self):
        row=event();row['record_value']['after']['dispatched_at']*=1000
        with self.assertRaises((ValueError,OverflowError)):typed_values(row)

    def test_missing_transaction_is_invalid_in_streaming(self):
        original=event();body=original['record_value'];body['transaction']=None
        row=decode(original['topic'],0,12,original['key_bytes'],json.dumps(body).encode())
        self.assertEqual(row['event_type'],'invalid')

    def test_snapshot_does_not_require_transaction_metadata(self):
        original=event();body=original['record_value'];body['op']='r';body['transaction']=None
        row=decode(original['topic'],0,12,original['key_bytes'],json.dumps(body).encode())
        self.assertEqual(row['event_type'],'r')

    def test_tombstone_and_empty_bytes_have_different_hashes(self):
        self.assertNotEqual(bytes_hash(None,None),bytes_hash(b'',None))
        self.assertNotEqual(bytes_hash(b'{}',None),bytes_hash(b'{}',b'null'))
        self.assertEqual(decode('lakanalytics.lak_source.orders',0,10,b'{}',None)['event_type'],'tombstone')

    def test_invalid_json_remains_raw_and_marked_invalid(self):
        row=decode('lakanalytics.lak_source.orders',0,10,b'{}',b'{broken')
        self.assertEqual(row['event_type'],'invalid')
        self.assertEqual(row['value_bytes'],b'{broken')

    def test_numeric_binlog_version_order(self):
        first=event();last=event();last['source_file_number']=11;last['source_position']=1
        self.assertLess(version(first),version(last))

    def test_end_counts_only_selected_source_collections(self):
        end={'record_value':{'event_count':20,'data_collections':[{'data_collection':'lak_source.orders','event_count':1},{'data_collection':'lak_source.import_rows','event_count':19}]}}
        self.assertEqual(expected_count(end),1)

    def test_incomplete_transaction_waits(self):
        self.assertIsNone(assemble([event()],2))

    def test_transaction_data_order_and_exact_duplicate(self):
        one,two=event(order=1),event(order=2)
        self.assertEqual([e['tx_total_order'] for e in assemble([two,one,copy.deepcopy(one)],2)],[1,2])

    def test_conflicting_transaction_duplicate_is_rejected(self):
        one,two=event(),event()
        two['record_value']['after']['shipping_fee']='5001.00'
        two['record_value']['after']['total_paid']='225001.00'
        with self.assertRaises(ValueError):assemble([one,two],1)

    def test_reemitted_transaction_ignores_only_processing_timestamp(self):
        one,two=event(),event()
        two['record_value']['ts_ms']=999999
        two['content_sha256']='0'*64
        self.assertEqual(len(assemble([one,two],1)),1)

    def test_transaction_metadata_partition_is_checked(self):
        row=decode(TX_TOPIC,1,0,None,json.dumps({'status':'END','id':'TX-1','event_count':0}).encode())
        self.assertEqual(row['event_type'],'invalid')


if __name__=='__main__':
    unittest.main()
