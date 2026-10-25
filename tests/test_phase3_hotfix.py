import unittest
from src.source.data import FIELDS
from src.source.runtime import identifier, insert_noop


class RecordingCursor:
    def __init__(self):
        self.calls=[]

    def executemany(self, sql, values):
        self.calls.append((sql,values))


class Phase3HotfixTests(unittest.TestCase):
    def test_contract_and_provenance_identifiers_are_accepted(self):
        names=set(FIELDS)
        for fields in FIELDS.values():
            names.update(fields)
        names.update(['import_files','import_rows','file_name','file_sha256',
            'excel_row_number','entity_type','entity_key','sanitized_payload',
            'payload_sha256','redaction_version'])
        for name in names:
            with self.subTest(name=name):
                self.assertEqual(identifier(name),'`'+name+'`')

    def test_invalid_identifiers_are_rejected(self):
        for name in ('','256_field','file-sha256','x.y','x`','x;DROP TABLE orders','x y','file_sha256\n'):
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    identifier(name)

    def test_provenance_insert_binds_payload_instead_of_interpolating_it(self):
        fields=['file_name','file_sha256','excel_row_number','entity_type','entity_key',
                'sanitized_payload','payload_sha256','redaction_version']
        payload='{"note":"quote \' and SQL-looking text; stays data"}'
        row=dict(zip(fields,['fixture.xlsx','a'*64,2,'orders','DH_FIXTURE',payload,'b'*64,'lak-minimal-v1']))
        cursor=RecordingCursor()
        insert_noop(cursor,'import_rows',[row],fields,'file_name')
        self.assertEqual(len(cursor.calls),1)
        sql,values=cursor.calls[0]
        self.assertIn('`file_sha256`',sql)
        self.assertIn('`payload_sha256`',sql)
        self.assertEqual(sql.count('%s'),len(fields))
        self.assertNotIn(payload,sql)
        self.assertEqual(values[0][5],payload)


if __name__=='__main__':
    unittest.main()
