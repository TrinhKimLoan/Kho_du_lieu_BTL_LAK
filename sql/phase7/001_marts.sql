CREATE TABLE IF NOT EXISTS mart.sales_cells (
    packed_date_key integer NOT NULL,
    dispatched_date_key integer NOT NULL,
    category_key bigint NOT NULL,
    delivery_geography_key bigint NOT NULL,
    product_key bigint NOT NULL,
    customer_key bigint NOT NULL,
    shipping_method_key bigint NOT NULL,
    order_count bigint NOT NULL,
    quantity_sum bigint NOT NULL,
    goods_amount numeric NOT NULL,
    vat_amount numeric NOT NULL,
    shipping_fee numeric NOT NULL,
    total_paid numeric NOT NULL,
    delivery_hours_sum numeric NOT NULL,
    delivered_orders bigint NOT NULL,
    dispatched_before_packed_count bigint NOT NULL,
    expected_before_dispatched_count bigint NOT NULL,
    received_before_dispatched_count bigint NOT NULL,
    PRIMARY KEY(packed_date_key,dispatched_date_key,category_key,delivery_geography_key,product_key,customer_key,shipping_method_key)
);
CREATE INDEX IF NOT EXISTS sales_cells_period ON mart.sales_cells(packed_date_key,category_key,delivery_geography_key);
CREATE TABLE IF NOT EXISTS mart.sales_daily (
    packed_date_key integer NOT NULL,
    category_key bigint NOT NULL,
    delivery_geography_key bigint NOT NULL,
    order_count bigint NOT NULL,
    quantity_sum bigint NOT NULL,
    goods_amount numeric NOT NULL,
    vat_amount numeric NOT NULL,
    shipping_fee numeric NOT NULL,
    total_paid numeric NOT NULL,
    customer_count bigint NOT NULL,
    PRIMARY KEY(packed_date_key,category_key,delivery_geography_key)
);
CREATE TABLE IF NOT EXISTS mart.product_daily (
    packed_date_key integer NOT NULL,
    product_key bigint NOT NULL,
    category_key bigint NOT NULL,
    order_count bigint NOT NULL,
    quantity_sum bigint NOT NULL,
    goods_amount numeric NOT NULL,
    customer_count bigint NOT NULL,
    PRIMARY KEY(packed_date_key,product_key,category_key)
);
CREATE TABLE IF NOT EXISTS mart.customer_summary (
    customer_key bigint PRIMARY KEY,
    order_count bigint NOT NULL,
    goods_amount numeric NOT NULL,
    total_paid numeric NOT NULL,
    first_packed_date_key integer NOT NULL,
    last_packed_date_key integer NOT NULL
);
CREATE TABLE IF NOT EXISTS mart.delivery_daily (
    dispatched_date_key integer NOT NULL,
    shipping_method_key bigint NOT NULL,
    delivery_geography_key bigint NOT NULL,
    order_count bigint NOT NULL,
    delivered_orders bigint NOT NULL,
    delivery_hours_sum numeric NOT NULL,
    received_before_dispatched_count bigint NOT NULL,
    PRIMARY KEY(dispatched_date_key,shipping_method_key,delivery_geography_key)
);
CREATE TABLE IF NOT EXISTS mart.news_daily (
    published_date_key integer NOT NULL,
    news_source_key bigint NOT NULL,
    relevance_level text NOT NULL,
    article_count bigint NOT NULL,
    PRIMARY KEY(published_date_key,news_source_key,relevance_level)
);
CREATE TABLE IF NOT EXISTS mart.news_membership (
    news_key bigint NOT NULL,
    category_key bigint NOT NULL,
    published_date_key integer NOT NULL,
    news_source_key bigint NOT NULL,
    relevance_level text NOT NULL,
    article_weight numeric NOT NULL,
    PRIMARY KEY(news_key,category_key)
);
CREATE INDEX IF NOT EXISTS news_membership_period ON mart.news_membership(published_date_key,category_key);
CREATE TABLE IF NOT EXISTS mart.news_category_daily (
    published_date_key integer NOT NULL,
    category_key bigint NOT NULL,
    news_source_key bigint NOT NULL,
    relevance_level text NOT NULL,
    article_count bigint NOT NULL,
    weighted_articles numeric NOT NULL,
    PRIMARY KEY(published_date_key,category_key,news_source_key,relevance_level)
);
CREATE TABLE IF NOT EXISTS mart.news_coverage (
    month_start date NOT NULL,
    category_key bigint NOT NULL,
    api_status text NOT NULL,
    query_configured boolean NOT NULL,
    query_signature text,
    PRIMARY KEY(month_start,category_key)
);
CREATE TABLE IF NOT EXISTS mart.snapshot_state (
    singleton boolean PRIMARY KEY DEFAULT true CHECK(singleton),
    refresh_id uuid NOT NULL REFERENCES audit.pipeline_runs(run_id),
    source_observed_at timestamptz NOT NULL,
    refreshed_at timestamptz NOT NULL,
    sales_facts bigint NOT NULL,
    news_facts bigint NOT NULL,
    source_sha256 text NOT NULL
);
CREATE OR REPLACE VIEW mart.v_sales_cube AS
SELECT dp.year,c.category_code,g.city,
       GROUPING(dp.year,c.category_code,g.city) AS grouping_mask,
       coalesce(sum(f.order_count),0) AS order_count,count(DISTINCT f.customer_key) AS customer_count,
       coalesce(sum(f.goods_amount),0) AS goods_amount,coalesce(sum(f.vat_amount),0) AS vat_amount,
       coalesce(sum(f.shipping_fee),0) AS shipping_fee,coalesce(sum(f.total_paid),0) AS total_paid,
       sum(f.goods_amount)/nullif(sum(f.order_count),0) AS avg_order_goods,
       sum(f.delivery_hours_sum)/nullif(sum(f.delivered_orders),0) AS avg_delivery_hours
