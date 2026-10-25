import copy
import unittest
from contextlib import nullcontext
from src.quality.rules import summarize
from src.quality.retry import request_retry,resolve_processed


class Result:
    def __init__(self,row=None,count=1):self.row=row;self.rowcount=count
    def fetchone(self):return self.row


class RetryConnection:
    def __init__(self,state='OPEN',processed=None):
        self.row={'state':state,'processed_at':processed,'attempts':0}
        self.statements=[]
    def transaction(self):return nullcontext()
    def execute(self,sql,params=None):
        self.statements.append(sql)
        if sql.startswith('SELECT'):return Result(copy.deepcopy(self.row))
        if "state='RETRYING'" in sql:
            self.row.update(state='RETRYING',attempts=self.row['attempts']+1)
        elif "state='RESOLVED'" in sql:self.row['state']='RESOLVED'
        else:raise AssertionError('Unexpected mutation')
        return Result()


class Phase5QualityTests(unittest.TestCase):
    def test_known_business_warnings_do_not_fail_gate(self):
        result=summarize({'DISPATCH_BEFORE_PACK':880,'EXPECTED_BEFORE_DISPATCH':118})
        self.assertTrue(result['passed']);self.assertEqual(result['warning_findings'],998)

    def test_one_technical_error_fails_even_with_many_warnings(self):
        result=summarize({'SCD2_OVERLAP':1,'DISPATCH_BEFORE_PACK':880})
        self.assertFalse(result['passed']);self.assertEqual(result['error_findings'],1)

    def test_clean_gate(self):self.assertTrue(summarize({})['passed'])

    def test_retry_is_idempotent_and_preserves_raw_event(self):
        connection=RetryConnection()
        self.assertTrue(request_retry(connection,1)['changed'])
        self.assertFalse(request_retry(connection,1)['changed'])
        self.assertEqual(connection.row['attempts'],1)
        self.assertFalse(any('UPDATE raw.' in s or 'DELETE ' in s for s in connection.statements))

    def test_processed_error_resolves_without_replay(self):
        connection=RetryConnection(processed='2026-10-26')
        self.assertEqual(request_retry(connection,1)['state'],'RESOLVED')
        self.assertEqual(connection.row['attempts'],0)

    def test_resolved_error_is_unchanged(self):
        connection=RetryConnection(state='RESOLVED',processed='done')
        self.assertFalse(request_retry(connection,1)['changed'])
        self.assertEqual(len(connection.statements),1)

    def test_missing_error_is_rejected(self):
        class Missing(RetryConnection):
            def execute(self,*args):return Result()
        with self.assertRaises(ValueError):request_retry(Missing(),123)


if __name__=='__main__':unittest.main()
