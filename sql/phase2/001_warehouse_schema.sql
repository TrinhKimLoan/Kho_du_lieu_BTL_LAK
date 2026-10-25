-- New, empty LAK database only. Never apply to the legacy LAK/CommerceInsight DB.
-- Intentionally fails on existing schemas rather than silently reusing old tables.
BEGIN;
CREATE EXTENSION IF NOT EXISTS btree_gist;
CREATE SCHEMA raw;
CREATE SCHEMA staging;
CREATE SCHEMA dw;
CREATE SCHEMA mart;
CREATE SCHEMA audit;
CREATE SCHEMA ml;

CREATE TABLE audit.schema_versions (
    version text PRIMARY KEY,
    installed_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE raw.import_rows (
    file_name text NOT NULL,
    file_sha256 char(64) NOT NULL CHECK (file_sha256 ~ '^[0-9a-f]{64}$'),
    excel_row_number integer NOT NULL CHECK (excel_row_number >= 2),
    entity_type text NOT NULL CHECK (entity_type IN ('customers','products','orders')),
    entity_key text NOT NULL,
    sanitized_payload jsonb NOT NULL,
    redaction_version text NOT NULL,
    imported_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (file_name, file_sha256, excel_row_number)
);

CREATE TABLE raw.cdc_events (
    event_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_epoch uuid NOT NULL,
    topic text NOT NULL,
    partition_id integer NOT NULL CHECK (partition_id >= 0),
    kafka_offset bigint NOT NULL CHECK (kafka_offset >= 0),
    event_type text NOT NULL CHECK (event_type IN ('r','c','u','d','tombstone','BEGIN','END','invalid')),
    entity_type text,
    entity_key text,
    source_tx_id text,
    tx_total_order bigint,
    source_file_number bigint,
    source_position bigint,
    source_row_number bigint,
    key_bytes bytea,
    value_bytes bytea,
    record_key jsonb,
    record_value jsonb,
    content_sha256 char(64) NOT NULL CHECK (content_sha256 ~ '^[0-9a-f]{64}$'),
    captured_at timestamptz NOT NULL DEFAULT now(),
    processed_at timestamptz,
    UNIQUE (source_epoch, topic, partition_id, kafka_offset),
    CHECK (event_type <> 'tombstone' OR value_bytes IS NULL)
);
CREATE INDEX cdc_events_pending ON raw.cdc_events (event_id) WHERE processed_at IS NULL;
CREATE INDEX cdc_events_transaction ON raw.cdc_events (source_epoch, source_tx_id);

CREATE TABLE raw.kafka_checkpoints (
    source_epoch uuid NOT NULL,
    consumer_group text NOT NULL,
    topic text NOT NULL,
    partition_id integer NOT NULL CHECK (partition_id >= 0),
    next_offset bigint NOT NULL CHECK (next_offset >= 0),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (source_epoch, consumer_group, topic, partition_id)
);

CREATE TABLE raw.news_snapshots (
    run_id uuid NOT NULL,
    article_key text NOT NULL,
    origin text NOT NULL CHECK (origin IN ('seed','api','demo')),
    payload jsonb NOT NULL,
    content_sha256 char(64) NOT NULL,
    fetched_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (run_id, article_key)
);

CREATE TABLE staging.customers (
    customer_id text PRIMARY KEY,
    gender text,
    profile_city text,
    profile_district text,
    is_demo boolean NOT NULL,
    source_is_deleted boolean NOT NULL DEFAULT false,
    source_epoch uuid NOT NULL,
    source_file_number bigint NOT NULL CHECK (source_file_number >= 0),
    source_position bigint NOT NULL CHECK (source_position >= 0),
    source_row_number bigint NOT NULL CHECK (source_row_number >= 0),
    tx_total_order bigint NOT NULL CHECK (tx_total_order >= 0),
    last_event_id bigint NOT NULL REFERENCES raw.cdc_events(event_id),
    observed_at timestamptz NOT NULL
);

CREATE TABLE staging.products (
    product_id text PRIMARY KEY,
    product_name text,
    product_group text,
    category_code text,
    catalog_unit_price numeric(18,2),
    product_size_band text,
    is_demo boolean NOT NULL,
    source_is_deleted boolean NOT NULL DEFAULT false,
    source_epoch uuid NOT NULL,
    source_file_number bigint NOT NULL CHECK (source_file_number >= 0),
    source_position bigint NOT NULL CHECK (source_position >= 0),
    source_row_number bigint NOT NULL CHECK (source_row_number >= 0),
    tx_total_order bigint NOT NULL CHECK (tx_total_order >= 0),
    last_event_id bigint NOT NULL REFERENCES raw.cdc_events(event_id),
    observed_at timestamptz NOT NULL
);

-- Staging keeps parseable business anomalies; hard business checks belong to
-- projection gates and the corresponding fact constraints, not silent cleanup.
CREATE TABLE staging.orders (
    order_id text PRIMARY KEY,
    customer_id text,
    product_id text,
    quantity integer,
    transaction_unit_price numeric(18,2),
    goods_amount numeric(20,2),
    vat_amount numeric(20,2),
    shipping_fee numeric(20,2),
    total_paid numeric(20,2),
    shipping_method text,
    quantity_band text,
    warehouse_name text,
    vehicle_type text,
    delivery_city text,
    delivery_district text,
    packed_at timestamp without time zone,
    dispatched_at timestamp without time zone,
    expected_at timestamp without time zone,
    received_at timestamp without time zone,
    is_demo boolean NOT NULL,
    source_is_deleted boolean NOT NULL DEFAULT false,
    source_epoch uuid NOT NULL,
    source_file_number bigint NOT NULL CHECK (source_file_number >= 0),
    source_position bigint NOT NULL CHECK (source_position >= 0),
    source_row_number bigint NOT NULL CHECK (source_row_number >= 0),
    tx_total_order bigint NOT NULL CHECK (tx_total_order >= 0),
    last_event_id bigint NOT NULL REFERENCES raw.cdc_events(event_id),
    observed_at timestamptz NOT NULL
);

CREATE TABLE staging.news_articles (
    article_key text PRIMARY KEY,
    external_id text,
    canonical_url text NOT NULL,
    title text NOT NULL,
    source_domain text,
    published_date date NOT NULL,
    indexed_at timestamptz,
    category_codes text[] NOT NULL DEFAULT '{}',
    relevance_level text NOT NULL CHECK (relevance_level IN ('DIRECT','INDIRECT','IRRELEVANT','UNCLASSIFIED')),
    relevance_reason text,
    quality_status text NOT NULL CHECK (quality_status IN ('candidate','review')),
    rule_version text NOT NULL,
    content_sha256 char(64) NOT NULL,
    origin text NOT NULL CHECK (origin IN ('seed','api','demo')),
    is_demo boolean NOT NULL DEFAULT false,
    is_deleted boolean NOT NULL DEFAULT false,
    first_seen_at timestamptz NOT NULL,
    last_seen_at timestamptz NOT NULL,
    CHECK (last_seen_at >= first_seen_at)
);

CREATE TABLE dw.dim_date (
    date_key integer PRIMARY KEY,
    full_date date UNIQUE,
    year smallint GENERATED ALWAYS AS (extract(year FROM full_date)::smallint) STORED,
    quarter smallint GENERATED ALWAYS AS (extract(quarter FROM full_date)::smallint) STORED,
    month smallint GENERATED ALWAYS AS (extract(month FROM full_date)::smallint) STORED,
    day smallint GENERATED ALWAYS AS (extract(day FROM full_date)::smallint) STORED,
    iso_week smallint GENERATED ALWAYS AS (extract(week FROM full_date)::smallint) STORED,
    iso_weekday smallint GENERATED ALWAYS AS (extract(isodow FROM full_date)::smallint) STORED,
    CHECK ((date_key = 0 AND full_date IS NULL) OR
           (date_key > 0 AND full_date IS NOT NULL AND date_key = to_char(full_date,'YYYYMMDD')::integer))
);

CREATE TABLE dw.dim_geography (
    geography_key bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    geography_code text NOT NULL UNIQUE,
    city text,
    district text,
    CHECK (geography_key = 0 OR (city IS NOT NULL AND district IS NOT NULL))
);

CREATE TABLE dw.dim_category (
    category_key bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    category_code text NOT NULL UNIQUE,
    display_name text NOT NULL
);

CREATE TABLE dw.dim_customer (
    customer_key bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    customer_id text NOT NULL UNIQUE,
    gender text,
    profile_geography_key bigint NOT NULL DEFAULT 0 REFERENCES dw.dim_geography(geography_key),
    is_demo boolean NOT NULL DEFAULT false,
    is_deleted boolean NOT NULL DEFAULT false,
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE dw.dim_product (
    product_key bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    product_id text NOT NULL,
    product_name text NOT NULL,
    product_group text,
    category_code text NOT NULL DEFAULT 'UNKNOWN',
    valid_from timestamptz NOT NULL,
    valid_to timestamptz,
    is_current boolean NOT NULL,
    is_demo boolean NOT NULL DEFAULT false,
    is_deleted boolean NOT NULL DEFAULT false,
    UNIQUE (product_id, valid_from),
    CHECK (valid_to IS NULL OR valid_to > valid_from),
    CHECK (is_current = (valid_to IS NULL)),
    EXCLUDE USING gist (product_id WITH =, tstzrange(valid_from,valid_to,'[)') WITH &&)
);
CREATE UNIQUE INDEX dim_product_one_current ON dw.dim_product(product_id) WHERE is_current;

CREATE TABLE dw.dim_shipping_method (
    shipping_method_key bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    shipping_method_code text NOT NULL UNIQUE,
    display_name text NOT NULL
);

CREATE TABLE dw.dim_news_source (
    news_source_key bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    domain text NOT NULL UNIQUE,
    display_name text NOT NULL
);

INSERT INTO dw.dim_date(date_key, full_date) VALUES (0, NULL);
INSERT INTO dw.dim_geography(geography_key, geography_code) VALUES (0, 'UNKNOWN');
INSERT INTO dw.dim_category(category_key, category_code, display_name) VALUES (0, 'UNKNOWN', 'Chưa biết');
INSERT INTO dw.dim_customer(customer_key, customer_id) VALUES (0, 'UNKNOWN');
INSERT INTO dw.dim_product(product_key, product_id, product_name, valid_from, is_current)
VALUES (0, 'UNKNOWN', 'Chưa biết', '-infinity', true);
INSERT INTO dw.dim_shipping_method(shipping_method_key, shipping_method_code, display_name)
VALUES (0, 'UNKNOWN', 'Chưa biết');
INSERT INTO dw.dim_news_source(news_source_key, domain, display_name) VALUES (0, 'UNKNOWN', 'Chưa biết');

CREATE TABLE dw.fact_sales (
    sales_key bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id text NOT NULL UNIQUE,
    customer_key bigint NOT NULL DEFAULT 0 REFERENCES dw.dim_customer(customer_key),
    product_key bigint NOT NULL DEFAULT 0 REFERENCES dw.dim_product(product_key),
    category_key bigint NOT NULL DEFAULT 0 REFERENCES dw.dim_category(category_key),
    delivery_geography_key bigint NOT NULL DEFAULT 0 REFERENCES dw.dim_geography(geography_key),
    shipping_method_key bigint NOT NULL DEFAULT 0 REFERENCES dw.dim_shipping_method(shipping_method_key),
    packed_date_key integer NOT NULL DEFAULT 0 REFERENCES dw.dim_date(date_key),
    dispatched_date_key integer NOT NULL DEFAULT 0 REFERENCES dw.dim_date(date_key),
    expected_date_key integer NOT NULL DEFAULT 0 REFERENCES dw.dim_date(date_key),
    received_date_key integer NOT NULL DEFAULT 0 REFERENCES dw.dim_date(date_key),
    packed_at timestamp without time zone,
    dispatched_at timestamp without time zone,
    expected_at timestamp without time zone,
    received_at timestamp without time zone,
    quantity integer NOT NULL CHECK (quantity > 0),
    transaction_unit_price numeric(18,2) NOT NULL CHECK (transaction_unit_price > 0),
    goods_amount numeric(20,2) NOT NULL CHECK (goods_amount >= 0),
    vat_amount numeric(20,2) NOT NULL CHECK (vat_amount >= 0),
    shipping_fee numeric(20,2) NOT NULL CHECK (shipping_fee >= 0),
    total_paid numeric(20,2) NOT NULL CHECK (total_paid >= 0),
    quantity_band text,
    warehouse_name text,
    vehicle_type text,
    delivery_hours numeric GENERATED ALWAYS AS
      (CASE WHEN received_at >= dispatched_at THEN extract(epoch FROM (received_at - dispatched_at))/3600 ELSE NULL END) STORED,
    dispatched_before_packed boolean GENERATED ALWAYS AS (dispatched_at < packed_at) STORED,
    expected_before_dispatched boolean GENERATED ALWAYS AS (expected_at < dispatched_at) STORED,
    received_before_dispatched boolean GENERATED ALWAYS AS (received_at < dispatched_at) STORED,
    is_demo boolean NOT NULL DEFAULT false,
    is_deleted boolean NOT NULL DEFAULT false,
    source_epoch uuid NOT NULL,
    last_event_id bigint NOT NULL REFERENCES raw.cdc_events(event_id),
    projected_at timestamptz NOT NULL,
    CHECK (goods_amount = quantity * transaction_unit_price),
    CHECK (vat_amount = round(goods_amount * 0.1, 2)),
    CHECK (total_paid = goods_amount + vat_amount + shipping_fee),
    CHECK (packed_date_key = coalesce(to_char(packed_at,'YYYYMMDD')::integer,0)),
    CHECK (dispatched_date_key = coalesce(to_char(dispatched_at,'YYYYMMDD')::integer,0)),
    CHECK (expected_date_key = coalesce(to_char(expected_at,'YYYYMMDD')::integer,0)),
    CHECK (received_date_key = coalesce(to_char(received_at,'YYYYMMDD')::integer,0))
);
CREATE INDEX fact_sales_customer ON dw.fact_sales(customer_key) WHERE NOT is_deleted;
CREATE INDEX fact_sales_packed ON dw.fact_sales(packed_date_key) WHERE NOT is_deleted;
CREATE INDEX fact_sales_product ON dw.fact_sales(product_key) WHERE NOT is_deleted;
CREATE INDEX fact_sales_dispatched ON dw.fact_sales(dispatched_date_key) WHERE NOT is_deleted;

CREATE TABLE dw.fact_news (
    news_key bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    article_key text NOT NULL UNIQUE,
    published_date_key integer NOT NULL REFERENCES dw.dim_date(date_key),
    news_source_key bigint NOT NULL DEFAULT 0 REFERENCES dw.dim_news_source(news_source_key),
    title text NOT NULL,
    canonical_url text NOT NULL,
    relevance_level text NOT NULL CHECK (relevance_level IN ('DIRECT','INDIRECT','IRRELEVANT','UNCLASSIFIED')),
    relevance_reason text,
    quality_status text NOT NULL CHECK (quality_status IN ('candidate','review')),
    rule_version text NOT NULL,
    origin text NOT NULL CHECK (origin IN ('seed','api','demo')),
    is_demo boolean NOT NULL DEFAULT false,
    is_deleted boolean NOT NULL DEFAULT false,
    first_seen_at timestamptz NOT NULL,
    last_seen_at timestamptz NOT NULL,
    projected_at timestamptz NOT NULL,
    CHECK (last_seen_at >= first_seen_at)
);
CREATE INDEX fact_news_published ON dw.fact_news(published_date_key);
CREATE TABLE dw.bridge_news_category (
    news_key bigint NOT NULL REFERENCES dw.fact_news(news_key),
    category_key bigint NOT NULL REFERENCES dw.dim_category(category_key),
    PRIMARY KEY (news_key, category_key)
);
CREATE INDEX bridge_news_category_category ON dw.bridge_news_category(category_key, news_key);

CREATE VIEW dw.v_sales_analysis AS SELECT * FROM dw.fact_sales WHERE NOT is_deleted AND NOT is_demo;
CREATE VIEW dw.v_news_analysis AS SELECT * FROM dw.fact_news WHERE NOT is_deleted AND NOT is_demo;

CREATE TABLE audit.applied_source_transactions (
    source_epoch uuid NOT NULL,
    source_tx_id text NOT NULL,
    end_event_id bigint NOT NULL REFERENCES raw.cdc_events(event_id),
    expected_data_events integer NOT NULL CHECK (expected_data_events >= 0),
    applied_data_events integer NOT NULL CHECK (applied_data_events >= 0),
    end_topic text NOT NULL,
    end_partition integer NOT NULL CHECK (end_partition = 0),
    end_offset bigint NOT NULL CHECK (end_offset >= 0),
    applied_at timestamptz NOT NULL,
    PRIMARY KEY (source_epoch, source_tx_id),
    CHECK (expected_data_events = applied_data_events)
);
CREATE TABLE audit.pipeline_runs (
    run_id uuid PRIMARY KEY,
    pipeline text NOT NULL,
    status text NOT NULL CHECK (status IN ('RUNNING','SUCCESS','PARTIAL','FAILED')),
    started_at timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz,
    details jsonb NOT NULL DEFAULT '{}'
);
CREATE TABLE audit.quality_findings (
    finding_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id uuid REFERENCES audit.pipeline_runs(run_id),
    event_id bigint REFERENCES raw.cdc_events(event_id),
    entity_type text NOT NULL,
    entity_key text NOT NULL,
    rule_code text NOT NULL,
    severity text NOT NULL CHECK (severity IN ('ERROR','WARNING')),
    detected_at timestamptz NOT NULL DEFAULT now(),
    resolved_at timestamptz,
    details jsonb NOT NULL DEFAULT '{}'
);
CREATE TABLE audit.projection_errors (
    error_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_id bigint NOT NULL REFERENCES raw.cdc_events(event_id),
    error_code text NOT NULL,
    safe_message text NOT NULL,
    attempts integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    state text NOT NULL CHECK (state IN ('OPEN','RETRYING','RESOLVED')),
    first_seen_at timestamptz NOT NULL DEFAULT now(),
    resolved_at timestamptz
);
CREATE TABLE audit.news_coverage (
    month_start date NOT NULL CHECK (extract(day FROM month_start) = 1),
    category_key bigint NOT NULL REFERENCES dw.dim_category(category_key),
    query_signature text NOT NULL,
    origin text NOT NULL CHECK (origin IN ('seed','api')),
    status text NOT NULL CHECK (status IN ('NOT_FETCHED','PARTIAL','COMPLETE','FAILED')),
    observed_at timestamptz NOT NULL,
    details jsonb NOT NULL DEFAULT '{}',
    PRIMARY KEY (month_start, category_key, query_signature, origin)
);

INSERT INTO audit.schema_versions(version) VALUES ('lak-phase2-v1');
COMMIT;
