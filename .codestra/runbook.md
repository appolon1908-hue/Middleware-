# Middleware integration API runbook

Owner: `codestra-platform`

Confirm `/health/live`, `/health/ready`, `/health/dependencies`, and `/version`. Use the returned correlation ID to inspect the Codestra observability facade. Never copy credentials, connection strings, internal hostnames, or raw tenant payloads into an incident record.

Production changes require a validated provisioning request, independent approval, immutable image digest, SBOM, verified provenance, and a separately authorized deployment operator. The platform API records intent and evidence; it does not directly mutate Caddy, Kong, Keycloak, OpenBao, or telemetry backends.

Rollback uses the provisioning request's reviewed rollback action and the preceding digest-pinned
release. Stop apply workers first, preserve audit evidence, and never roll back by changing a mutable
tag or bypassing the migration compatibility gate.
