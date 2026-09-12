# Monitoring integration — Middleware-

This repository is included in the shared design for **63 repositories and 17 monitoring components**. Its assigned profile is `runtime-or-website`. Runtime coverage is **unverified** until release and telemetry evidence are recorded.

- [Complete architecture and rollout design](https://github.com/appolon1908-hue/Infustruction-repo/blob/afeea11b86d296874ec12ce6e8615400240bc72f/INTEGRATED-MONITORING-DESIGN.md)
- [36-operation Middleware implementation](https://github.com/appolon1908-hue/Middleware-/tree/cedaa23b89f84f365ae6789413411c3f01516952/app/monitoring)
- [Executable API contract](https://raw.githubusercontent.com/appolon1908-hue/Middleware-/cedaa23b89f84f365ae6789413411c3f01516952/contracts/observability/integrated-monitoring.openapi.json)
- Local machine-readable onboarding record: [monitoring-integration.v1.json](monitoring-integration.v1.json)

Middleware owns the monitoring API and remains the cross-system operational write boundary. Prometheus owns metrics, Loki logs, Tempo traces, Alertmanager routing, Backstage catalog discovery, Sentry application errors and Wazuh security observations. Grafana provides operational drilldowns. These responsibilities extend the existing collection pipeline without creating another writer or duplicating collectors.

Before activation, enumerate this repository's deployable service units, approved environments, health/metrics paths and release OpenAPI artifacts. Register each service with tenant and deployment identity; source-only libraries and configuration repositories use CI/release/dependency evidence instead of invented health URLs. Empty `service_ids` deliberately means mapping is outstanding.

The release controller mounts reviewed configuration and artifacts in Middleware. An authorized collector posts observations and heartbeats with an idempotency key, correlation ID, monotonic sequence and observation time. Use the coverage endpoint to identify missing metrics/logs/traces; timestamps older than 90 seconds are stale. The synchronization endpoint compares approved configuration with runtime evidence and does not deploy changes.

Keep native backends private. Send UI reads through authenticated Middleware/BFF routes, never browser-held backend credentials. Use release-mounted secrets, approved targets/query templates, tenant and campaign scopes, and structured redacted telemetry. Service registration, green CI and successful ingestion are distinct from verified production coverage.

Acceptance requires the exact source CI result, approved immutable release, registered service/endpoint contracts, fresh telemetry, private authentication, a synthetic alert and recovery evidence. Production activation remains separate. This commit adds the repository's design/onboarding record; it does not instrument or deploy its application.


## Kyyow observability → Odoo projection

The canonical cross-repository contract is [contracts/observability/odoo-sync.v1.json](contracts/observability/odoo-sync.v1.json). Middleware owns the authenticated API boundary and the durable `odoo_result_delivery` queue; Odoo owns the business records.

- `POST /v1/observability/kpis` accepts a bounded, hashed KPI snapshot and queues Odoo delivery.
- `POST /v1/observability/incidents` accepts versioned Alertmanager incident state and queues the Odoo incident projection.
- `GET /v1/observability/kpis`, `/kpis/{event_id}`, and `/odoo-sync` expose tenant-scoped projection and delivery status.
- Alertmanager status changes use the same incident identity and queue; acknowledgements, resolutions, and reopens do not create a second business incident.
- Prometheus, Alertmanager, Grafana, exporters, Loki, Tempo, Superset, and OpenBao do not write Odoo directly.

Activation stays fail-closed until OIDC credentials, tenant allowlists, endpoint-registry approval, Odoo ORM routes, and release evidence are present.
