CREATE TABLE IF NOT EXISTS ml.inference_config (
 singleton boolean PRIMARY KEY DEFAULT true CHECK(singleton),
 rfm_model_id text NOT NULL REFERENCES ml.model_registry(model_id),
 delivery_model_id text NOT NULL REFERENCES ml.model_registry(model_id),
 reference_date date NOT NULL,
 configured_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS ml.inference_jobs (
 job_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 event_key text NOT NULL, kind text NOT NULL CHECK(kind IN ('RFM','DELIVERY')),
 entity_key text NOT NULL, is_demo boolean NOT NULL, model_id text NOT NULL REFERENCES ml.model_registry(model_id),
 reference_date date NOT NULL, payload jsonb NOT NULL,
 state text NOT NULL DEFAULT 'PENDING' CHECK(state IN ('PENDING','RETRY','DONE','FAILED')),
 attempts integer NOT NULL DEFAULT 0, available_at timestamptz NOT NULL DEFAULT now(),
 safe_error text, enqueued_at timestamptz NOT NULL DEFAULT now(), finished_at timestamptz,
 UNIQUE(event_key,kind,entity_key,model_id,reference_date)
);
CREATE INDEX IF NOT EXISTS inference_pending ON ml.inference_jobs(job_id) WHERE state IN ('PENDING','RETRY');
CREATE TABLE IF NOT EXISTS ml.inference_receipts (
 job_id bigint PRIMARY KEY REFERENCES ml.inference_jobs(job_id), result jsonb NOT NULL, processed_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS ml.rfm_assignment_history (
 job_id bigint PRIMARY KEY REFERENCES ml.inference_jobs(job_id), customer_key bigint NOT NULL,
 is_demo boolean NOT NULL, model_id text NOT NULL REFERENCES ml.model_registry(model_id), reference_date date NOT NULL,
 input jsonb NOT NULL, input_sha256 text NOT NULL, cluster_id integer,
 state text NOT NULL CHECK(state IN ('ASSIGNED','NO_HISTORY','NO_POSITIVE_VALUE')),
 assigned_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS ml.rfm_current_assignments (
 customer_key bigint NOT NULL, is_demo boolean NOT NULL, model_id text NOT NULL, reference_date date NOT NULL,
 job_id bigint NOT NULL REFERENCES ml.rfm_assignment_history(job_id),
 PRIMARY KEY(customer_key,is_demo,model_id,reference_date)
);
CREATE TABLE IF NOT EXISTS ml.live_delivery_predictions (
 prediction_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 order_id text NOT NULL, is_demo boolean NOT NULL, model_id text NOT NULL REFERENCES ml.model_registry(model_id),
 job_id bigint NOT NULL UNIQUE REFERENCES ml.inference_jobs(job_id),
 dispatched_at timestamp without time zone NOT NULL, input jsonb NOT NULL, input_sha256 text NOT NULL,
 predicted_hours double precision NOT NULL CHECK(predicted_hours>=0 AND predicted_hours<'Infinity'::double precision),
 observed_at timestamptz NOT NULL, predicted_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(order_id,is_demo)
);
CREATE TABLE IF NOT EXISTS ml.delivery_outcome_history (
 job_id bigint PRIMARY KEY REFERENCES ml.inference_jobs(job_id),
 prediction_id bigint NOT NULL REFERENCES ml.live_delivery_predictions(prediction_id),
 received_at timestamp without time zone,
 state text NOT NULL CHECK(state IN ('RECEIVED','PENDING','DELETED','INVALID_TIME','DISPATCH_CORRECTED')),
 actual_hours double precision, error_hours double precision, recorded_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS ml.rfm_reference_history (
 reference_date date PRIMARY KEY, previous_date date, reason text NOT NULL, changed_at timestamptz NOT NULL DEFAULT now()
);
CREATE OR REPLACE FUNCTION ml.enqueue_inference_fact() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE cfg ml.inference_config%ROWTYPE; event_key_value text; inputs jsonb;
BEGIN
 SELECT * INTO cfg FROM ml.inference_config WHERE singleton;
 IF NOT FOUND THEN RETURN NEW; END IF;
 event_key_value := 'cdc:' || NEW.source_epoch::text || ':' || NEW.last_event_id::text;
 INSERT INTO ml.inference_jobs(event_key,kind,entity_key,is_demo,model_id,reference_date,payload)
 VALUES(event_key_value,'RFM',NEW.customer_key::text,NEW.is_demo,cfg.rfm_model_id,cfg.reference_date,'{}') ON CONFLICT DO NOTHING;
 IF TG_OP='UPDATE' THEN
  IF OLD.customer_key<>NEW.customer_key OR OLD.is_demo<>NEW.is_demo THEN
   INSERT INTO ml.inference_jobs(event_key,kind,entity_key,is_demo,model_id,reference_date,payload)
   VALUES(event_key_value || ':old','RFM',OLD.customer_key::text,OLD.is_demo,cfg.rfm_model_id,cfg.reference_date,'{}') ON CONFLICT DO NOTHING;
  END IF;
 END IF;
 SELECT jsonb_build_object('order_id',NEW.order_id,'is_deleted',NEW.is_deleted,'dispatched_at',NEW.dispatched_at,
 'received_at',NEW.received_at,'observed_at',now(), 'features',jsonb_build_object(
 'quantity',NEW.quantity,'goods_amount',NEW.goods_amount,'quantity_band',NEW.quantity_band,'warehouse_name',NEW.warehouse_name,
 'vehicle_type',NEW.vehicle_type,'shipping_method',s.shipping_method_code,'delivery_district',g.district)) INTO inputs
 FROM dw.dim_shipping_method s CROSS JOIN dw.dim_geography g
 WHERE s.shipping_method_key=NEW.shipping_method_key AND g.geography_key=NEW.delivery_geography_key;
 IF inputs IS NULL THEN RAISE EXCEPTION 'Missing inference dimension'; END IF;
 INSERT INTO ml.inference_jobs(event_key,kind,entity_key,is_demo,model_id,reference_date,payload)
 VALUES(event_key_value,'DELIVERY',NEW.order_id,NEW.is_demo,cfg.delivery_model_id,cfg.reference_date,inputs) ON CONFLICT DO NOTHING;
 RETURN NEW;
END $$;
CREATE OR REPLACE TRIGGER enqueue_ml_after_projection AFTER INSERT OR UPDATE ON dw.fact_sales
 FOR EACH ROW EXECUTE FUNCTION ml.enqueue_inference_fact();
INSERT INTO audit.schema_versions(version) VALUES('lak-phase10-v1') ON CONFLICT(version) DO NOTHING;

CREATE OR REPLACE FUNCTION ml.protect_initial_prediction() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'Initial prediction is immutable; append outcome instead'; END $$;
CREATE OR REPLACE TRIGGER protect_initial_prediction BEFORE UPDATE OR DELETE ON ml.live_delivery_predictions
 FOR EACH ROW EXECUTE FUNCTION ml.protect_initial_prediction();
