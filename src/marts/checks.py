import uuid
from src.news.model import digest
from .refresh import populate,source_state
from .queries import sales,examples,news,all_news_totals
from src.cdc.project import date_key


# Each expected relation is computed directly from fact and existing dimensions.
RELATIONS={
 'sales_cells':'''SELECT packed_date_key,dispatched_date_key,category_key,delivery_geography_key,product_key,customer_key,shipping_method_key,
   count(*) order_count,sum(quantity) quantity_sum,sum(goods_amount) goods_amount,sum(vat_amount) vat_amount,
   sum(shipping_fee) shipping_fee,sum(total_paid) total_paid,coalesce(sum(delivery_hours),0) delivery_hours_sum,
   count(delivery_hours) delivered_orders,count(*) FILTER(WHERE dispatched_before_packed) dispatched_before_packed_count,
   count(*) FILTER(WHERE expected_before_dispatched) expected_before_dispatched_count,
   count(*) FILTER(WHERE received_before_dispatched) received_before_dispatched_count
   FROM dw.v_sales_analysis GROUP BY 1,2,3,4,5,6,7''',
 'sales_daily':'''SELECT packed_date_key,category_key,delivery_geography_key,count(*) order_count,sum(quantity) quantity_sum,
   sum(goods_amount) goods_amount,sum(vat_amount) vat_amount,sum(shipping_fee) shipping_fee,sum(total_paid) total_paid,
   count(DISTINCT customer_key) customer_count FROM dw.v_sales_analysis GROUP BY 1,2,3''',
 'product_daily':'''SELECT packed_date_key,product_key,category_key,count(*) order_count,sum(quantity) quantity_sum,
   sum(goods_amount) goods_amount,count(DISTINCT customer_key) customer_count FROM dw.v_sales_analysis GROUP BY 1,2,3''',
 'customer_summary':'''SELECT customer_key,count(*) order_count,sum(goods_amount) goods_amount,sum(total_paid) total_paid,
   min(packed_date_key) first_packed_date_key,max(packed_date_key) last_packed_date_key FROM dw.v_sales_analysis GROUP BY 1''',
 'delivery_daily':'''SELECT dispatched_date_key,shipping_method_key,delivery_geography_key,count(*) order_count,
   count(delivery_hours) delivered_orders,coalesce(sum(delivery_hours),0) delivery_hours_sum,
   count(*) FILTER(WHERE received_before_dispatched) received_before_dispatched_count FROM dw.v_sales_analysis GROUP BY 1,2,3''',
 'news_daily':'''SELECT published_date_key,news_source_key,relevance_level,count(*) article_count FROM dw.v_news_analysis GROUP BY 1,2,3''',
 'news_membership':'''SELECT n.news_key,b.category_key,n.published_date_key,n.news_source_key,n.relevance_level,
   1.0/count(*) OVER(PARTITION BY n.news_key) article_weight FROM dw.v_news_analysis n
   JOIN dw.bridge_news_category b USING(news_key) WHERE n.relevance_level IN ('DIRECT','INDIRECT')''',
 'news_category_daily':'''SELECT n.published_date_key,n.category_key,n.news_source_key,n.relevance_level,count(DISTINCT n.news_key) article_count,
   sum(n.article_weight) weighted_articles FROM dw.v_news_category_analysis n GROUP BY 1,2,3,4''',
}


def equal_rows(actual,expected,label):
    # Numeric equality keeps Decimal vs bigint casts harmless without rounding away differences.
    if len(actual)!=len(expected) or actual!=expected:raise RuntimeError('Mart/fact mismatch: '+label)


def reconcile(connection,check_snapshot=True):
    result={}
    for name,expected_sql in RELATIONS.items():
        actual=connection.execute('SELECT * FROM mart.'+name+' ORDER BY '+','.join(str(i) for i in range(1,8 if name=='sales_cells' else 2))).fetchall()
        expected=connection.execute('SELECT * FROM ('+expected_sql+') e ORDER BY '+','.join(str(i) for i in range(1,8 if name=='sales_cells' else 2))).fetchall()
        # Sort by the full row, not only the first dimension, for ties on period.
        key=lambda row:tuple(str(row[k]) for k in row)
        equal_rows(sorted(actual,key=key),sorted(expected,key=key),name)
        result[name]=len(actual)
    for dimensions in [(),('year',),('year','category'),('month','district'),('product_version',),('customer',),('dispatch_month','shipping')]:
        equal_rows(sales(connection,dimensions,source='mart'),sales(connection,dimensions,source='fact'),'OLAP '+str(dimensions))
    equal_rows(examples(connection,'mart')['roll_up'],examples(connection,'fact')['roll_up'],'roll_up')
    if examples(connection,'mart')!=examples(connection,'fact'):raise RuntimeError('OLAP example mismatch')
    for dimensions in [(),('year',),('month','category'),('category','source','relevance')]:
        equal_rows(news(connection,dimensions,source='mart'),news(connection,dimensions,source='fact'),'news OLAP '+str(dimensions))
    if all_news_totals(connection,'mart')!=all_news_totals(connection,'fact'):raise RuntimeError('News total/source distinct mismatch')
    totals=sales(connection)[0]
    combined=connection.execute('SELECT coalesce(sum(goods_amount),0) goods,coalesce(sum(order_count),0) orders FROM mart.v_month_category_comparison').fetchone()
    if combined['goods']!=totals['goods_amount'] or combined['orders']!=totals['order_count']:
        raise RuntimeError('Cross-fact monthly join multiplied sales')
    missing=connection.execute("SELECT count(*) n FROM mart.v_month_category_comparison WHERE api_coverage<>'COMPLETE' AND comparable_article_count IS NOT NULL").fetchone()['n']
    if missing:raise RuntimeError('Incomplete news coverage was represented as complete zero')
    grand=connection.execute('SELECT order_count,customer_count,goods_amount FROM mart.v_sales_cube WHERE grouping_mask=7').fetchone()
    if not grand or any(grand[k]!=totals[k] for k in ('order_count','customer_count','goods_amount')):raise RuntimeError('Cube grand total mismatch')
    snapshot=connection.execute("SELECT *,extract(epoch FROM(now()-source_observed_at)) age_seconds FROM mart.snapshot_state WHERE singleton").fetchone()
    if check_snapshot:
        state=source_state(connection)
        if not snapshot or state['source_sha256']!=snapshot['source_sha256']:raise RuntimeError('Mart snapshot is stale; refresh after the source pipeline finishes')
    return {'passed':True,'row_counts':result,'totals':totals,'cube_grand_total_reconciled':True,
            'cross_fact_sales_not_duplicated':True,'snapshot':snapshot,
            'all_news_totals':all_news_totals(connection),'relevant_news_totals':news(connection,())[0],'sla_late_rate':None,'sla_note':'No verified committed SLA; no SLA late rate is published.'}


