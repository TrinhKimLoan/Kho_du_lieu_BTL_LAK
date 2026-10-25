DELETE FROM mart.sales_cells;
INSERT INTO mart.sales_cells
SELECT packed_date_key,dispatched_date_key,category_key,delivery_geography_key,product_key,customer_key,shipping_method_key,
 count(*),sum(quantity),sum(goods_amount),sum(vat_amount),sum(shipping_fee),sum(total_paid),
 coalesce(sum(delivery_hours),0),count(delivery_hours),
 count(*) FILTER(WHERE dispatched_before_packed),count(*) FILTER(WHERE expected_before_dispatched),count(*) FILTER(WHERE received_before_dispatched)
FROM dw.v_sales_analysis
GROUP BY packed_date_key,dispatched_date_key,category_key,delivery_geography_key,product_key,customer_key,shipping_method_key;
DELETE FROM mart.sales_daily;
INSERT INTO mart.sales_daily
SELECT packed_date_key,category_key,delivery_geography_key,sum(order_count),sum(quantity_sum),
 sum(goods_amount),sum(vat_amount),sum(shipping_fee),sum(total_paid),count(DISTINCT customer_key)
FROM mart.sales_cells GROUP BY packed_date_key,category_key,delivery_geography_key;
DELETE FROM mart.product_daily;
INSERT INTO mart.product_daily
SELECT packed_date_key,product_key,category_key,sum(order_count),sum(quantity_sum),sum(goods_amount),count(DISTINCT customer_key)
FROM mart.sales_cells GROUP BY packed_date_key,product_key,category_key;
DELETE FROM mart.customer_summary;
INSERT INTO mart.customer_summary
SELECT customer_key,sum(order_count),sum(goods_amount),sum(total_paid),min(packed_date_key),max(packed_date_key)
FROM mart.sales_cells GROUP BY customer_key;
DELETE FROM mart.delivery_daily;
INSERT INTO mart.delivery_daily
SELECT dispatched_date_key,shipping_method_key,delivery_geography_key,sum(order_count),sum(delivered_orders),
 sum(delivery_hours_sum),sum(received_before_dispatched_count)
FROM mart.sales_cells GROUP BY dispatched_date_key,shipping_method_key,delivery_geography_key;
DELETE FROM mart.news_daily;
INSERT INTO mart.news_daily
SELECT published_date_key,news_source_key,relevance_level,count(*)
FROM dw.v_news_analysis GROUP BY published_date_key,news_source_key,relevance_level;
DELETE FROM mart.news_membership;
INSERT INTO mart.news_membership
SELECT news_key,category_key,published_date_key,news_source_key,relevance_level,article_weight
FROM dw.v_news_category_analysis;
DELETE FROM mart.news_category_daily;
INSERT INTO mart.news_category_daily
SELECT published_date_key,category_key,news_source_key,relevance_level,count(DISTINCT news_key),sum(article_weight)
FROM mart.news_membership GROUP BY published_date_key,category_key,news_source_key,relevance_level;
