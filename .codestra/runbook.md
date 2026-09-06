# Middleware integration API runbook

Owner: `codestra-platform`

Confirm `/health/live`, `/health/ready`, `/health/dependencies`, and `/version`. Use the returned correlation ID to inspect the Codestra observability facade. Never copy credentials, connection strings, internal hostnames, or raw tenant payloads into an incident record.

Production changes require a validated provisioning request, independent approval, immutable image digest, SBOM, verified provenance, and a separately authorized deployment operator. The platform API records intent and evidence; it does not directly mutate Caddy, Kong, Keycloak, OpenBao, or telemetry backends.
