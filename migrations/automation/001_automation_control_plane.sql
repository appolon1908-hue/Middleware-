BEGIN;

CREATE TABLE IF NOT EXISTS automation_jobs (
    job_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    workflow_key TEXT NOT NULL,
    workflow_version TEXT NOT NULL,
    workflow_family TEXT NOT NULL,
    delivery_token_hash TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('PENDING', 'CLAIMED', 'COMPLETED', 'FAILED')),
    attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    lease_token_hash TEXT,
    execution_id TEXT,
    leased_until TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS automation_job_steps (
    step_id BIGSERIAL PRIMARY KEY,
    job_id TEXT NOT NULL REFERENCES automation_jobs(job_id) ON DELETE CASCADE,
    step_key TEXT NOT NULL,
    status TEXT NOT NULL,
    execution_id TEXT NOT NULL,
    data JSONB NOT NULL DEFAULT '{}'::jsonb,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS automation_commands (
    command_id TEXT PRIMARY KEY,
    idempotency_key_hash TEXT NOT NULL UNIQUE,
    fingerprint TEXT NOT NULL,
    job_id TEXT NOT NULL REFERENCES automation_jobs(job_id) ON DELETE RESTRICT,
    tenant_id TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    workflow_key TEXT NOT NULL,
    workflow_version TEXT NOT NULL,
    step_key TEXT NOT NULL,
    execution_id TEXT NOT NULL,
    command_type TEXT NOT NULL,
    scope TEXT NOT NULL,
    client TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('DRY_RUN_ACCEPTED', 'PENDING_ADAPTER', 'SUCCEEDED', 'FAILED', 'REJECTED')),
    dry_run BOOLEAN NOT NULL DEFAULT true,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    adapter_result JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS automation_dead_letters (
    dead_letter_id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL REFERENCES automation_jobs(job_id) ON DELETE RESTRICT,
    tenant_id TEXT NOT NULL,
    workflow_key TEXT NOT NULL,
    workflow_version TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('OPEN', 'REPLAY_REQUESTED', 'CLOSED')),
    safe_replay BOOLEAN NOT NULL DEFAULT false,
    version INTEGER NOT NULL DEFAULT 1 CHECK (version >= 1),
    error JSONB NOT NULL DEFAULT '{}'::jsonb,
    replay_reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS automation_reconciliation_runs (
    reconciliation_run_id TEXT PRIMARY KEY,
    state TEXT NOT NULL CHECK (state IN ('STARTED', 'COMPLETED', 'FAILED')),
    requested_by TEXT NOT NULL,
    checked_commands INTEGER NOT NULL DEFAULT 0 CHECK (checked_commands >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS automation_dispatch_outbox (
    outbox_id BIGSERIAL PRIMARY KEY,
    aggregate_type TEXT NOT NULL,
    aggregate_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload JSONB NOT NULL,
    published_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_automation_jobs_state ON automation_jobs(state);
CREATE INDEX IF NOT EXISTS idx_automation_jobs_tenant ON automation_jobs(tenant_id);
CREATE INDEX IF NOT EXISTS idx_automation_commands_job ON automation_commands(job_id);
CREATE INDEX IF NOT EXISTS idx_automation_commands_state ON automation_commands(state);
CREATE INDEX IF NOT EXISTS idx_automation_dead_letters_state ON automation_dead_letters(state);
CREATE INDEX IF NOT EXISTS idx_automation_outbox_unpublished ON automation_dispatch_outbox(outbox_id) WHERE published_at IS NULL;

COMMIT;
