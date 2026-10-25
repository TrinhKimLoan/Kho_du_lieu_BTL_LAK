from dataclasses import dataclass


@dataclass(frozen=True)
class Rule:
    code: str
    severity: str
    entity: str
    sql: str


RULES = [
    Rule('UNKNOWN_MEMBERS', 'ERROR', 'dimension', """SELECT name AS entity_key FROM (VALUES
        ('date',EXISTS(SELECT 1 FROM dw.dim_date WHERE date_key=0)),
        ('customer',EXISTS(SELECT 1 FROM dw.dim_customer WHERE customer_key=0)),
        ('product',EXISTS(SELECT 1 FROM dw.dim_product WHERE product_key=0)),
        ('category',EXISTS(SELECT 1 FROM dw.dim_category WHERE category_key=0)),
        ('geography',EXISTS(SELECT 1 FROM dw.dim_geography WHERE geography_key=0)),
        ('shipping',EXISTS(SELECT 1 FROM dw.dim_shipping_method WHERE shipping_method_key=0)),
        ('news_source',EXISTS(SELECT 1 FROM dw.dim_news_source WHERE news_source_key=0))) AS required(name,present)
        WHERE NOT present"""),
    Rule('SALES_DUPLICATE', 'ERROR', 'orders', "SELECT order_id AS entity_key FROM dw.fact_sales GROUP BY order_id HAVING count(*)>1"),
    Rule('SALES_FOREIGN_KEYS', 'ERROR', 'orders', '''SELECT f.order_id AS entity_key FROM dw.fact_sales f
        LEFT JOIN dw.dim_customer c USING(customer_key) LEFT JOIN dw.dim_product p USING(product_key)
        LEFT JOIN dw.dim_category g USING(category_key) LEFT JOIN dw.dim_geography d ON d.geography_key=f.delivery_geography_key
        LEFT JOIN dw.dim_shipping_method s USING(shipping_method_key)
        LEFT JOIN dw.dim_date d1 ON d1.date_key=f.packed_date_key
        LEFT JOIN dw.dim_date d2 ON d2.date_key=f.dispatched_date_key
        LEFT JOIN dw.dim_date d3 ON d3.date_key=f.expected_date_key
        LEFT JOIN dw.dim_date d4 ON d4.date_key=f.received_date_key
        WHERE d1.date_key IS NULL OR d2.date_key IS NULL OR d3.date_key IS NULL OR d4.date_key IS NULL OR c.customer_key IS NULL OR p.product_key IS NULL OR g.category_key IS NULL OR d.geography_key IS NULL OR s.shipping_method_key IS NULL'''),
    Rule('SALES_MONEY', 'ERROR', 'orders', '''SELECT order_id AS entity_key FROM dw.fact_sales WHERE quantity<=0
        OR transaction_unit_price<=0 OR shipping_fee<0 OR goods_amount<>quantity*transaction_unit_price
        OR vat_amount<>round(goods_amount*0.1,2) OR total_paid<>goods_amount+vat_amount+shipping_fee'''),
    Rule('DATE_ROLES', 'ERROR', 'orders', '''SELECT order_id AS entity_key FROM dw.fact_sales WHERE
        packed_date_key<>coalesce(to_char(packed_at,'YYYYMMDD')::integer,0)
        OR dispatched_date_key<>coalesce(to_char(dispatched_at,'YYYYMMDD')::integer,0)
        OR expected_date_key<>coalesce(to_char(expected_at,'YYYYMMDD')::integer,0)
        OR received_date_key<>coalesce(to_char(received_at,'YYYYMMDD')::integer,0)'''),
    Rule('SCD2_OVERLAP', 'ERROR', 'products', '''SELECT DISTINCT a.product_id AS entity_key FROM dw.dim_product a JOIN dw.dim_product b
        ON a.product_id=b.product_id AND a.product_key<b.product_key
        WHERE tstzrange(a.valid_from,a.valid_to,'[)') && tstzrange(b.valid_from,b.valid_to,'[)')'''),
    Rule('SCD2_CURRENT', 'ERROR', 'products', '''SELECT product_id AS entity_key FROM dw.dim_product GROUP BY product_id
        HAVING count(*) FILTER(WHERE is_current)<>1'''),
    Rule('SCD2_BOUNDS', 'ERROR', 'products', '''SELECT product_id AS entity_key FROM dw.dim_product
        WHERE (valid_to IS NOT NULL AND valid_to<=valid_from) OR is_current<>(valid_to IS NULL)'''),
    Rule('FACT_PRODUCT_VERSION', 'ERROR', 'orders', '''SELECT f.order_id AS entity_key FROM dw.fact_sales f
        JOIN dw.dim_product p USING(product_key) JOIN staging.orders o USING(order_id) JOIN dw.dim_category c USING(category_key)
        WHERE p.product_id<>o.product_id OR p.category_code<>c.category_code'''),
    Rule('UNKNOWN_ANALYTICAL_KEYS', 'ERROR', 'orders', '''SELECT order_id AS entity_key FROM dw.v_sales_analysis
        WHERE customer_key=0 OR product_key=0 OR category_key=0 OR delivery_geography_key=0 OR shipping_method_key=0'''),
    Rule('ML_TARGET', 'ERROR', 'orders', '''SELECT order_id AS entity_key FROM dw.fact_sales
        WHERE ((received_at IS NULL OR dispatched_at IS NULL OR received_at<dispatched_at) AND delivery_hours IS NOT NULL)
        OR (received_at>=dispatched_at AND delivery_hours IS DISTINCT FROM extract(epoch FROM(received_at-dispatched_at))/3600)'''),
    Rule('DEMO_ANALYSIS_LEAK', 'ERROR', 'orders', "SELECT order_id AS entity_key FROM dw.v_sales_analysis WHERE is_demo OR is_deleted"),
    Rule('PROJECTION_UNRESOLVED', 'ERROR', 'cdc', "SELECT error_id::text AS entity_key FROM audit.projection_errors WHERE state IN ('OPEN','RETRYING')"),
    Rule('DISPATCH_BEFORE_PACK', 'WARNING', 'orders', "SELECT order_id AS entity_key FROM dw.v_sales_analysis WHERE dispatched_at<packed_at"),
    Rule('EXPECTED_BEFORE_DISPATCH', 'WARNING', 'orders', "SELECT order_id AS entity_key FROM dw.v_sales_analysis WHERE expected_at<dispatched_at"),
    Rule('RECEIVED_BEFORE_DISPATCH', 'WARNING', 'orders', "SELECT order_id AS entity_key FROM dw.v_sales_analysis WHERE received_at<dispatched_at"),
    Rule('MISSING_DELIVERY_TIMES', 'WARNING', 'orders', "SELECT order_id AS entity_key FROM dw.v_sales_analysis WHERE dispatched_at IS NULL OR received_at IS NULL"),
]


def summarize(counts):
    errors=sum(n for code,n in counts.items() if next(r for r in RULES if r.code==code).severity=='ERROR')
    warnings=sum(n for code,n in counts.items() if next(r for r in RULES if r.code==code).severity=='WARNING')
    return {'error_findings':errors,'warning_findings':warnings,'passed':errors==0}