def fixtures(connection):
    # The uncommitted analytical fixture and all its refreshed marts are rolled back.
    token='PHASE7_FIX_'+uuid.uuid4().hex[:10]
    before=source_state(connection)
    with connection.transaction(force_rollback=True):
        sample=connection.execute('SELECT * FROM dw.v_sales_analysis ORDER BY order_id LIMIT 1').fetchone()
        if not sample:raise RuntimeError('Historical sales are required for refresh mutation fixtures')
        fields=['order_id','customer_key','product_key','category_key','delivery_geography_key','shipping_method_key',
                'packed_date_key','dispatched_date_key','expected_date_key','received_date_key','packed_at','dispatched_at','expected_at','received_at',
                'quantity','transaction_unit_price','goods_amount','vat_amount','shipping_fee','total_paid','quantity_band','warehouse_name','vehicle_type',
                'is_demo','is_deleted','source_epoch','last_event_id','projected_at']
        row={k:sample[k] for k in fields};row.update(order_id=token,is_demo=False,is_deleted=False)
        connection.execute('INSERT INTO dw.fact_sales('+','.join(fields)+') VALUES('+','.join(['%s']*len(fields))+')',tuple(row[k] for k in fields))
        populate(connection);reconcile(connection,False)
        if sales(connection)[0]['order_count']!=before['sales_facts']+1:raise RuntimeError('Insert did not reach mart totals')
        alternate=connection.execute('''SELECT p.product_key,c.category_key FROM dw.dim_product p JOIN dw.dim_category c USING(category_code)
            WHERE NOT p.is_demo AND NOT p.is_deleted AND p.is_current AND p.product_key<>0 AND p.product_key<>%s AND c.category_key<>%s ORDER BY p.product_key LIMIT 1''',(sample['product_key'],sample['category_key'])).fetchone()
        geo=connection.execute('SELECT geography_key FROM dw.dim_geography WHERE geography_key<>0 AND geography_key<>%s ORDER BY geography_key LIMIT 1',(sample['delivery_geography_key'],)).fetchone()
        if not alternate or not geo:raise RuntimeError('Product/geography alternatives are required for reallocation fixture')
        shifted=connection.execute("SELECT %s::timestamp+interval '1 month' stamp",(sample['packed_at'],)).fetchone()['stamp']
        shifted_key=date_key(connection,shifted)
        connection.execute('''UPDATE dw.fact_sales SET product_key=%s,category_key=%s,delivery_geography_key=%s,
            packed_at=%s,packed_date_key=%s,received_at=NULL,received_date_key=0,
            quantity=quantity+1,goods_amount=(quantity+1)*transaction_unit_price,
            vat_amount=round((quantity+1)*transaction_unit_price*0.1,2),
            total_paid=(quantity+1)*transaction_unit_price+round((quantity+1)*transaction_unit_price*0.1,2)+shipping_fee
            WHERE order_id=%s''',(alternate['product_key'],alternate['category_key'],geo['geography_key'],shifted,shifted_key,token))
        populate(connection);reconcile(connection,False)
        connection.execute('UPDATE dw.fact_sales SET is_deleted=true WHERE order_id=%s',(token,))
        populate(connection);reconcile(connection,False)
        if sales(connection)[0]['order_count']!=before['sales_facts']:raise RuntimeError('Soft delete remained in mart')
    if source_state(connection)!=before:raise RuntimeError('Mart fixture changed source facts')
    return {'passed':True,'insert_refresh':True,'money_date_product_geography_reallocation':True,'soft_delete_refresh':True,
            'fixtures_and_mart_changes_rolled_back':True,'scope':'PostgreSQL projection-to-mart fixture; not a new MySQL/CDC integration test'}
