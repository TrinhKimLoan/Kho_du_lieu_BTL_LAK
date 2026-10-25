from datetime import date
from .fetch import config,signature
from .model import RULE_VERSION


def report(connection,collection_id=34412246):
    level=connection.execute('SELECT relevance_level,count(*) n FROM dw.v_news_analysis GROUP BY relevance_level').fetchall()
    monthly=connection.execute('''SELECT d.year,d.month,n.relevance_level,count(*) n FROM dw.v_news_analysis n
        JOIN dw.dim_date d ON d.date_key=n.published_date_key GROUP BY d.year,d.month,n.relevance_level ORDER BY d.year,d.month,n.relevance_level''').fetchall()
    groups=connection.execute('''SELECT c.category_code,count(DISTINCT n.news_key) articles,sum(n.article_weight) weighted_articles
        FROM dw.v_news_category_analysis n JOIN dw.dim_category c USING(category_key) GROUP BY c.category_code ORDER BY c.category_code''').fetchall()
    months=connection.execute("SELECT generate_series(date_trunc('month',min(packed_at)),date_trunc('month',max(packed_at)),interval '1 month')::date AS month FROM dw.v_sales_analysis").fetchall()
    categories=connection.execute("SELECT category_code FROM dw.dim_category WHERE category_key<>0 ORDER BY category_code").fetchall()
    coverage=[];queries=config()
    for item in months:
        month=item['month']
        for category in categories:
            group=category['category_code']
            seed_count=connection.execute('''SELECT count(DISTINCT n.news_key) n FROM dw.v_news_category_analysis n JOIN dw.dim_category c USING(category_key)
                JOIN dw.dim_date d ON d.date_key=n.published_date_key WHERE c.category_code=%s AND d.full_date>=%s AND d.full_date<(%s::date+interval '1 month') AND EXISTS(SELECT 1 FROM raw.news_snapshots r WHERE r.article_key=n.article_key AND r.origin='seed') ''',(group,month,month)).fetchone()['n']
            current=None
            if group in queries:
                current=connection.execute('''SELECT v.status FROM audit.news_coverage v JOIN dw.dim_category c USING(category_key)
                    WHERE c.category_code=%s AND v.month_start=%s AND v.origin='api' AND v.query_signature=%s''',(group,month,signature(group,queries[group],collection_id,month))).fetchone()
            coverage.append({'month':month.isoformat(),'category':group,'seed_observed_articles':seed_count,'api_status':current['status'] if current else 'NOT_FETCHED',
                             'query_configured':group in queries})
    return {'rule_version':RULE_VERSION,'counts_by_relevance':{r['relevance_level']:r['n'] for r in level},
            'monthly_counts':monthly,'by_category':groups,'coverage':coverage,
            'origin_policy':'seed is a stored CSV, API is a polling observation, demo is excluded',
            'comparison_policy':'Aggregate sales and news separately at common month/category grain; never join raw facts through bridge.',
            'causality':'No causal effect of news on sales established.'}
