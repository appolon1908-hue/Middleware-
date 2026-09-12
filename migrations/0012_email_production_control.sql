BEGIN;

CREATE TABLE IF NOT EXISTS middleware_email_production_policy (
  tenant_id text PRIMARY KEY,
  version bigint NOT NULL CHECK (version >= 1),
  payload jsonb NOT NULL CHECK (jsonb_typeof(payload) = 'object'),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS middleware_email_production_mutations (
  id bigserial PRIMARY KEY,
  tenant_id text NOT NULL,
  action text NOT NULL,
  actor_id text NOT NULL,
  idempotency_key text NOT NULL,
  request_sha256 text NOT NULL CHECK (request_sha256 ~ '^[0-9a-f]{64}$'),
  response_payload jsonb NOT NULL CHECK (jsonb_typeof(response_payload) = 'object'),
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, action, actor_id, idempotency_key)
);

CREATE INDEX IF NOT EXISTS idx_email_production_mutations_tenant_created
  ON middleware_email_production_mutations (tenant_id, created_at DESC, id DESC);

CREATE TABLE IF NOT EXISTS middleware_email_production_audit (
  id bigserial PRIMARY KEY,
  tenant_id text NOT NULL,
  action text NOT NULL,
  actor_id text NOT NULL,
  reason text NOT NULL,
  correlation_id text NOT NULL,
  previous_policy jsonb NOT NULL CHECK (jsonb_typeof(previous_policy) = 'object'),
  new_policy jsonb NOT NULL CHECK (jsonb_typeof(new_policy) = 'object'),
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_email_production_audit_tenant_id
  ON middleware_email_production_audit (tenant_id, id DESC);

CREATE INDEX IF NOT EXISTS idx_email_production_audit_correlation
  ON middleware_email_production_audit (tenant_id, correlation_id);

CREATE TABLE IF NOT EXISTS middleware_email_quota_buckets (
  tenant_id text NOT NULL,
  window_kind text NOT NULL CHECK (window_kind IN ('minute', 'hour', 'day')),
  bucket_start timestamptz NOT NULL,
  used bigint NOT NULL DEFAULT 0 CHECK (used >= 0),
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, window_kind, bucket_start)
);

CREATE INDEX IF NOT EXISTS idx_email_quota_buckets_updated
  ON middleware_email_quota_buckets (updated_at);

COMMIT;
