# Service catalog monitoring state

Middleware is the operational control plane: it owns the service catalog,
monitoring desired and observed state, certification state, incidents,
Alertmanager ingestion, delivery intent and read-back, correlation, audit and
reconciliation. It is never a metrics, log or trace database, and it never
stores a secret value.

## Catalog descriptor (Alembic `0067_service_catalog_monitoring_state`)

`POST /platform/v1/services` and `PATCH /platform/v1/services/{service_id}`
accept, in addition to the existing fields, the monitoring descriptor the
integrated monitoring design proposes:

| Group | Fields |
| --- | --- |
| Identity | `deployment_id`, `host_id`, `instance_id` (a stable `service_id` stays separate from where it runs) |
| Origins | `public_origin`, `private_origin` (declared from deployment configuration, never derived from a repository name) |
| Contract paths | `liveness_path`, `readiness_path` (defaults to `health_path`), `metrics_path`, `openapi_path` |
| Collection owners | `metrics_profile` (`prometheus`/`otel`/`not-applicable`), `logs_profile` (`alloy`/`otel`/`not-applicable`), `traces_profile` (`otel`/`not-applicable`) |
| Bindings | `prometheus_target_id`, `blackbox_target_id`, `grafana_dashboard_ids` |
| Expected release identity | `expected_git_sha`, `expected_image_digest`, `expected_config_digest`, `expected_migration_head` |
| Observed release identity | `observed_git_sha`, `observed_image_digest`, `observed_config_digest`, `observed_migration_head` — written only by `POST .../monitoring-state/observations` |
| Secret references | `secret_references[]` — `app.secret_reference.SecretReference` objects (pointer only) |
| State | `monitoring_state`, `monitoring_state_reason`, `last_observed_at`, `last_observation_source`, `last_certified_at`, `last_certified_by` |

Every transition is written to `platform_service_monitoring_audit` with the
actor, correlation id and the sha256 of the evidence that justified it. The
migration's downgrade refuses to drop the audit table while it holds rows.

## Monitoring states

```text
unregistered → registered → pending → synced → certified
                              ↓         ↓         ↓
                            unknown   drifted   (re-derived on every observation)
                            applying / failed   (reported by the collector)
```

| State | Meaning |
| --- | --- |
| `unregistered` | not in the catalog |
| `registered` | approved descriptor imported; no expected release identity, or nothing observed yet without one |
| `pending` | expected release identity declared; no runtime observation yet |
| `applying` | an authorized collector reported an apply in progress |
| `synced` | every declared expected field equals fresh (≤ 15 min) runtime evidence |
| `drifted` | fresh evidence differs from the expected identity (fields named in the reason) |
| `failed` | the collector reported a failed apply or read-back |
| `unknown` | evidence stale, partial or absent for a declared expectation |
| `certified` | granted by a `platform_admin`/`platform_reviewer` with runtime proof; kept only while synced and fresh |

`app.platform_catalog_monitoring.derive_state` is the single implementation.
A Git descriptor alone never yields `synced`; an HTTP 200 never yields
`synced`; certification never comes from configuration existing.

## Endpoints (private network, not edge-routed; same class as the catalog CRUD)

| Operation | Scope / role | Purpose |
| --- | --- | --- |
| `GET /platform/v1/services/{id}/monitoring-state` | `platform.services.read` | expected vs observed per field, derived state, freshness, bindings, references (never values), last 20 audit rows |
| `POST /platform/v1/services/{id}/monitoring-state/observations` | `platform.runtime.observe` (`platform_operator`/`platform_admin`), `X-Correlation-ID` required | collector read-back of git SHA / image / config / migration head; refuses observations older than the last one (delayed evidence never overwrites newer state); `status: applying|failed` supported |
| `POST /platform/v1/services/{id}/monitoring-state/certification` | `platform.services.write` (`platform_admin`/`platform_reviewer`), `X-Correlation-ID` required | 409 with the blocker list unless synced, fresh, targets and dashboards bound, and every applicable evidence flag (`health_endpoints`, `metrics_scraped`, `logs_received`, `traces_received`, `alert_route_test`, `dashboards_bound`, `secret_references_reconciled`) is true |

Changing an expected field through `PATCH` re-derives the state; a certified
service whose desired release changes falls back until fresh evidence matches.

## Per-component reconciliation

`GET /platform/v1/sync/status` and `POST /platform/v1/sync/reconciliations`
now return `component_states` beside the existing `state`: each required
component (Prometheus targets/rules, Alertmanager configuration, Grafana
datasources/dashboards, Loki, Tempo, Alloy, OpenBao health, exporters,
Blackbox) is `pending`, `applying`, `synced`, `drifted`, `failed` or
`unknown`, from a fresh `config` observation carrying the active
configuration digest (and optionally `status`). A component without a fresh
digest read-back is `unknown`, never `synced`.

## Secret references

`contracts/secrets/secret-reference.v1.schema.json` is the OpenBao-owned
contract vendored byte-for-byte and pinned by canonical sha256
(`scripts/validate_secret_reference_contract.py [--openbao-repo …]`).
`SecretReference` rejects, at any depth, `value`, `password`, `token`,
`private_key`, `client_secret`, `secret`, `secret_value`, `unseal_key`,
`recovery_key`, `root_token`, any `*_password|*_token|*_secret` key and any
secret-shaped string; it requires `secret_ref` to lie inside its own
environment, derives `reference_uri = openbao:// + secret_ref`, and the
catalog additionally requires the environment to be one the service declares.
Middleware may hold `rotation_status`, hashed lease metadata and
reconciliation timestamps; no Middleware API resolves a reference.

## Alertmanager → incidents

Unchanged and reused: `POST /v1/integrations/alertmanager/events` and
`/status-events` with fingerprint deduplication, idempotency keys, source
timestamps, suppression reconciliation and tenant/environment isolation
(`tests/test_observability_alerts.py`: a replayed delivery returns the same
`incident_id` with `duplicate: true`). Incident lifecycle stays under
`/v1/observability/incidents/*`.
