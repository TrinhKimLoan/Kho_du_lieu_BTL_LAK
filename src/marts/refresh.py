import hashlib
import uuid
import time
from src.source.data import ROOT
from src.news.model import digest
from src.news.fetch import config,signature


LOCK=274107


def acquire(connection):
    deadline=time.monotonic()+60
    while not connection.execute('SELECT pg_try_advisory_lock(%s) locked',(LOCK,)).fetchone()['locked']:
        if time.monotonic()>=deadline:raise RuntimeError('Another mart refresh or validation owns the lock for more than 60 seconds')
        time.sleep(0.5)
    connection.execute("SET TIME ZONE 'UTC'")


def migrate(connection):
    if not connection.execute("SELECT 1 FROM audit.schema_versions WHERE version='lak-phase6-v1'").fetchone():raise RuntimeError('Phase 6 warehouse is required')
    sql=(ROOT/'sql/phase7/001_marts.sql').read_text()
    checksum=hashlib.sha256(sql.encode()).hexdigest()
    with connection.transaction():
        connection.execute('CREATE TABLE IF NOT EXISTS audit.mart_schema_identity(singleton boolean PRIMARY KEY DEFAULT true CHECK(singleton),ddl_sha256 text NOT NULL)')
        previous=connection.execute('SELECT ddl_sha256 FROM audit.mart_schema_identity WHERE singleton').fetchone()
        if previous and previous['ddl_sha256']!=checksum:raise RuntimeError('Mart schema fingerprint changed; explicit migration required')
        connection.execute(sql,prepare=False)
        connection.execute('INSERT INTO audit.mart_schema_identity VALUES(true,%s) ON CONFLICT(singleton) DO NOTHING',(checksum,))


def source_state(connection):
    sales=connection.execute('SELECT to_jsonb(f)::text row_state FROM dw.v_sales_analysis f ORDER BY order_id').fetchall()
    news=connection.execute('SELECT to_jsonb(n)::text row_state FROM dw.v_news_analysis n ORDER BY article_key').fetchall()
    bridges=connection.execute('SELECT b.news_key,b.category_key FROM dw.bridge_news_category b JOIN dw.v_news_analysis n USING(news_key) ORDER BY b.news_key,b.category_key').fetchall()
    coverage=connection.execute('SELECT to_jsonb(c)::text row_state FROM audit.news_coverage c ORDER BY month_start,category_key,query_signature,origin').fetchall()
    return {'sales_facts':len(sales),'news_facts':len(news),'source_sha256':digest([sales,news,bridges,coverage])}


def populate(connection):
    connection.execute((ROOT/'sql/phase7/002_populate.sql').read_text(),prepare=False)
    connection.execute('DELETE FROM mart.news_coverage')
    periods=connection.execute('''SELECT generate_series(min(d),max(d),interval '1 month')::date AS month_start FROM (
        SELECT date_trunc('month',packed_at) d FROM dw.v_sales_analysis
        UNION ALL SELECT date_trunc('month',d.full_date) FROM dw.v_news_analysis n JOIN dw.dim_date d ON d.date_key=n.published_date_key
    ) dates''').fetchall()
    categories=connection.execute('SELECT category_key,category_code FROM dw.dim_category WHERE category_key<>0 ORDER BY category_key').fetchall()
    queries=config()
    for row in periods:
        month=row['month_start']
        for cat in categories:
            code=cat['category_code'];sig=signature(code,queries[code],34412246,month) if code in queries else None
            status=None
            if sig:
                status=connection.execute("SELECT status FROM audit.news_coverage WHERE month_start=%s AND category_key=%s AND query_signature=%s AND origin='api'",(month,cat['category_key'],sig)).fetchone()
            connection.execute('INSERT INTO mart.news_coverage VALUES(%s,%s,%s,%s,%s)',(month,cat['category_key'],status['status'] if status else 'NOT_FETCHED',code in queries,sig))


def refresh(connection):
    from psycopg.types.json import Jsonb
    run_id=uuid.uuid4()
    connection.execute("INSERT INTO audit.pipeline_runs(run_id,pipeline,status) VALUES(%s,'phase7-mart-refresh','RUNNING')",(run_id,))
    try:
        with connection.transaction():
            connection.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
            observed=connection.execute('SELECT transaction_timestamp() moment').fetchone()['moment']
            state=source_state(connection)
            populate(connection)
            # Test financial/count components before publishing the new snapshot.
            actual=connection.execute('SELECT coalesce(sum(order_count),0) n FROM mart.sales_cells').fetchone()['n']
            if actual!=state['sales_facts']:raise RuntimeError('Mart refresh lost or duplicated sales orders')
            connection.execute('''INSERT INTO mart.snapshot_state(singleton,refresh_id,source_observed_at,refreshed_at,sales_facts,news_facts,source_sha256)
                VALUES(true,%s,%s,clock_timestamp(),%s,%s,%s) ON CONFLICT(singleton) DO UPDATE SET
                refresh_id=excluded.refresh_id,source_observed_at=excluded.source_observed_at,refreshed_at=excluded.refreshed_at,
                sales_facts=excluded.sales_facts,news_facts=excluded.news_facts,source_sha256=excluded.source_sha256''',
                (run_id,observed,state['sales_facts'],state['news_facts'],state['source_sha256']))
            connection.execute("UPDATE audit.pipeline_runs SET status='SUCCESS',finished_at=clock_timestamp(),details=%s WHERE run_id=%s",(Jsonb(state),run_id))
        return dict(state,refresh_id=str(run_id),atomic_snapshot=True)
    except Exception as exc:
        connection.execute("UPDATE audit.pipeline_runs SET status='FAILED',finished_at=now(),details=%s WHERE run_id=%s",(Jsonb({'error_type':type(exc).__name__}),run_id));raise
