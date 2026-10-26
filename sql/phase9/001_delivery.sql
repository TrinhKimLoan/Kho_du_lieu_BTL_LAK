CREATE TABLE IF NOT EXISTS ml.delivery_features (
    snapshot_id text NOT NULL REFERENCES ml.feature_snapshots(snapshot_id),
    order_id text NOT NULL,
    dispatched_at timestamp without time zone NOT NULL,
    received_at timestamp without time zone NOT NULL,
    split text NOT NULL CHECK(split IN ('train','validation','test')),
    target_hours double precision NOT NULL CHECK(target_hours>=0 AND target_hours<'Infinity'::double precision),
    features jsonb NOT NULL,
    row_sha256 char(64) NOT NULL,
    PRIMARY KEY(snapshot_id,order_id),
    CHECK(received_at>=dispatched_at)
);
CREATE TABLE IF NOT EXISTS ml.delivery_predictions (
    model_id text NOT NULL,
    snapshot_id text NOT NULL,
    order_id text NOT NULL,
    predicted_hours double precision NOT NULL CHECK(predicted_hours>=0 AND predicted_hours<'Infinity'::double precision),
    baseline_hours double precision NOT NULL CHECK(baseline_hours>=0 AND baseline_hours<'Infinity'::double precision),
    actual_hours double precision NOT NULL CHECK(actual_hours>=0 AND actual_hours<'Infinity'::double precision),
    error_hours double precision NOT NULL CHECK(abs(error_hours)<'Infinity'::double precision),
    predicted_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY(model_id,order_id),
    FOREIGN KEY(model_id,snapshot_id) REFERENCES ml.model_registry(model_id,snapshot_id),
    FOREIGN KEY(snapshot_id,order_id) REFERENCES ml.delivery_features(snapshot_id,order_id)
);
INSERT INTO audit.schema_versions(version) VALUES('lak-phase9-v1') ON CONFLICT(version) DO NOTHING;
