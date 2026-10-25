import csv
import hashlib
import json
import uuid
from datetime import date,datetime,timezone
from src.source.data import ROOT
from src.cdc.project import category,date_key
from .model import normalize,digest,change_type


def migrate(connection):
    if not connection.execute("SELECT 1 FROM audit.schema_versions WHERE version='lak-phase5-v1'").fetchone():raise RuntimeError('Phase 5 warehouse is required')
    sql=(ROOT/'sql/phase6/001_news_pipeline.sql').read_text()
    sha=hashlib.sha256(sql.encode()).hexdigest()
    with connection.transaction():
        connection.execute('CREATE TABLE IF NOT EXISTS audit.news_pipeline_identity(singleton boolean PRIMARY KEY DEFAULT true CHECK(singleton),ddl_sha256 text NOT NULL)')
        old=connection.execute('SELECT ddl_sha256 FROM audit.news_pipeline_identity WHERE singleton').fetchone()
        if old and old['ddl_sha256']!=sha:raise RuntimeError('News DDL fingerprint changed; migration review is required')
        connection.execute(sql,prepare=False)
        connection.execute('INSERT INTO audit.news_pipeline_identity VALUES(true,%s) ON CONFLICT(singleton) DO NOTHING',(sha,))


def begin_run(connection,origin,details=None):
    from psycopg.types.json import Jsonb
    run_id=uuid.uuid4()
    connection.execute("INSERT INTO audit.pipeline_runs(run_id,pipeline,status,details) VALUES(%s,%s,'RUNNING',%s)",(run_id,'phase6-news-'+origin,Jsonb(details or {})))
    return run_id


def finish_run(connection,run_id,status,details):
    from psycopg.types.json import Jsonb
    connection.execute('UPDATE audit.pipeline_runs SET status=%s,finished_at=now(),details=%s WHERE run_id=%s',(status,Jsonb(details),run_id))


def project(connection,obj,origin,first_seen,seen):
    domain=obj['source_domain']
    connection.execute('INSERT INTO dw.dim_news_source(domain,display_name) VALUES(%s,%s) ON CONFLICT(domain) DO NOTHING',(domain,domain))
    source_key=connection.execute('SELECT news_source_key FROM dw.dim_news_source WHERE domain=%s',(domain,)).fetchone()['news_source_key']
    key=date_key(connection,datetime.fromisoformat(obj['published_date']))
    result={k:obj[k] for k in ('article_key','title','canonical_url','relevance_level','relevance_reason','quality_status','rule_version')}
    result.update(published_date_key=key,news_source_key=source_key,origin=origin,is_demo=origin=='demo',is_deleted=False,
                  first_seen_at=first_seen,last_seen_at=seen,projected_at=seen)
    fields=list(result)
    news_key=connection.execute('INSERT INTO dw.fact_news('+','.join(fields)+') VALUES('+','.join(['%s']*len(fields))+') ON CONFLICT(article_key) DO UPDATE SET '+','.join(k+'=excluded.'+k for k in fields if k not in ('article_key','first_seen_at'))+' RETURNING news_key',tuple(result.values())).fetchone()['news_key']
    connection.execute('DELETE FROM dw.bridge_news_category WHERE news_key=%s',(news_key,))
    for code in obj['categories']:
        connection.execute('INSERT INTO dw.bridge_news_category(news_key,category_key) VALUES(%s,%s)',(news_key,category(connection,code)))


