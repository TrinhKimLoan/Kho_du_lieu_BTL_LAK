import copy
import json
import math
import unittest
from src.source.data import fingerprint,json_text,provenance_payload
from src.source.runtime import validate_provenance


def fixture():
    payload=provenance_payload({'Ma_Don':'DH_TEST','Gio_Nhan_Hang':0.6616203703703704,'So_Luong':4})
    row={'file_name':'04_thoi_gian_giao_hang.xlsx','excel_row_number':2,'entity_type':'orders',
         'entity_key':'DH_TEST','sanitized_payload':json_text(payload),'payload_sha256':fingerprint(payload),
         'redaction_version':'lak-minimal-v2-float-repr'}
    return row


class Phase3JsonHotfixTests(unittest.TestCase):
    def test_excel_float_is_preserved_as_exact_tagged_text(self):
        value=0.6616203703703704
        encoded=provenance_payload({'clock':value,'quantity':4})
        self.assertEqual(encoded['clock'],{'__lak_type__':'excel_float_repr','value':repr(value)})
        self.assertEqual(float(encoded['clock']['value']),value)
        self.assertIsInstance(encoded['quantity'],int)
        self.assertNotEqual(fingerprint(provenance_payload(value)),fingerprint(repr(value)))

    def test_json_key_order_and_unicode_escape_do_not_change_hash(self):
        target=fixture()
        actual=copy.deepcopy(target)
        actual['sanitized_payload']=json.dumps(json.loads(target['sanitized_payload']),sort_keys=False,indent=2,ensure_ascii=True)
        validate_provenance(actual,target)

    def test_changed_clock_is_detected_without_tolerance(self):
        target=fixture();actual=copy.deepcopy(target)
        payload=json.loads(actual['sanitized_payload'])
        payload['Gio_Nhan_Hang']['value']='0.6616203703703705'
        actual['sanitized_payload']=json.dumps(payload)
        with self.assertRaisesRegex(RuntimeError,'differing_columns=Gio_Nhan_Hang'):
            validate_provenance(actual,target)

    def test_changed_stored_hash_is_detected(self):
        target=fixture();actual=copy.deepcopy(target)
        actual['payload_sha256']='0'*64
        with self.assertRaisesRegex(RuntimeError,'stored_hash_differs_from_input'):
            validate_provenance(actual,target)

    def test_nonfinite_numbers_are_rejected(self):
        for value in (math.nan,math.inf,-math.inf):
            with self.assertRaises(ValueError):
                provenance_payload(value)


if __name__=='__main__':
    unittest.main()
