import json
import os
import time
from urllib.request import Request,urlopen
from urllib.parse import urlencode
from urllib.error import HTTPError,URLError

ENDPOINT='https://search.mediacloud.org/api/search/story-list'


class MediaCloud:
    def __init__(self,key=None,delay=32):
        self.key=key or os.environ.get('MEDIACLOUD_API_KEY','').strip()
        if not self.key:raise RuntimeError('MEDIACLOUD_API_KEY is missing; stored-data validation is separate from live API validation')
        self.delay=max(32,float(delay));self.last_request=None
    def __call__(self,query,start,end,collection_id,page_size,token):
        params={'q':query,'start':start.isoformat(),'end':end.isoformat(),'cs':str(collection_id),
                'platform':'onlinenews-mediacloud','page_size':page_size}
        if token:params['pagination_token']=token
        for attempt in range(3):
            if self.last_request is not None:time.sleep(max(0,self.delay-(time.monotonic()-self.last_request)))
            self.last_request=time.monotonic()
            request=Request(ENDPOINT+'?'+urlencode(params),headers={'Authorization':'Token '+self.key,'Accept':'application/json','User-Agent':'LAK-Analytics/phase6'})
            try:
                with urlopen(request,timeout=60) as response:body=json.load(response)
                if not isinstance(body,dict):raise ValueError('MediaCloud response is not an object')
                return body
            except HTTPError as exc:
                if exc.code not in (429,500,502,503,504) or attempt==2:
                    raise RuntimeError('MediaCloud HTTP '+str(exc.code)+'; response body and credential omitted') from None
                try:retry=min(60,max(1,int(exc.headers.get('Retry-After','32'))))
                except ValueError:retry=32
                time.sleep(retry)
            except URLError:
                if attempt==2:raise RuntimeError('MediaCloud network connection failed after retries') from None
            except (ValueError,UnicodeError):raise RuntimeError('MediaCloud returned invalid JSON') from None
        raise RuntimeError('MediaCloud request exhausted retries')


def pages(fetch,query,start,end,collection_id=34412246,page_size=100,max_pages=2):
    if not 1<=page_size<=100 or max_pages<1:raise ValueError('page_size must be 1..100 and max_pages >=1')
    token=None;seen=set()
    for number in range(1,max_pages+1):
        body=fetch(query,start,end,collection_id,page_size,token)
        if not isinstance(body,dict) or not isinstance(body.get('stories'),list) or 'pagination_token' not in body:
            raise ValueError('Invalid MediaCloud pagination response')
        next_token=body['pagination_token']
        if next_token is not None and not isinstance(next_token,str):raise ValueError('Invalid pagination token type')
        loop=bool(next_token and (next_token==token or next_token in seen))
        exhausted=not next_token
        yield number,body,('COMPLETE' if exhausted else 'PARTIAL'),('TOKEN_LOOP' if loop else 'PAGE_CAP' if number==max_pages and next_token else None)
        if loop:raise ValueError('MediaCloud pagination token loop')
        if exhausted:return
        seen.add(next_token);token=next_token
