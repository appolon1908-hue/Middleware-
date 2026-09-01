# Middleware API completion matrix

This matrix is generated from the canonical FastAPI entrypoint and reviewed
domain modules. `IMPLEMENTED` means executable behavior exists in the runtime;
source-only documentation or an OpenAPI declaration is not sufficient.

The machine-readable authoritative matrix is
`config/api-completion-matrix.yaml`. At the current checkpoint, the platform,
command, communication, and intake routes are implemented. The remaining
operations, durability, policy, reconciliation, quarantine, adapter, and
webhook groups are explicitly marked `MISSING` until their domain services,
persistence, authorization, tests, and runtime registration are delivered.