def ingest_page(connection,run_id,group,number,payload,origin,parameters):
    from psycopg.types.json import Jsonb
    if origin not in ('seed','api','demo'):raise ValueError('Unknown news origin')
    rows=payload['stories']
    if not isinstance(rows,list):raise ValueError('Stories must be a list')
    with connection.transaction():
        page_id=connection.execute('''INSERT INTO raw.news_pages(run_id,query_group,page_number,origin,request_parameters,payload,payload_sha256)
            VALUES(%s,%s,%s,%s,%s,%s,%s) RETURNING page_id''',(run_id,group,number,origin,Jsonb(parameters),Jsonb(payload),digest(payload))).fetchone()['page_id']
    stats={k:0 for k in ('NEW','UPDATED','UNCHANGED','SKIPPED_SEED','INVALID','DUPLICATES')}
    try:
        with connection.transaction():
            seen=datetime.now(timezone.utc);page_seen={}
            for index,row in enumerate(rows,1):
                obj=None;error=None
                try:obj=normalize(row)
                except (ValueError,TypeError,OverflowError,UnicodeError):error='INVALID_TITLE_URL_OR_DATE'
                snapshot=connection.execute('''INSERT INTO raw.news_observations(page_id,row_number,article_key,payload,content_hash,validation_error)
                    VALUES(%s,%s,%s,%s,%s,%s) RETURNING snapshot_id''',(page_id,index,obj['article_key'] if obj else None,Jsonb(row),obj['content_hash'] if obj else None,error)).fetchone()['snapshot_id']
                if not obj:stats['INVALID']+=1;continue
                connection.execute('''INSERT INTO raw.news_snapshots(run_id,article_key,origin,payload,content_sha256)
                    VALUES(%s,%s,%s,%s,%s) ON CONFLICT(run_id,article_key) DO NOTHING''',
                    (run_id,obj['article_key'],origin,Jsonb(row),obj['content_hash']))
                if obj['article_key'] in page_seen:
                    if page_seen[obj['article_key']]!=obj['content_hash']:raise ValueError('Conflicting payloads for same article in one page')
                    stats['DUPLICATES']+=1
                page_seen[obj['article_key']]=obj['content_hash']
                if origin=='demo' and not obj['source_domain'].endswith('.invalid'):raise ValueError('Demo news must use a reserved .invalid domain')
                old=connection.execute('SELECT * FROM staging.news_articles WHERE article_key=%s FOR UPDATE',(obj['article_key'],)).fetchone()
                if old and old['is_demo']!=(origin=='demo'):raise ValueError('Demo/real article identity collision')
                change=change_type(old['content_sha256'] if old else None,obj['content_hash'])
                if old and old['origin']=='api' and origin=='seed':change='SKIPPED_SEED'
                stats[change]+=1
                connection.execute('''INSERT INTO audit.news_changes(run_id,snapshot_id,article_key,change_type,previous_hash,current_hash)
                    VALUES(%s,%s,%s,%s,%s,%s)''',(run_id,snapshot,obj['article_key'],change,old['content_sha256'] if old else None,obj['content_hash']))
                if change=='SKIPPED_SEED':continue
                first_seen=old['first_seen_at'] if old else seen
                entity={k:obj[k] for k in ('article_key','external_id','title','canonical_url','source_domain','indexed_at','relevance_level','relevance_reason','quality_status','rule_version')}
                entity.update(content_sha256=obj['content_hash'],published_date=date.fromisoformat(obj['published_date']),category_codes=obj['categories'],origin=origin,is_demo=origin=='demo',first_seen_at=first_seen,last_seen_at=seen,last_snapshot_id=snapshot)
                fields=list(entity)
                connection.execute('INSERT INTO staging.news_articles('+','.join(fields)+') VALUES('+','.join(['%s']*len(fields))+') ON CONFLICT(article_key) DO UPDATE SET '+','.join(k+'=excluded.'+k for k in fields if k not in ('article_key','first_seen_at')),tuple(entity.values()))
                project(connection,obj,origin,first_seen,seen)
            connection.execute('UPDATE raw.news_pages SET processed_at=now() WHERE page_id=%s',(page_id,))
    except Exception as exc:
        connection.execute('UPDATE raw.news_pages SET processing_error=%s WHERE page_id=%s',(type(exc).__name__,page_id))
        raise
    return stats


def seed(connection):
    path=ROOT/'data/news_seed/media_api_2024.csv'
    with path.open(encoding='utf-8-sig',newline='') as source:rows=list(csv.DictReader(source))
    run_id=begin_run(connection,'seed',{'file':path.name,'file_sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
    try:
        stats=ingest_page(connection,run_id,'stored-csv',1,{'stories':rows,'pagination_token':None},'seed',{'file':path.name,'completeness':'unknown; imported CSV is not exhaustive API coverage'})
        dates=[date.fromisoformat(str(r['publish_date'])[:10]) for r in rows if r.get('publish_date')]
        from psycopg.types.json import Jsonb
        # Stored observations do not establish which keyword queries/pages were exhausted.
        signature=digest({'origin':'seed','sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
        for month in sorted({d.replace(day=1) for d in dates}):
            for group in ('GPU','CPU','SSD','HDD','RAM','NETWORK','MONITOR','MOTHERBOARD','PERIPHERAL','CAMERA','PSU'):
                connection.execute('''INSERT INTO audit.news_coverage(month_start,category_key,query_signature,origin,status,observed_at,details)
                    VALUES(%s,%s,%s,'seed','PARTIAL',now(),%s) ON CONFLICT(month_start,category_key,query_signature,origin)
                    DO UPDATE SET observed_at=excluded.observed_at,details=excluded.details''',(month,category(connection,group),signature,Jsonb({'run_id':str(run_id),'reason':'CSV coverage not established'})))
        finish_run(connection,run_id,'PARTIAL',dict(stats,coverage='PARTIAL',live_api=False))
        return dict(stats,run_id=str(run_id),rows=len(rows),coverage='PARTIAL',live_api=False)
    except Exception as exc:
        finish_run(connection,run_id,'FAILED',{'error_type':type(exc).__name__});raise
