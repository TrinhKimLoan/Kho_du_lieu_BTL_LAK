from datetime import date

DIMENSIONS={
 'year':('dp.year','year'),
 'quarter':("CASE WHEN dp.full_date IS NULL THEN NULL ELSE dp.year::text||'-Q'||dp.quarter::text END",'quarter'),
 'month':("to_char(dp.full_date,'YYYY-MM')",'month'),
 'packed_date':('dp.full_date','packed_date'),
 'dispatch_month':("to_char(dd.full_date,'YYYY-MM')",'dispatch_month'),
 'category':('c.category_code','category'),
 'city':('g.city','city'),
 'district':('g.district','district'),
 'product':('p.product_id','product'),
 'product_version':("p.product_id||'#'||p.product_key::text||': '||p.product_name",'product_version'),
 'customer':('cu.customer_id','customer'),
 'shipping':('sm.shipping_method_code','shipping'),
}
FILTERS={'start','end','years','categories','districts','cities'}


def sales_query(dimensions=(),filters=None,source='mart'):
    if source not in ('mart','fact'):raise ValueError('Unknown sales source')
    if len(set(dimensions))!=len(dimensions) or any(d not in DIMENSIONS for d in dimensions):raise ValueError('Unknown or repeated OLAP dimension')
    filters=filters or {}
    if set(filters)-FILTERS:raise ValueError('Unknown OLAP filter')
    clauses=[];params=[]
    for key in ('start','end'):
        if key in filters:
            value=date.fromisoformat(str(filters[key]));clauses.append('dp.full_date '+('>=' if key=='start' else '<')+' %s');params.append(value)
    if 'start' in filters and 'end' in filters and str(filters['start'])>=str(filters['end']):raise ValueError('start must precede exclusive end')
    for key,expression in [('years','dp.year'),('categories','c.category_code'),('districts','g.district'),('cities','g.city')]:
        if key in filters:
            values=filters[key]
            if not isinstance(values,(list,tuple)) or not values:raise ValueError('Filter requires a non-empty list')
            if key=='years' and any(type(v) is not int or not 1<=v<=9999 for v in values):raise ValueError('Years must be integers')
            if key!='years' and any(not isinstance(v,str) for v in values):raise ValueError('Dimension filter values must be text')
            clauses.append(expression+'=ANY(%s)');params.append(list(values))
    orders='coalesce(sum(f.order_count),0)' if source=='mart' else 'count(*)'
    qty='coalesce(sum(f.quantity_sum),0)' if source=='mart' else 'coalesce(sum(f.quantity),0)'
    delivered='coalesce(sum(f.delivered_orders),0)' if source=='mart' else 'count(f.delivery_hours)'
    hours='coalesce(sum(f.delivery_hours_sum),0)' if source=='mart' else 'coalesce(sum(f.delivery_hours),0)'
    values=[orders+' AS order_count','count(DISTINCT f.customer_key) AS customer_count',qty+' AS quantity_sum']
    for field in ('goods_amount','vat_amount','shipping_fee','total_paid'):values.append('coalesce(sum(f.'+field+'),0) AS '+field)
    values += [delivered+' AS delivered_orders',hours+' AS delivery_hours_sum',
               'coalesce(sum(f.goods_amount),0)/nullif('+orders+',0) AS avg_order_goods',hours+'/nullif('+delivered+',0) AS avg_delivery_hours']
    expressions=[DIMENSIONS[d][0] for d in dimensions]
    fields=[DIMENSIONS[d][0]+' AS '+DIMENSIONS[d][1] for d in dimensions]
    table='mart.sales_cells' if source=='mart' else 'dw.v_sales_analysis'
    sql='SELECT '+','.join(fields+values)+' FROM '+table+''' f
      JOIN dw.dim_date dp ON dp.date_key=f.packed_date_key JOIN dw.dim_date dd ON dd.date_key=f.dispatched_date_key
      JOIN dw.dim_category c USING(category_key) JOIN dw.dim_product p USING(product_key)
      JOIN dw.dim_customer cu USING(customer_key) JOIN dw.dim_geography g ON g.geography_key=f.delivery_geography_key
      JOIN dw.dim_shipping_method sm USING(shipping_method_key)'''
    if clauses:sql+=' WHERE '+' AND '.join(clauses)
    if expressions:sql+=' GROUP BY '+','.join(expressions)+' ORDER BY '+','.join(str(i+1) for i in range(len(expressions)))
    return sql,params


