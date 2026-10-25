CREATE TABLE IF NOT EXISTS raw.news_pages (
    page_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id uuid NOT NULL REFERENCES audit.pipeline_runs(run_id),
    query_group text NOT NULL,
    page_number integer NOT NULL CHECK(page_number>0),
    origin text NOT NULL CHECK(origin IN ('seed','api','demo')),
    request_parameters jsonb NOT NULL,
    payload jsonb NOT NULL,
    payload_sha256 char(64) NOT NULL,
    collected_at timestamptz NOT NULL DEFAULT now(),
    processed_at timestamptz,
    processing_error text,
    UNIQUE(run_id,query_group,page_number)
);
CREATE TABLE IF NOT EXISTS raw.news_observations (
    snapshot_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    page_id bigint NOT NULL REFERENCES raw.news_pages(page_id),
    row_number integer NOT NULL,
    article_key text,
    payload jsonb NOT NULL,
    content_hash char(64),
    validation_error text,
    UNIQUE(page_id,row_number)
);
ALTER TABLE staging.news_articles ADD COLUMN IF NOT EXISTS last_snapshot_id bigint REFERENCES raw.news_observations(snapshot_id);
CREATE UNIQUE INDEX IF NOT EXISTS news_articles_canonical_url ON staging.news_articles(canonical_url);
CREATE TABLE IF NOT EXISTS audit.news_changes (
    change_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id uuid NOT NULL REFERENCES audit.pipeline_runs(run_id),
    snapshot_id bigint NOT NULL UNIQUE REFERENCES raw.news_observations(snapshot_id),
    article_key text NOT NULL,
    change_type text NOT NULL CHECK(change_type IN ('NEW','UPDATED','UNCHANGED','SKIPPED_SEED')),
    previous_hash char(64),
    current_hash char(64) NOT NULL,
    changed_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS audit.news_fetch_windows (
    run_id uuid NOT NULL REFERENCES audit.pipeline_runs(run_id),
    query_group text NOT NULL,
    query_signature char(64) NOT NULL,
    start_date date NOT NULL,
    end_date date NOT NULL,
    status text NOT NULL CHECK(status IN ('COMPLETE','PARTIAL','FAILED')),
    pages integer NOT NULL DEFAULT 0,
    rows_seen integer NOT NULL DEFAULT 0,
    invalid_rows integer NOT NULL DEFAULT 0,
    reason text,
    PRIMARY KEY(run_id,query_group)
);
CREATE INDEX IF NOT EXISTS news_snapshots_article ON raw.news_observations(article_key,snapshot_id);
CREATE INDEX IF NOT EXISTS news_changes_article ON audit.news_changes(article_key,change_id);
CREATE OR REPLACE VIEW dw.v_news_category_analysis AS
SELECT n.*,b.category_key,1.0/count(*) OVER(PARTITION BY n.news_key) AS article_weight
FROM dw.v_news_analysis n JOIN dw.bridge_news_category b USING(news_key)
WHERE n.relevance_level IN ('DIRECT','INDIRECT');
INSERT INTO audit.schema_versions(version) VALUES('lak-phase6-v1') ON CONFLICT(version) DO NOTHING;