FROM mart.sales_cells f JOIN dw.dim_date dp ON dp.date_key=f.packed_date_key
JOIN dw.dim_category c USING(category_key) JOIN dw.dim_geography g ON g.geography_key=f.delivery_geography_key
GROUP BY CUBE(dp.year,c.category_code,g.city);
CREATE OR REPLACE VIEW mart.v_month_category_comparison AS
WITH sales AS (
 SELECT date_trunc('month',d.full_date)::date AS month_start,f.category_key,
        sum(f.order_count) order_count,sum(f.goods_amount) goods_amount,sum(f.total_paid) total_paid
 FROM mart.sales_daily f JOIN dw.dim_date d ON d.date_key=f.packed_date_key
 GROUP BY date_trunc('month',d.full_date)::date,f.category_key
), news AS (
 SELECT date_trunc('month',d.full_date)::date AS month_start,n.category_key,
        count(DISTINCT n.news_key) observed_articles,count(DISTINCT n.news_source_key) observed_sources,
        sum(n.article_weight) weighted_articles
 FROM mart.news_membership n JOIN dw.dim_date d ON d.date_key=n.published_date_key
 GROUP BY date_trunc('month',d.full_date)::date,n.category_key
)
SELECT coalesce(s.month_start,n.month_start) month_start,coalesce(s.category_key,n.category_key) category_key,
       s.order_count,s.goods_amount,s.total_paid,coalesce(n.observed_articles,0) observed_articles,
       coalesce(n.observed_sources,0) observed_sources,coalesce(n.weighted_articles,0) weighted_articles,
       coalesce(v.api_status,'NOT_FETCHED') api_coverage,
       CASE WHEN v.api_status='COMPLETE' THEN coalesce(n.observed_articles,0) ELSE NULL END comparable_article_count
FROM sales s FULL OUTER JOIN news n USING(month_start,category_key)
LEFT JOIN mart.news_coverage v ON v.month_start=coalesce(s.month_start,n.month_start)
 AND v.category_key=coalesce(s.category_key,n.category_key);
INSERT INTO audit.schema_versions(version) VALUES('lak-phase7-v1') ON CONFLICT(version) DO NOTHING;
