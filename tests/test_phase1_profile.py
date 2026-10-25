import importlib.util
import unittest
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('phase1_profile', ROOT / 'scripts/profile_lak_data.py')
profile = importlib.util.module_from_spec(spec)
spec.loader.exec_module(profile)


class Phase1ProfileTests(unittest.TestCase):
    def test_currency_uses_exact_decimal_arithmetic(self):
        self.assertEqual(profile.decimal('0.1') + profile.decimal('0.2'), Decimal('0.3'))
        with self.assertRaises(ValueError):
            profile.decimal('NaN')

    def test_excel_clock_combines_with_date_at_second_precision(self):
        serial = (date(2024, 1, 1) - date(1899, 12, 30)).days
        result = profile.stamp({'d': serial, 't': 45296 / 86400}, 'd', 't')
        self.assertEqual(result, datetime(2024, 1, 1, 12, 34, 56))
        with self.assertRaises(ValueError):
            profile.stamp({'d': serial, 't': 1.5}, 'd', 't')

    def test_duplicate_order_is_rejected_before_dictionary_join(self):
        original = profile.xlsx_rows

        def read(path):
            rows = original(path)
            return rows + [dict(rows[0])] if path.name.startswith('01') else rows

        with patch.object(profile, 'xlsx_rows', side_effect=read):
            result = profile.analyze(ROOT / 'data')
        self.assertFalse(result['passed'])
        self.assertEqual(result['hard_errors']['01_duplicate_keys'], 1)

    def test_missing_shipping_row_is_rejected(self):
        original = profile.xlsx_rows

        def read(path):
            rows = original(path)
            return rows[1:] if path.name.startswith('06') else rows

        with patch.object(profile, 'xlsx_rows', side_effect=read):
            result = profile.analyze(ROOT / 'data')
        self.assertFalse(result['passed'])
        self.assertEqual(result['hard_errors']['06_order_key_set_difference'], 1)

    def test_wrong_total_is_detected_without_changing_source(self):
        original = profile.xlsx_rows

        def read(path):
            rows = original(path)
            if path.name.startswith('05'):
                rows[0]['Tong_Thanh_Toan'] += 1
            return rows

        with patch.object(profile, 'xlsx_rows', side_effect=read):
            result = profile.analyze(ROOT / 'data')
        self.assertFalse(result['passed'])
        self.assertEqual(result['hard_errors']['total_formula_mismatch'], 1)
        self.assertEqual(result['hard_errors']['customer_total_paid_mismatch'], 1)


if __name__ == '__main__':
    unittest.main()
