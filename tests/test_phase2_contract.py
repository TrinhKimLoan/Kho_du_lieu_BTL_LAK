import copy
import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('phase2_contract', ROOT / 'scripts/verify_phase2.py')
design = importlib.util.module_from_spec(spec)
spec.loader.exec_module(design)


class Phase2ContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = json.loads((ROOT / 'docs/phase2/data_contract.json').read_text(encoding='utf-8'))
        cls.sql = (ROOT / 'sql/phase2/001_warehouse_schema.sql').read_text(encoding='utf-8')

    def test_contract_and_schema_agree(self):
        errors, count = design.inspect_design(self.contract, self.sql)
        self.assertEqual(errors, [])
        self.assertGreater(count, 15)

    def test_wrong_customer_foreign_key_is_detected(self):
        contract = copy.deepcopy(self.contract)
        contract['facts']['dw.fact_sales']['foreign_keys']['customer_key'] = 'dw.dim_product.product_key'
        errors, _ = design.inspect_design(contract, self.sql)
        self.assertTrue(any('FK differs' in error for error in errors))

    def test_demo_leak_into_analysis_view_is_detected(self):
        sql = self.sql.replace('WHERE NOT is_deleted AND NOT is_demo', 'WHERE NOT is_deleted', 1)
        errors, _ = design.inspect_design(self.contract, sql)
        self.assertTrue(any('exclude deleted/demo' in error for error in errors))

    def test_missing_source_field_in_staging_is_detected(self):
        contract = copy.deepcopy(self.contract)
        contract['source_entities']['orders']['fields'].append('missing_dispatch_feature')
        errors, _ = design.inspect_design(contract, self.sql)
        self.assertTrue(any('missing_dispatch_feature' in error for error in errors))


if __name__ == '__main__':
    unittest.main()
