import json
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from src.source.data import canonical, fingerprint, json_text


class Phase4UuidTests(unittest.TestCase):
    epoch = UUID('13168923-bbb9-4cac-ac2b-9af01a53c892')

    def test_uuid_has_standard_text_representation(self):
        self.assertEqual(canonical(self.epoch), str(self.epoch))

    def test_nested_postgres_fact_state_is_serializable(self):
        state = [{'order_id': 'DH001', 'source_epoch': self.epoch,
                  'total_paid': Decimal('335000.00'),
                  'projected_at': datetime(2026, 10, 25, 17, 44, 59, tzinfo=timezone.utc),
                  'is_demo': False, 'received_at': None}]
        decoded = json.loads(json_text(state))[0]
        self.assertEqual(decoded['source_epoch'], str(self.epoch))
        self.assertEqual(decoded['total_paid'], '335000.00')
        self.assertEqual(decoded['projected_at'], '2026-10-25T17:44:59.000000+00:00')
        self.assertEqual(decoded['is_demo'], 0)
        self.assertIsNone(decoded['received_at'])

    def test_roundtrip_uuid_does_not_change_fingerprint(self):
        original = [{'source_epoch': self.epoch}]
        roundtrip = json.loads(json_text(original))
        self.assertEqual(fingerprint(original), fingerprint(roundtrip))

    def test_changed_uuid_changes_fingerprint(self):
        self.assertNotEqual(fingerprint({'source_epoch': self.epoch}),
                            fingerprint({'source_epoch': UUID(int=1)}))

    def test_unknown_types_are_still_rejected(self):
        with self.assertRaises(TypeError):
            json_text({'value': object()})


if __name__ == '__main__':
    unittest.main()
