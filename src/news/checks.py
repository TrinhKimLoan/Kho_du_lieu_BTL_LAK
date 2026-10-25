import csv
import json
import uuid
from datetime import date
from decimal import Decimal
from src.source.data import ROOT,prepare
from src.cdc.checks import history,wait_idle
from src.cdc.store import epoch
from .model import normalize,digest
from .store import seed,begin_run,finish_run,ingest_page
from .fetch import prepare_coverage
from .report import report


def content_state(connection):
    return digest(connection.execute('''SELECT n.article_key,n.title,n.canonical_url,n.published_date_key,n.news_source_key,
        n.relevance_level,n.relevance_reason,n.rule_version,n.origin,n.is_demo,n.is_deleted,
        coalesce((SELECT array_agg(c.category_code ORDER BY c.category_code) FROM dw.bridge_news_category b
          JOIN dw.dim_category c USING(category_key) WHERE b.news_key=n.news_key),'{}') categories
        FROM dw.v_news_analysis n ORDER BY n.article_key''').fetchall())


def fixtures(connection):
    token=uuid.uuid4().hex
    base={'id':'fixture','title':'Giá RAM DDR5 và SSD NVMe giảm mạnh','url':'https://news-'+token+'.invalid/article',
          'publish_date':'2024-12-10','indexed_date':'2024-12-11T00:00:00Z'}
    with connection.transaction(force_rollback=True):
        run=begin_run(connection,'demo')
        a=ingest_page(connection,run,'fixture',1,{'stories':[base],'pagination_token':None},'demo',{})
        b=ingest_page(connection,run,'fixture',2,{'stories':[dict(base,indexed_date='2024-12-12T00:00:00Z')],'pagination_token':None},'demo',{})
        c=ingest_page(connection,run,'fixture',3,{'stories':[dict(base,title='Giá GPU RTX 5070 giảm mạnh')],'pagination_token':None},'demo',{})
        # Absent from a later page is an observation, not a delete instruction.
        ingest_page(connection,run,'fixture',4,{'stories':[],'pagination_token':None},'demo',{})
        row=connection.execute('SELECT * FROM dw.fact_news WHERE article_key=%s',(normalize(base)['article_key'],)).fetchone()
        cats=connection.execute('SELECT c.category_code FROM dw.bridge_news_category b JOIN dw.dim_category c USING(category_key) WHERE news_key=%s',(row['news_key'],)).fetchall()
        if (a['NEW'],b['UNCHANGED'],c['UPDATED'])!=(1,1,1):raise RuntimeError('News change classification did not match NEW/UNCHANGED/UPDATED')
        if row['is_deleted'] or sorted(x['category_code'] for x in cats)!=['GPU']:raise RuntimeError('News absence/bridge replacement policy failed')
        if connection.execute('SELECT 1 FROM dw.v_news_analysis WHERE news_key=%s',(row['news_key'],)).fetchone():raise RuntimeError('Demo leaked into news analysis')
        bad=ingest_page(connection,run,'fixture',5,{'stories':[{'title':'bad','url':'javascript:bad','publish_date':'2024-12-10'}],'pagination_token':None},'demo',{})
        if bad['INVALID']!=1:raise RuntimeError('Invalid news was not quarantined')
        finish_run(connection,run,'SUCCESS',{'fixture':True})
    if connection.execute('SELECT 1 FROM staging.news_articles WHERE article_key=%s',(normalize(base)['article_key'],)).fetchone():raise RuntimeError('News fixture was not rolled back')
    return {'new_changed_unchanged':True,'indexed_time_not_content_change':True,'absence_not_delete':True,
            'bridge_categories_replaced':True,'invalid_rows_retained_in_raw':True,'demo_excluded':True,'fixtures_rolled_back':True}


def review():
    samples=json.loads((ROOT/'config/news_review_sample.json').read_text())
    comparisons=[]
    for item in samples:
        obj=normalize(item['record'])
        comparisons.append({'article_key':obj['article_key'],'title':obj['title'],'rule_level':obj['relevance_level'],
            'review_level':item['review_level'],'rule_categories':obj['categories'],'review_categories':item['review_categories'],
            'level_agrees':obj['relevance_level']==item['review_level'],
            'categories_agree':obj['categories']==sorted(item['review_categories']),'note':item['note']})
    return {'reviewer_type':'AI_ASSISTANT_TITLE_METADATA_REVIEW','human_verified':False,
            'sampling':'all 25 predicted DIRECT/INDIRECT plus 10 fixed IRRELEVANT examples; not random population estimate',
            'sample_size':len(comparisons),'level_agreement_count':sum(r['level_agrees'] for r in comparisons),
            'category_agreement_count':sum(r['categories_agree'] for r in comparisons),'comparisons':comparisons,
            'limitations':'Title-only editorial judgment. No full-text or human gold labels. Not ML accuracy.'}


