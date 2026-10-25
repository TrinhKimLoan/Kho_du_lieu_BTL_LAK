import unittest
import io
import json
from unittest.mock import patch
from urllib.error import HTTPError
from email.message import Message
from datetime import date
from src.news.model import normalize,canonical_url,change_type,normalize_page
from src.news.api import pages,MediaCloud


def article(**kwargs):
    return dict({'id':'a','title':'Giá RAM DDR5 và SSD NVMe giảm mạnh','url':'https://www.example.com/a?utm_source=x&b=2&a=1#top',
                 'publish_date':'2024-12-10','indexed_date':'2024-12-11T00:00:00Z'},**kwargs)


class Phase6NewsTests(unittest.TestCase):
    def test_tracking_fragment_and_query_order_merge(self):
        self.assertEqual(normalize(article())['article_key'],normalize(article(url='https://example.com/a?a=1&b=2&fbclid=xx'))['article_key'])
    def test_identity_query_parameter_is_retained(self):
        self.assertNotEqual(normalize(article(url='https://example.com/?id=1'))['article_key'],normalize(article(url='https://example.com/?id=2'))['article_key'])
    def test_http_and_trailing_slash_are_not_assumed_equivalent(self):
        self.assertNotEqual(canonical_url('http://example.com/a'),canonical_url('https://example.com/a'))
        self.assertNotEqual(canonical_url('https://example.com/a'),canonical_url('https://example.com/a/'))
    def test_url_credentials_and_unsafe_schemes_are_rejected(self):
        for url in ['javascript:alert(1)','file:///a','https://user:secret@example.com/','https://ex ample.com/a']:
            with self.assertRaises(ValueError):normalize(article(url=url))
    def test_collected_metadata_does_not_change_content_hash(self):
        self.assertEqual(normalize(article())['content_hash'],normalize(article(id='different',indexed_date='2025-01-01T00:00:00Z'))['content_hash'])
    def test_title_change_keeps_key_and_changes_content_hash(self):
        before=normalize(article());after=normalize(article(title='Giá RTX 5070 tăng mạnh'))
        self.assertEqual(before['article_key'],after['article_key']);self.assertNotEqual(before['content_hash'],after['content_hash'])
    def test_multiple_categories_are_unique(self):self.assertEqual(normalize(article())['categories'],['RAM','SSD'])
    def test_out_of_scope_matches_do_not_create_bridges(self):
        obj=normalize(article(title='Điện thoại Galaxy A07 có GPU mạnh'))
        self.assertEqual(obj['relevance_level'],'IRRELEVANT');self.assertEqual(obj['categories'],[])
    def test_missing_or_bad_date_is_rejected(self):
        for stamp in ['',None,'2024-02-30']:
            with self.assertRaises(ValueError):normalize(article(publish_date=stamp))
    def test_change_classification(self):
        self.assertEqual(change_type(None,'x'),'NEW');self.assertEqual(change_type('x','x'),'UNCHANGED');self.assertEqual(change_type('x','y'),'UPDATED')
    def test_duplicate_and_invalid_rows_are_counted(self):
        good,bad,duplicates=normalize_page([article(),article(),{'title':''}])
        self.assertEqual((len(good),bad,duplicates),(1,[3],1))
    def test_conflicting_page_duplicates_fail(self):
        with self.assertRaises(ValueError):normalize_page([article(),article(title='Giá CPU Ryzen tăng')])
    def test_pagination_uses_next_token_and_detects_exhaustion(self):
        calls=[]
        def fetch(*args):
            calls.append(args[-1]);return {'stories':[article()],'pagination_token':'next' if len(calls)==1 else None}
        result=list(pages(fetch,'RAM',date(2024,12,1),date(2024,12,31)))
        self.assertEqual(calls,[None,'next']);self.assertEqual(result[-1][2],'COMPLETE')
    def test_cap_remains_partial(self):
        result=list(pages(lambda *a:{'stories':[],'pagination_token':'next'},'RAM',date(2024,12,1),date(2024,12,31),max_pages=1))
        self.assertEqual(result[0][2:],('PARTIAL','PAGE_CAP'))
    def test_token_loop_fails(self):
        with self.assertRaises(ValueError):list(pages(lambda *a:{'stories':[],'pagination_token':'same'},'RAM',date(2024,12,1),date(2024,12,31),max_pages=4))
    def test_missing_pagination_metadata_fails(self):
        with self.assertRaises(ValueError):list(pages(lambda *a:{'stories':[]},'RAM',date(2024,12,1),date(2024,12,31)))
    def test_api_failure_is_not_empty_complete_result(self):
        def fetch(*args):raise RuntimeError('network unavailable')
        with self.assertRaises(RuntimeError):list(pages(fetch,'RAM',date(2024,12,1),date(2024,12,31)))

    def test_http_adapter_uses_header_auth_and_official_parameters(self):
        calls=[]
        def open_request(request,timeout):
            calls.append(request)
            return io.BytesIO(json.dumps({'stories':[],'pagination_token':None}).encode())
        with patch('src.news.api.urlopen',side_effect=open_request):
            result=MediaCloud('DUMMY_TEST_TOKEN')('RAM',date(2024,12,1),date(2024,12,31),34412246,100,None)
        self.assertEqual(result['stories'],[])
        self.assertEqual(calls[0].get_header('Authorization'),'Token DUMMY_TEST_TOKEN')
        self.assertIn('cs=34412246',calls[0].full_url)
        self.assertIn('platform=onlinenews-mediacloud',calls[0].full_url)
        self.assertNotIn('DUMMY_TEST_TOKEN',calls[0].full_url)

    def test_http_401_error_omits_body_and_secret(self):
        error=HTTPError('https://search.mediacloud.org',401,'Unauthorized',Message(),None)
        with patch('src.news.api.urlopen',side_effect=error):
            with self.assertRaisesRegex(RuntimeError,'HTTP 401') as context:
                MediaCloud('DUMMY_TEST_TOKEN')('RAM',date(2024,12,1),date(2024,12,31),1,10,None)
        self.assertNotIn('DUMMY_TEST_TOKEN',str(context.exception))

    def test_http_429_retries_then_succeeds(self):
        headers=Message();headers['Retry-After']='1'
        error=HTTPError('https://search.mediacloud.org',429,'rate limit',headers,None)
        response=io.BytesIO(b'{"stories":[],"pagination_token":null}')
        with patch('src.news.api.urlopen',side_effect=[error,response]) as opener,patch('src.news.api.time.sleep'):
            MediaCloud('DUMMY_TEST_TOKEN')('RAM',date(2024,12,1),date(2024,12,31),1,10,None)
        self.assertEqual(opener.call_count,2)

    def test_bad_json_response_fails(self):
        with patch('src.news.api.urlopen',return_value=io.BytesIO(b'not-json')):
            with self.assertRaisesRegex(RuntimeError,'invalid JSON'):
                MediaCloud('DUMMY_TEST_TOKEN')('RAM',date(2024,12,1),date(2024,12,31),1,10,None)


if __name__=='__main__':unittest.main()
