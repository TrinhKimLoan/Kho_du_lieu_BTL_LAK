import os
import json
from datetime import date
from urllib.request import urlopen
from src.marts.queries import sales,pivot


def connector_status():
    try:
        with urlopen('http://connect:8083/connectors/lak-source-v1/status',timeout=3) as response:raw=json.load(response)
        return {'connector':raw.get('connector',{}).get('state','UNKNOWN'),
                'tasks':[{'task':r.get('id'),'state':r.get('state','UNKNOWN')} for r in raw.get('tasks',[])]}
    except Exception:return {'connector':'UNAVAILABLE','tasks':[]}


class Repository:
    def __enter__(self):
        import psycopg
        from psycopg.rows import dict_row
        self.connection=psycopg.connect(host=os.environ.get('PG_HOST','postgres'),dbname='lak_warehouse',user='lak_dw',
            password=os.environ['LAK_POSTGRES_PASSWORD'],autocommit=True,row_factory=dict_row,connect_timeout=8,
            options='-c statement_timeout=15000 -c default_transaction_read_only=on')
        self.connection.execute('BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY')
        return self
    def __exit__(self,*args):
        self.connection.rollback();self.connection.close()
    def all(self,sql,params=()):return self.connection.execute(sql,params).fetchall()
    def one(self,sql,params=()):return self.connection.execute(sql,params).fetchone()
    def settings(self):
        if not self.one("SELECT 1 AS ok FROM audit.schema_versions WHERE version='lak-phase10-v1'"):raise RuntimeError('Phase 10 chưa được khởi tạo.')
        return {'categories':[r['category_code'] for r in self.all('SELECT category_code FROM dw.dim_category WHERE category_key<>0 ORDER BY category_code')],
                'districts':[r['district'] for r in self.all('SELECT DISTINCT g.district FROM mart.sales_cells f JOIN dw.dim_geography g ON g.geography_key=f.delivery_geography_key ORDER BY g.district') if r['district']],
                'bounds':self.one('SELECT min(packed_at)::date AS first_date,max(packed_at)::date AS last_date FROM dw.v_sales_analysis'),
                'snapshot':self.one('SELECT source_observed_at,refreshed_at,sales_facts,news_facts FROM mart.snapshot_state WHERE singleton'),
                'inference':self.one('SELECT rfm_model_id,delivery_model_id,reference_date FROM ml.inference_config WHERE singleton'),
                'missing_packed':self.one('SELECT count(*) AS orders,coalesce(sum(goods_amount),0) AS goods_amount FROM dw.v_sales_analysis WHERE packed_at IS NULL'),
                'queried_at':self.one('SELECT now() AS at')['at']}
    def sales(self,dimensions,filters,source='mart'):return sales(self.connection,dimensions,filters,source)
    def overview(self,filters):
        return {'kpi':self.sales((),filters)[0],'trend':self.sales(('month',),filters),
                'categories':self.sales(('category',),filters),
                'products':sorted(self.sales(('product_version',),filters),key=lambda r:-r['goods_amount'])[:10]}
    def olap(self,filters,year):
        narrowed=dict(filters,years=[year])
        roll=self.sales(('year',),filters);drill=self.sales(('year','quarter','month'),narrowed)
        sliced=self.sales(('category',),narrowed);diced=self.sales(('month','category','district'),filters)
        cells=self.sales(('category','year'),filters)
        return {'roll_up':roll,'drill_down':drill,'slice':sliced,'dice':diced,'pivot':pivot(cells),
                'grand_total':self.sales((),filters)[0]}
    def model(self,algorithm):
        if algorithm not in ('kmeans_rfm','random_forest_delivery'):raise ValueError('Unknown model algorithm')
        column='rfm_model_id' if algorithm=='kmeans_rfm' else 'delivery_model_id'
        return self.one('''SELECT r.model_id,r.algorithm,r.created_at,r.status,r.active,r.metadata,r.snapshot_id,s.reference_date,s.row_count
         FROM ml.inference_config c JOIN ml.model_registry r ON r.model_id=c.'''+column+'''
         JOIN ml.feature_snapshots s USING(snapshot_id) WHERE c.singleton''')
    def customers(self):
        model=self.model('kmeans_rfm')
        rows=self.all('''SELECT c.customer_id,h.cluster_id,h.state,h.input->>'recency_days' AS recency_days,
          h.input->>'frequency' AS frequency,h.input->>'monetary' AS monetary,h.assigned_at,h.reference_date,h.model_id
          FROM ml.rfm_current_assignments a JOIN ml.rfm_assignment_history h USING(job_id)
          JOIN dw.dim_customer c ON c.customer_key=a.customer_key JOIN ml.inference_config cfg ON cfg.singleton
          WHERE NOT a.is_demo AND a.model_id=cfg.rfm_model_id AND a.reference_date=cfg.reference_date
          ORDER BY c.customer_id''')
        return {'model':model,'rows':rows,'profiles':self.all('SELECT cluster_id,display_name,customer_count,profile FROM ml.segment_profiles WHERE model_id=%s ORDER BY cluster_id',(model['model_id'],)),
                'expected':self.one('SELECT count(*) AS n FROM dw.dim_customer WHERE customer_key<>0 AND NOT is_demo')['n']}
    def fact_filter(self,filters,time='dispatched_at'):
        if time not in ('dispatched_at','packed_at'):raise ValueError('Unknown time role')
        clauses=['NOT f.is_demo','NOT f.is_deleted','f.'+time+'>=%s::date','f.'+time+'<%s::date'];params=[filters['start'],filters['end']]
        if filters.get('categories'):clauses.append('c.category_code=ANY(%s)');params.append(filters['categories'])
        if filters.get('districts'):clauses.append('g.district=ANY(%s)');params.append(filters['districts'])
        return ' AND '.join(clauses),params
    def shipping(self,filters):
        where,params=self.fact_filter(filters)
        actual=self.all('''SELECT f.order_id,f.delivery_hours,s.shipping_method_code AS shipping_method,g.district,f.dispatched_at,
          f.received_before_dispatched FROM dw.fact_sales f JOIN dw.dim_category c USING(category_key)
          JOIN dw.dim_geography g ON g.geography_key=f.delivery_geography_key JOIN dw.dim_shipping_method s USING(shipping_method_key)
          WHERE '''+where+' ORDER BY f.dispatched_at,f.order_id',params)
        model=self.model('random_forest_delivery')
        test=self.all('''SELECT p.order_id,p.actual_hours,p.predicted_hours,p.baseline_hours,p.error_hours,
          f.features->>'shipping_method' AS shipping_method,f.features->>'delivery_district' AS district
          FROM ml.delivery_predictions p JOIN ml.delivery_features f ON f.snapshot_id=p.snapshot_id AND f.order_id=p.order_id
          WHERE p.model_id=%s AND f.split='test' ORDER BY p.order_id''',(model['model_id'],))
        live=self.all('''SELECT p.order_id,p.model_id,p.predicted_hours,p.dispatched_at,p.predicted_at,o.state,o.actual_hours,o.error_hours
          FROM ml.live_delivery_predictions p LEFT JOIN LATERAL(SELECT * FROM ml.delivery_outcome_history x
            WHERE x.prediction_id=p.prediction_id ORDER BY x.job_id DESC LIMIT 1) o ON true
          WHERE NOT p.is_demo ORDER BY p.predicted_at DESC LIMIT 300''')
        return {'actual':actual,'model':model,'test':test,'live':live}
    def news(self,filters,page=1,category=None):
        clauses=['d.full_date>=%s::date','d.full_date<%s::date'];params=[filters['start'],filters['end']]
        categories=filters.get('categories')
        if categories:
            clauses.append('EXISTS(SELECT 1 FROM dw.bridge_news_category b JOIN dw.dim_category c USING(category_key) WHERE b.news_key=n.news_key AND c.category_code=ANY(%s))');params.append(categories)
        where=' AND '.join(clauses)
        base=' FROM dw.v_news_analysis n JOIN dw.dim_date d ON d.date_key=n.published_date_key JOIN dw.dim_news_source s USING(news_source_key) WHERE '+where
        count=self.one('SELECT count(*) AS n'+base,params)['n']
        articles=self.all('''SELECT n.article_key,n.title,n.canonical_url,s.domain,d.full_date AS published_date,n.relevance_level,n.relevance_reason,n.origin'''+base+' ORDER BY d.full_date DESC,n.article_key LIMIT 30 OFFSET %s',params+[(page-1)*30])
        monthly=self.all("SELECT to_char(d.full_date,'YYYY-MM') AS month,count(*) AS articles"+base+' GROUP BY 1 ORDER BY 1',params)
        sources=self.all('SELECT s.domain,count(*) AS articles'+base+' GROUP BY s.domain ORDER BY articles DESC LIMIT 15',params)
        category_clause=' AND c.category_code=ANY(%s)' if categories else ''
        cp=[filters['start'],filters['end']]+([categories] if categories else [])
        coverage=self.all('''SELECT v.month_start,c.category_code,v.api_status,v.query_configured FROM mart.news_coverage v
          JOIN dw.dim_category c USING(category_key) WHERE v.month_start>=date_trunc('month',%s::date)
          AND v.month_start<%s::date'''+category_clause+' ORDER BY v.month_start,c.category_code',cp)
        comparison=self.all('''WITH sa AS (
          SELECT date_trunc('month',d.full_date)::date AS month_start,sum(f.goods_amount) AS goods_amount
          FROM mart.sales_daily f JOIN dw.dim_date d ON d.date_key=f.packed_date_key JOIN dw.dim_category c USING(category_key)
          WHERE d.full_date>=%s::date AND d.full_date<%s::date AND c.category_code=%s GROUP BY 1
        ), ne AS (
          SELECT date_trunc('month',d.full_date)::date AS month_start,count(DISTINCT n.news_key) AS articles
          FROM mart.news_membership n JOIN dw.dim_date d ON d.date_key=n.published_date_key JOIN dw.dim_category c USING(category_key)
          WHERE d.full_date>=%s::date AND d.full_date<%s::date AND c.category_code=%s GROUP BY 1
        ) SELECT coalesce(sa.month_start,ne.month_start) AS month_start,sa.goods_amount,
          coalesce(ne.articles,0) AS observed_articles,coalesce(v.api_status,'NOT_FETCHED') AS api_coverage,
          CASE WHEN v.api_status='COMPLETE' THEN coalesce(ne.articles,0) ELSE NULL END AS comparable_article_count
        FROM sa FULL OUTER JOIN ne USING(month_start)
        LEFT JOIN mart.news_coverage v ON v.month_start=coalesce(sa.month_start,ne.month_start)
          AND v.category_key=(SELECT category_key FROM dw.dim_category WHERE category_code=%s)
        ORDER BY 1''', (filters['start'],filters['end'],category or 'RAM',filters['start'],filters['end'],category or 'RAM',category or 'RAM'))
        return {'count':count,'articles':articles,'monthly':monthly,'sources':sources,'coverage':coverage,'comparison':comparison}
    def detail(self,kind,value):
        if kind not in ('order','customer') or not isinstance(value,str) or not 1<=len(value.strip())<=120:raise ValueError('Mã tra cứu không hợp lệ.')
        value=value.strip()
        clause='f.order_id=%s' if kind=='order' else 'c.customer_id=%s'
        rows=self.all('''SELECT f.order_id,c.customer_id,p.product_name,f.quantity,f.goods_amount,f.total_paid,
          f.packed_at,f.dispatched_at,f.received_at,f.delivery_hours,s.shipping_method_code,f.is_demo,f.is_deleted
          FROM dw.fact_sales f JOIN dw.dim_customer c USING(customer_key) JOIN dw.dim_product p USING(product_key)
          JOIN dw.dim_shipping_method s USING(shipping_method_key) WHERE '''+clause+' ORDER BY f.packed_at DESC NULLS LAST,f.order_id LIMIT 100',(value,))
        customer=rows[0]['customer_id'] if rows else value if kind=='customer' else None
        segments=self.all('''SELECT h.reference_date,h.model_id,h.cluster_id,h.state,h.input,h.assigned_at
          FROM ml.rfm_assignment_history h JOIN dw.dim_customer c USING(customer_key) WHERE c.customer_id=%s ORDER BY h.job_id DESC LIMIT 30''',(customer,)) if customer else []
        predictions=self.all('''SELECT p.order_id,p.model_id,p.predicted_hours,p.dispatched_at,p.predicted_at,p.input_sha256,o.state,o.actual_hours,o.error_hours
          FROM ml.live_delivery_predictions p LEFT JOIN LATERAL(SELECT state,actual_hours,error_hours FROM ml.delivery_outcome_history x
            WHERE x.prediction_id=p.prediction_id ORDER BY job_id DESC LIMIT 1)o ON true
          WHERE p.order_id IN (SELECT f.order_id FROM dw.fact_sales f JOIN dw.dim_customer c USING(customer_key) WHERE '''+clause+''')
          ORDER BY p.predicted_at DESC LIMIT 100''',(value,))
        return {'orders':rows,'segments':segments,'predictions':predictions}
    def operations(self):
        return {'connector':connector_status(),
          'workers':self.all('''SELECT worker,heartbeat_at,extract(epoch FROM now()-heartbeat_at)::integer AS age_seconds,
            heartbeat_at>now()-interval '30 seconds' AND safe_error IS NULL AS healthy,safe_error FROM audit.worker_heartbeats ORDER BY worker'''),
          'cdc':self.one('''SELECT count(*) AS events,count(*) FILTER(WHERE processed_at IS NULL) AS pending,
            max(captured_at) AS latest_capture,max(processed_at) AS latest_projection,
            avg(extract(epoch FROM processed_at-captured_at)) FILTER(WHERE processed_at>=captured_at) AS avg_capture_to_process_seconds FROM raw.cdc_events'''),
          'event_series':self.all("SELECT date_trunc('minute',captured_at) AS minute,count(*) AS events FROM raw.cdc_events WHERE captured_at>now()-interval '24 hours' GROUP BY 1 ORDER BY 1"),
          'queues':self.all('SELECT kind,state,is_demo,count(*) AS jobs FROM ml.inference_jobs GROUP BY kind,state,is_demo ORDER BY kind,state,is_demo'),
          'errors':self.all("SELECT error_code,state,count(*) AS errors FROM audit.projection_errors GROUP BY error_code,state ORDER BY errors DESC"),
          'quality':self.all('SELECT rule_code,severity,count(*) AS findings,count(*) FILTER(WHERE resolved_at IS NULL) AS unresolved FROM audit.quality_findings GROUP BY rule_code,severity ORDER BY severity,rule_code'),
          'runs':self.all('SELECT pipeline,status,started_at,finished_at FROM audit.pipeline_runs ORDER BY started_at DESC LIMIT 30'),
          'models':self.all('SELECT model_id,algorithm,status,active,created_at,snapshot_id FROM ml.model_registry ORDER BY created_at DESC LIMIT 20'),
          'clock':self.all('SELECT reference_date,previous_date,reason,changed_at FROM ml.rfm_reference_history ORDER BY changed_at DESC LIMIT 20')}
    def demo(self,suffix):
        from .demo import validate_suffix
        validate_suffix(suffix);oid='DEMO_'+suffix+'_O';cid='DEMO_'+suffix+'_C'
        return {'order_id':oid,'fact':self.one('SELECT order_id,quantity,goods_amount,received_at,is_demo,is_deleted,last_event_id FROM dw.fact_sales WHERE order_id=%s',(oid,)),
          'jobs':self.all('''SELECT j.job_id,j.kind,j.state,j.attempts,j.enqueued_at,j.finished_at FROM ml.inference_jobs j
            WHERE j.entity_key=%s OR (j.kind='RFM' AND j.entity_key IN(SELECT customer_key::text FROM dw.dim_customer WHERE customer_id=%s))
            ORDER BY job_id DESC LIMIT 20''',(oid,cid)),
          'segments':self.all('''SELECT h.reference_date,h.cluster_id,h.state,h.input,h.model_id,h.assigned_at FROM ml.rfm_assignment_history h
             JOIN dw.dim_customer c USING(customer_key) WHERE c.customer_id=%s ORDER BY h.job_id DESC LIMIT 10''',(cid,)),
          'predictions':self.all('SELECT order_id,model_id,predicted_hours,input,input_sha256,predicted_at FROM ml.live_delivery_predictions WHERE order_id=%s AND is_demo',(oid,)),
          'outcomes':self.all('''SELECT o.state,o.actual_hours,o.error_hours,o.recorded_at FROM ml.delivery_outcome_history o
             JOIN ml.live_delivery_predictions p USING(prediction_id) WHERE p.order_id=%s AND p.is_demo ORDER BY o.job_id DESC LIMIT 10''',(oid,))}