def check(connection):
    dataset=prepare();wait_idle(connection,epoch(connection));sales_before=history(connection,dataset)['fact_state_sha256']
    initial=seed(connection);state=content_state(connection);again=seed(connection)
    if again['NEW'] or again['UPDATED'] or content_state(connection)!=state:raise RuntimeError('Stored-news replay changed content state')
    prepare_coverage(connection)
    fixture=fixtures(connection)
    source_rows=list(csv.DictReader((ROOT/'data/news_seed/media_api_2024.csv').open(encoding='utf-8-sig',newline='')))
    expected={normalize(r)['article_key'] for r in source_rows}
    found={r['article_key'] for r in connection.execute('SELECT article_key FROM dw.v_news_analysis').fetchall()}
    if not expected<=found:raise RuntimeError('Stored news did not all reach fact_news')
    bad=connection.execute('''SELECT count(*) n FROM staging.news_articles s LEFT JOIN dw.fact_news n USING(article_key)
        LEFT JOIN raw.news_observations o ON o.snapshot_id=s.last_snapshot_id
        LEFT JOIN dw.dim_date d ON d.date_key=n.published_date_key
        LEFT JOIN dw.dim_news_source ns ON ns.news_source_key=n.news_source_key
        WHERE n.news_key IS NULL OR o.snapshot_id IS NULL OR s.content_sha256<>o.content_hash OR n.title<>s.title
        OR n.relevance_level<>s.relevance_level OR n.canonical_url<>s.canonical_url
        OR n.relevance_reason IS DISTINCT FROM s.relevance_reason OR n.rule_version<>s.rule_version
        OR n.quality_status<>s.quality_status OR d.full_date<>s.published_date OR ns.domain IS DISTINCT FROM s.source_domain
        OR n.is_demo<>s.is_demo OR n.origin<>s.origin OR n.first_seen_at<>s.first_seen_at OR n.last_seen_at<>s.last_seen_at
        OR s.category_codes IS DISTINCT FROM coalesce((SELECT array_agg(c.category_code ORDER BY c.category_code)
            FROM dw.bridge_news_category b JOIN dw.dim_category c USING(category_key) WHERE b.news_key=n.news_key),'{}')''').fetchone()['n']
    if bad:raise RuntimeError('News raw/staging/fact lineage reconciliation failed')
    for observation in connection.execute('SELECT payload,content_hash FROM raw.news_observations WHERE content_hash IS NOT NULL').fetchall():
        if normalize(observation['payload'])['content_hash']!=observation['content_hash']:
            raise RuntimeError('News normalized raw payload hash differs from observation hash')
    invalid_bridge=connection.execute('''SELECT count(*) n FROM dw.bridge_news_category b JOIN dw.fact_news n USING(news_key)
        WHERE n.relevance_level NOT IN ('DIRECT','INDIRECT')''').fetchone()['n']
    if invalid_bridge:raise RuntimeError('Irrelevant article has analytical category bridge')
    weighted=connection.execute('SELECT coalesce(sum(article_weight),0) n FROM dw.v_news_category_analysis').fetchone()['n']
    distinct=connection.execute('SELECT count(DISTINCT news_key) n FROM dw.v_news_category_analysis').fetchone()['n']
    if abs(weighted-Decimal(distinct))>Decimal('0.000000001'):raise RuntimeError('Category weights duplicate total article count')
    wait_idle(connection,epoch(connection));sales_after=history(connection,dataset)['fact_state_sha256']
    if sales_before!=sales_after:raise RuntimeError('News pipeline changed sales facts')
    return {'passed':True,'seed_first':initial,'seed_replay':again,'fixtures':fixture,
            'historical_sales_unchanged':True,'category_weight_reconciled':True,'news_report':report(connection),
            'sample_review':review(),'live_api_validated':False}
