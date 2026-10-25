-- Synthetic fixtures only. All fixture changes are rolled back.
BEGIN;
DO $checks$
DECLARE
    event_key bigint;
    old_product bigint;
    cat_cpu bigint;
    cat_ram bigint;
    news_one bigint;
    news_two bigint;
    actual_amount numeric;
    actual_count bigint;
    actual_hours numeric;
BEGIN
    IF (SELECT count(*) FROM audit.schema_versions WHERE version = 'lak-phase2-v1') <> 1 THEN
        RAISE EXCEPTION 'Missing schema marker';
    END IF;
    IF (SELECT count(*) FROM dw.dim_date WHERE date_key=0) <> 1
       OR (SELECT count(*) FROM dw.dim_geography WHERE geography_key=0) <> 1
       OR (SELECT count(*) FROM dw.dim_category WHERE category_key=0) <> 1
       OR (SELECT count(*) FROM dw.dim_customer WHERE customer_key=0) <> 1
       OR (SELECT count(*) FROM dw.dim_product WHERE product_key=0) <> 1
       OR (SELECT count(*) FROM dw.dim_shipping_method WHERE shipping_method_key=0) <> 1
       OR (SELECT count(*) FROM dw.dim_news_source WHERE news_source_key=0) <> 1 THEN
        RAISE EXCEPTION 'Unknown member is missing';
    END IF;
    RAISE NOTICE 'PASS seven unknown dimension members';

    INSERT INTO raw.cdc_events(source_epoch,topic,partition_id,kafka_offset,event_type,content_sha256)
    VALUES ('00000000-0000-0000-0000-000000000001','fixture.orders',0,0,'r',repeat('a',64))
    RETURNING event_id INTO event_key;
    BEGIN
        INSERT INTO raw.cdc_events(source_epoch,topic,partition_id,kafka_offset,event_type,content_sha256)
        VALUES ('00000000-0000-0000-0000-000000000001','fixture.orders',0,0,'r',repeat('a',64));
        RAISE EXCEPTION 'Duplicate Kafka coordinate accepted';
    EXCEPTION WHEN unique_violation THEN NULL;
    END;
    RAISE NOTICE 'PASS unique raw Kafka coordinate';

    INSERT INTO dw.dim_date(date_key,full_date) VALUES
        (20250101,'2025-01-01'),(20250102,'2025-01-02'),(20250103,'2025-01-03');
    IF (SELECT year <> 2025 OR quarter <> 1 OR month <> 1 OR day <> 1
        FROM dw.dim_date WHERE date_key=20250101) THEN
        RAISE EXCEPTION 'Date hierarchy does not match date';
    END IF;
    INSERT INTO dw.dim_category(category_code,display_name) VALUES ('FIXTURE_CPU','Fixture CPU') RETURNING category_key INTO cat_cpu;
    INSERT INTO dw.dim_category(category_code,display_name) VALUES ('FIXTURE_RAM','Fixture RAM') RETURNING category_key INTO cat_ram;
    INSERT INTO dw.dim_product(product_id,product_name,category_code,valid_from,is_current)
    VALUES ('FIXTURE_PRODUCT','Fixture product v1','FIXTURE_CPU','2026-01-01T00:00:00Z',true)
    RETURNING product_key INTO old_product;

    INSERT INTO dw.fact_sales(order_id,product_key,category_key,packed_date_key,dispatched_date_key,received_date_key,
        packed_at,dispatched_at,received_at,quantity,transaction_unit_price,goods_amount,vat_amount,
        shipping_fee,total_paid,source_epoch,last_event_id,projected_at)
    VALUES ('FIXTURE_ORDER',old_product,cat_cpu,20250101,20250102,20250103,
        '2025-01-01 08:00:00','2025-01-02 09:00:00','2025-01-03 09:00:00',
        2,50,100,10,5,115,'00000000-0000-0000-0000-000000000001',event_key,now());
    SELECT delivery_hours INTO actual_hours FROM dw.fact_sales WHERE order_id='FIXTURE_ORDER';
    IF actual_hours IS DISTINCT FROM 24 THEN RAISE EXCEPTION 'Delivery hours incorrect'; END IF;
    RAISE NOTICE 'PASS sales grain, money fields, date roles and delivery hours';

    BEGIN
        UPDATE dw.fact_sales SET total_paid=116 WHERE order_id='FIXTURE_ORDER';
        RAISE EXCEPTION 'Bad total accepted';
    EXCEPTION WHEN check_violation THEN NULL;
    END;
    BEGIN
        UPDATE dw.fact_sales SET customer_key=99999999 WHERE order_id='FIXTURE_ORDER';
        RAISE EXCEPTION 'Orphan customer accepted';
    EXCEPTION WHEN foreign_key_violation THEN NULL;
    END;
    BEGIN
        UPDATE dw.fact_sales SET packed_date_key=20250102 WHERE order_id='FIXTURE_ORDER';
        RAISE EXCEPTION 'Mismatched role date accepted';
    EXCEPTION WHEN check_violation THEN NULL;
    END;
    RAISE NOTICE 'PASS rejection of bad money, orphan FK and inconsistent date key';

    UPDATE dw.fact_sales SET received_date_key=20250101,received_at='2025-01-01 09:00:00'
    WHERE order_id='FIXTURE_ORDER';
    IF NOT (SELECT received_before_dispatched AND delivery_hours IS NULL
            FROM dw.fact_sales WHERE order_id='FIXTURE_ORDER') THEN
        RAISE EXCEPTION 'Invalid shipping target was not flagged and withheld';
    END IF;
    UPDATE dw.fact_sales SET received_date_key=20250103,received_at='2025-01-03 09:00:00'
    WHERE order_id='FIXTURE_ORDER';
    RAISE NOTICE 'PASS anomalous timestamps preserve sales but withhold invalid ML target';

    BEGIN
        INSERT INTO dw.dim_product(product_id,product_name,category_code,valid_from,valid_to,is_current)
        VALUES ('FIXTURE_PRODUCT','Overlapping','FIXTURE_CPU','2026-01-02T00:00:00Z','2026-01-03T00:00:00Z',false);
        RAISE EXCEPTION 'Overlapping SCD2 interval accepted';
    EXCEPTION WHEN exclusion_violation THEN NULL;
    END;
    UPDATE dw.dim_product SET valid_to='2026-02-01T00:00:00Z',is_current=false WHERE product_key=old_product;
    INSERT INTO dw.dim_product(product_id,product_name,category_code,valid_from,is_current)
    VALUES ('FIXTURE_PRODUCT','Fixture product v2','FIXTURE_RAM','2026-02-01T00:00:00Z',true);
    IF (SELECT count(*) FROM dw.dim_product WHERE product_id='FIXTURE_PRODUCT' AND is_current) <> 1
       OR (SELECT product_key FROM dw.fact_sales WHERE order_id='FIXTURE_ORDER') <> old_product THEN
        RAISE EXCEPTION 'SCD2 boundary or existing fact linkage failed';
    END IF;
    RAISE NOTICE 'PASS SCD2 overlap rejection, adjacent boundary and retained fact version';

    UPDATE dw.fact_sales SET is_deleted=true WHERE order_id='FIXTURE_ORDER';
    IF EXISTS (SELECT 1 FROM dw.v_sales_analysis WHERE order_id='FIXTURE_ORDER') THEN
        RAISE EXCEPTION 'Deleted sale leaked into analysis';
    END IF;
    UPDATE dw.fact_sales SET is_deleted=false,is_demo=true WHERE order_id='FIXTURE_ORDER';
    IF EXISTS (SELECT 1 FROM dw.v_sales_analysis WHERE order_id='FIXTURE_ORDER') THEN
        RAISE EXCEPTION 'Demo sale leaked into analysis';
    END IF;
    IF (SELECT total_paid FROM dw.fact_sales WHERE order_id='FIXTURE_ORDER') <> 115 THEN
        RAISE EXCEPTION 'Soft deletion changed stored historical amount';
    END IF;
    UPDATE dw.fact_sales SET is_demo=false WHERE order_id='FIXTURE_ORDER';
    RAISE NOTICE 'PASS soft-delete and demo exclusion without erasing stored facts';

    INSERT INTO dw.fact_news(article_key,published_date_key,title,canonical_url,relevance_level,
        quality_status,rule_version,origin,first_seen_at,last_seen_at,projected_at)
    VALUES ('FIXTURE_NEWS_1',20250101,'Fixture news 1','https://example.invalid/fixture/1',
        'DIRECT','candidate','fixture-v1','seed',now(),now(),now()) RETURNING news_key INTO news_one;
    INSERT INTO dw.fact_news(article_key,published_date_key,title,canonical_url,relevance_level,
        quality_status,rule_version,origin,first_seen_at,last_seen_at,projected_at)
    VALUES ('FIXTURE_NEWS_2',20250101,'Fixture news 2','https://example.invalid/fixture/2',
        'DIRECT','candidate','fixture-v1','seed',now(),now(),now()) RETURNING news_key INTO news_two;
    INSERT INTO dw.bridge_news_category(news_key,category_key)
    VALUES (news_one,cat_cpu),(news_one,cat_ram),(news_two,cat_cpu);
    BEGIN
        INSERT INTO dw.bridge_news_category(news_key,category_key) VALUES (news_one,cat_cpu);
        RAISE EXCEPTION 'Duplicate news/category accepted';
    EXCEPTION WHEN unique_violation THEN NULL;
    END;
    WITH sales AS (
        SELECT f.category_key,sum(f.goods_amount) AS goods
        FROM dw.v_sales_analysis f
        GROUP BY f.category_key
    ), news AS (
        SELECT b.category_key,count(DISTINCT n.news_key) AS articles
        FROM dw.v_news_analysis n JOIN dw.bridge_news_category b ON b.news_key=n.news_key
        GROUP BY b.category_key
    )
    SELECT s.goods,n.articles INTO actual_amount,actual_count FROM sales s
    LEFT JOIN news n ON n.category_key=s.category_key WHERE s.category_key=cat_cpu;
    IF actual_amount IS DISTINCT FROM 100 OR actual_count IS DISTINCT FROM 2 THEN
        RAISE EXCEPTION 'Preaggregated sales/news join multiplied money or articles';
    END IF;
    IF (SELECT count(DISTINCT news_key) FROM dw.bridge_news_category) <> 2 THEN
        RAISE EXCEPTION 'Distinct news count failed';
    END IF;
    RAISE NOTICE 'PASS bridge uniqueness and aggregation before cross-fact join';

    BEGIN
        INSERT INTO audit.applied_source_transactions(source_epoch,source_tx_id,end_event_id,
            expected_data_events,applied_data_events,end_topic,end_partition,end_offset,applied_at)
        VALUES ('00000000-0000-0000-0000-000000000001','fixture-tx',event_key,2,1,'fixture.transaction',0,1,now());
        RAISE EXCEPTION 'Incomplete applied transaction ledger accepted';
    EXCEPTION WHEN check_violation THEN NULL;
    END;
    RAISE NOTICE 'PASS ledger count constraint (not a CDC worker integration test)';
END;
$checks$;
ROLLBACK;
SELECT 'PHASE 2 POSTGRES CHECKS PASSED' AS result;