def sales(connection,dimensions=(),filters=None,source='mart'):
    sql,params=sales_query(dimensions,filters,source)
    return connection.execute(sql,params).fetchall()


def pivot(rows,row='category',column='year',value='goods_amount'):
    if row not in DIMENSIONS or column not in DIMENSIONS:raise ValueError('Unknown pivot dimension')
    if value not in ('goods_amount','order_count','customer_count','avg_order_goods','avg_delivery_hours'):raise ValueError('Unknown pivot measure')
    columns=sorted({str(r[column]) for r in rows});result={};seen=set()
    for item in rows:
        key=(item[row],str(item[column]))
        if key in seen:raise ValueError('Pivot requires one pre-aggregated row per cell; recompute distinct/means before pivot')
        seen.add(key);result.setdefault(item[row],{row:item[row],**{c:None for c in columns}})[str(item[column])]=item[value]
    return {'columns':[row]+columns,'rows':[result[k] for k in sorted(result,key=lambda v:str(v))],
            'totals':'Grand totals must be queried at the required scope, not summed from distinct counts or means.'}


def examples(connection,source='mart'):
    return {
      'roll_up':sales(connection,('year',),source=source),
      'drill_down':sales(connection,('year','quarter','month'),{'years':[2024]},source),
      'slice':sales(connection,('category',),{'years':[2024]},source),
      'dice':sales(connection,('month','category','district'),{'years':[2024],'categories':['CPU','RAM']},source),
      'pivot':pivot(sales(connection,('category','year'),source=source)),
    }


def news(connection,dimensions=('month','category'),filters=None,source='mart'):
    mapping={'year':('d.year','year'),'month':("to_char(d.full_date,'YYYY-MM')",'month'),
             'category':('c.category_code','category'),'source':('ns.domain','source'),
             'relevance':('n.relevance_level','relevance')}
    if source not in ('mart','fact') or len(set(dimensions))!=len(dimensions) or any(k not in mapping for k in dimensions):raise ValueError('Unknown news source/dimension')
    filters=filters or {}
    if set(filters)-{'start','end','categories','years'}:raise ValueError('Unknown news filter')
    clauses=[];params=[]
    for field,operator in [('start','>='),('end','<')]:
        if field in filters:
            clauses.append('d.full_date '+operator+' %s');params.append(date.fromisoformat(str(filters[field])))
    for field,expression in [('categories','c.category_code'),('years','d.year')]:
        if field in filters:
            values=filters[field]
            if not isinstance(values,(list,tuple)) or not values:raise ValueError('News filters require a non-empty list')
            if field=='years' and any(type(v) is not int for v in values):raise ValueError('News years must be integers')
            if field=='categories' and any(not isinstance(v,str) for v in values):raise ValueError('News categories must be text')
            clauses.append(expression+'=ANY(%s)');params.append(list(values))
    dims=[mapping[k][0]+' AS '+mapping[k][1] for k in dimensions]
    metrics=['count(DISTINCT n.news_key) AS article_count','count(DISTINCT n.news_source_key) AS source_count','coalesce(sum(n.article_weight),0) AS weighted_articles']
    table='mart.news_membership' if source=='mart' else 'dw.v_news_category_analysis'
    sql='SELECT '+','.join(dims+metrics)+' FROM '+table+''' n
        JOIN dw.dim_date d ON d.date_key=n.published_date_key JOIN dw.dim_category c USING(category_key)
        JOIN dw.dim_news_source ns USING(news_source_key)'''
    if clauses:sql+=' WHERE '+' AND '.join(clauses)
    if dims:sql+=' GROUP BY '+','.join(mapping[k][0] for k in dimensions)+' ORDER BY '+','.join(str(i+1) for i in range(len(dims)))
    return connection.execute(sql,params).fetchall()


def all_news_totals(connection,source='mart'):
    if source not in ('mart','fact'):raise ValueError('Unknown news source')
    count='coalesce(sum(article_count),0)' if source=='mart' else 'count(*)'
    table='mart.news_daily' if source=='mart' else 'dw.v_news_analysis'
    return connection.execute('SELECT '+count+' AS article_count,count(DISTINCT news_source_key) AS source_count FROM '+table).fetchone()
