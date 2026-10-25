-- Phase 2 already owns SCD2 columns and exclusion constraints; do not recreate them.
CREATE INDEX IF NOT EXISTS quality_findings_run_rule ON audit.quality_findings(run_id,rule_code,severity);
CREATE INDEX IF NOT EXISTS projection_errors_retry ON audit.projection_errors(state,event_id);
INSERT INTO audit.schema_versions(version) VALUES ('lak-phase5-v1') ON CONFLICT(version) DO NOTHING;
