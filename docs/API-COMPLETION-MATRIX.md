# Middleware API completion matrix

This matrix is generated from the canonical FastAPI entrypoint and reviewed
domain modules. `IMPLEMENTED` means executable behavior exists in the runtime;
source-only documentation or an OpenAPI declaration is not sufficient.

The machine-readable authoritative matrix is
`config/api-completion-matrix.yaml`. At the current checkpoint, the platform,
command, tenant-scoped durable operation control, communication, and intake
routes are implemented. Operation reads enforce each configured caller's
`status_scope`; cancellation and reconciliation enforce that caller's
`command_scope`. All require a bearer token for the `middleware-api` audience
and a matching `X-Tenant-ID`; mutations additionally require
`X-Correlation-ID`, `Idempotency-Key`, and `expected_version`. The remaining
durability, policy, reconciliation administration, quarantine, adapter, and
webhook groups are explicitly marked `MISSING` until their domain services,
persistence, authorization, tests, and runtime registration are delivered.
