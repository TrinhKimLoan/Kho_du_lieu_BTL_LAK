CREATE TABLE IF NOT EXISTS ml.feature_snapshots (
    snapshot_id text PRIMARY KEY,
    feature_type text NOT NULL CHECK(feature_type IN ('rfm','delivery')),
    reference_date date NOT NULL,
    window_start date,
    source_sha256 char(64) NOT NULL,
    dataset_sha256 char(64) NOT NULL,
    row_count integer NOT NULL,
    contract jsonb NOT NULL,
    observations jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS ml.rfm_features (
    snapshot_id text NOT NULL REFERENCES ml.feature_snapshots(snapshot_id),
    customer_key bigint NOT NULL REFERENCES dw.dim_customer(customer_key),
    customer_id text NOT NULL,
    recency_days integer NOT NULL CHECK(recency_days>=1),
    frequency integer NOT NULL CHECK(frequency>=1),
    monetary numeric(20,2) NOT NULL CHECK(monetary>0),
    last_packed_at timestamp without time zone NOT NULL,
    split text NOT NULL CHECK(split IN ('train','validation','test')),
    row_sha256 char(64) NOT NULL,
    PRIMARY KEY(snapshot_id,customer_key),
    UNIQUE(snapshot_id,customer_id)
);
CREATE TABLE IF NOT EXISTS ml.model_registry (
    model_id text PRIMARY KEY,
    algorithm text NOT NULL CHECK(algorithm IN ('kmeans_rfm','random_forest_delivery')),
    snapshot_id text NOT NULL REFERENCES ml.feature_snapshots(snapshot_id),
    artifact_relpath text NOT NULL,
    manifest_sha256 char(64) NOT NULL,
    metadata jsonb NOT NULL,
    status text NOT NULL CHECK(status IN ('READY','RETIRED')),
    active boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(model_id,snapshot_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS model_one_active ON ml.model_registry(algorithm) WHERE active;
CREATE TABLE IF NOT EXISTS ml.customer_segments (
    model_id text NOT NULL,
    snapshot_id text NOT NULL,
    customer_key bigint NOT NULL,
    cluster_id integer NOT NULL CHECK(cluster_id>=0),
    distance double precision NOT NULL CHECK(distance>=0 AND distance<'Infinity'::double precision),
    business_segment integer NOT NULL CHECK(business_segment BETWEEN 0 AND 7),
    assigned_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY(model_id,customer_key),
    FOREIGN KEY(model_id,snapshot_id) REFERENCES ml.model_registry(model_id,snapshot_id),
    FOREIGN KEY(snapshot_id,customer_key) REFERENCES ml.rfm_features(snapshot_id,customer_key)
);
CREATE TABLE IF NOT EXISTS ml.segment_profiles (
    model_id text NOT NULL REFERENCES ml.model_registry(model_id),
    cluster_id integer NOT NULL,
    display_name text NOT NULL,
    customer_count integer NOT NULL,
    profile jsonb NOT NULL,
    PRIMARY KEY(model_id,cluster_id)
);
INSERT INTO audit.schema_versions(version) VALUES('lak-phase8-v1') ON CONFLICT(version) DO NOTHING;
