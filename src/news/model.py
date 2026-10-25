import hashlib
import json
import re
import unicodedata
from datetime import date,datetime,timezone
from urllib.parse import urlsplit,urlunsplit,parse_qsl,urlencode
from app.relevance import classify
from src.source.data import ROOT

SUSPICIOUS={'lamdongtv.vn'}
RULE_VERSION='lak-title-v1-'+hashlib.sha256((ROOT/'app/relevance.py').read_bytes()).hexdigest()[:12]
TRACKING={'fbclid','gclid','dclid','msclkid','mc_cid','mc_eid'}


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'),default=str).encode()).hexdigest()


def canonical_url(value):
    p=urlsplit(str(value or '').strip())
    if p.scheme.lower() not in ('http','https') or not p.hostname or p.username or p.password:
        raise ValueError('INVALID_URL')
    host=p.hostname.encode('idna').decode('ascii').lower().removeprefix('www.')
    if any(not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?',label) for label in host.split('.')):
        raise ValueError('INVALID_HOST')
    port=p.port
    if port and not ((p.scheme.lower()=='https' and port==443) or (p.scheme.lower()=='http' and port==80)):host+=':'+str(port)
    query=sorted((k,v) for k,v in parse_qsl(p.query,keep_blank_values=True) if not k.lower().startswith('utm_') and k.lower() not in TRACKING)
    # Do not assume http=https, amp=desktop, or that a trailing slash is equivalent.
    return urlunsplit((p.scheme.lower(),host,p.path or '/',urlencode(query),''))


def timestamp(value):
    if not value:return None
    parsed=datetime.fromisoformat(str(value).replace('Z','+00:00'))
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)


def normalize(row):
    if not isinstance(row,dict):raise ValueError('NOT_AN_OBJECT')
    title=unicodedata.normalize('NFC',re.sub(r'\s+',' ',str(row.get('title') or '')).strip())
    if not title:raise ValueError('EMPTY_TITLE')
    url=canonical_url(row.get('url'))
    published=date.fromisoformat(str(row.get('publish_date') or '')[:10])
    domain=urlsplit(url).hostname
    classification=classify(title,domain,SUSPICIOUS)
    # Out-of-scope matches can explain rejection but must not create analysis bridges.
    categories=sorted(set(classification['categories'])) if classification['level'] in ('DIRECT','INDIRECT') else []
    obj={'article_key':hashlib.sha256(url.encode()).hexdigest(),'canonical_url':url,'title':title,
         'source_domain':domain,'published_date':published.isoformat(),'relevance_level':classification['level'],
         'relevance_reason':classification['reason'],'categories':categories,'rule_version':RULE_VERSION,
         'quality_status':'candidate' if classification['level']=='DIRECT' else 'review'}
    obj['content_hash']=digest(obj)
    obj['external_id']=str(row.get('id') or '')
    obj['indexed_at']=timestamp(row.get('indexed_date'))
    return obj


def change_type(previous_hash,current_hash):
    return 'NEW' if previous_hash is None else 'UNCHANGED' if previous_hash==current_hash else 'UPDATED'


def normalize_page(rows):
    unique={};invalid=[];duplicates=0
    for number,row in enumerate(rows,1):
        try:obj=normalize(row)
        except (ValueError,TypeError,OverflowError,UnicodeError):
            invalid.append(number);continue
        old=unique.get(obj['article_key'])
        if old:
            if old['content_hash']!=obj['content_hash']:raise ValueError('Conflicting article payloads in one page')
            duplicates+=1
        unique[obj['article_key']]=obj
    return list(unique.values()),invalid,duplicates
