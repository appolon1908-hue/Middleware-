# Middleware integration branch architecture

## Purpose

Each external system and major middleware runtime concern has an isolated Git workstream. This prevents Odoo, n8n, Kong, Caddy, identity, database, queue, telephony, messaging, crawler, worker, and monitoring changes from being mixed into one large branch.

These branches are code-review workstreams. They are **not** deployment environments and must never be deployed directly to production.

## Canonical branch set

| Branch | Scope |
|---|---|
| `integration/odoo` | Odoo API client, transactional outbox consumption, lead/campaign/callback/appointment delivery, reconciliation, duplicate-delivery handling, and Odoo adapter tests. |
| `integration/n8n` | Signed inbound/outbound webhooks, workflow template contracts, inactive-by-default workflow exports, replay protection, correlation IDs, and n8n adapter tests. |
| `integration/kong` | Kong services, routes, plugins, OIDC enforcement, mTLS, rate limits, allowlists, request/response transformation, and route smoke tests. |
| `integration/caddy` | Caddy reverse-proxy configuration, TLS, upstream health behavior, security headers, access restrictions, and edge validation. |
| `integration/keycloak` | OIDC/JWKS validation, service accounts, roles, claims, token audience/issuer rules, authorization policy, and identity tests. The canonical issuer remains `https://auth.codestra.co`. |
| `integration/postgresql` | Schema, migrations, least-privilege roles, row-level security, indexes, backup/restore, migration rollback, and PostgreSQL integration tests. |
| `integration/redis` | Queue isolation, idempotency state, locks, leases, cache behavior, retry scheduling, recovery behavior, and Redis integration tests. |
| `integration/vicidial` | Restricted VICIdial adapter client, signed commands, read-back comparison, campaign/agent synchronization, callback/transfer behavior, and write-denial tests. Direct middleware writes to VICIdial tables are prohibited. |
| `integration/jasmin-sms` | Jasmin SMS submission, delivery receipts, inbound messages, signatures, replay protection, suppression, rate limits, and provider reconciliation. |
| `integration/postal-email` | Postal/Klyrow email delivery, inbound events, bounce/complaint handling, suppression, templates, deduplication, and reconciliation. |
| `integration/kyqra-crawler` | Kyqra crawler job submission, result ingestion, tenant/job isolation, import validation, retry/replay behavior, and crawler contract tests. |
| `integration/webhook-inbox-outbox` | Shared durable inbox/outbox primitives, signatures, timestamp bounds, deduplication, leases, retries, dead letters, replay, and audit trails. |
| `integration/workers-scheduler` | Background workers, cron/scheduler jobs, graceful shutdown, concurrency, queue ownership, retry policy, and worker health/readiness. |
| `integration/observability` | Structured logs, metrics, traces, dashboards, alerts, release identity, secret redaction, and operational runbooks. |

## Branch rules

1. Every branch starts from the latest reviewed `main`.
2. No direct commits to `main` for integration work.
3. A branch may change only its declared integration plus the minimum shared contracts required for that integration.
4. Shared primitives used by multiple integrations belong in `integration/webhook-inbox-outbox`, `integration/workers-scheduler`, `integration/postgresql`, or `integration/redis`, rather than being duplicated.
5. Do not copy credentials, live `.env` files, private keys, certificates, database/Redis data, customer payloads, logs, or runtime volumes into any branch.
6. Every integration branch must include tests for authentication, authorization, tenant isolation, idempotency, retry/replay, duplicate handling, failure recovery, and disabled-capability behavior where applicable.
7. External writes remain disabled in staging unless a test explicitly uses a controlled fake or isolated test target.
8. Integration branches may merge only through a pull request after exact-head validation.
9. After merge, delete or reset the completed workstream before beginning unrelated work. Do not let long-lived branches silently drift from `main`.
10. Production deploys only an immutable image built from a reviewed merged SHA. Never deploy an integration branch, mutable tag, or locally edited server checkout.

## Cross-system changes

A change touching several systems must be split whenever practical:

```text
shared contract or persistence change
  -> merge first
system-specific adapter change
  -> rebase on updated main
edge/routing change
  -> merge after upstream behavior is stable
observability change
  -> merge with final metrics and alerts
```

Use stacked pull requests when one integration depends on another. Each PR must state its exact dependency and merge order. Do not combine Odoo, n8n, Kong, Caddy, database, and production activation into one oversized pull request.

## Recommended dependency order

1. `integration/postgresql`
2. `integration/redis`
3. `integration/keycloak`
4. `integration/webhook-inbox-outbox`
5. `integration/workers-scheduler`
6. System adapters: Odoo, n8n, VICIdial, Jasmin SMS, Postal email, and Kyqra crawler
7. `integration/kong`
8. `integration/caddy`
9. `integration/observability`

This order is guidance, not permission to merge untested work. An integration branch may move earlier only when it is demonstrably independent.

## Staging safety baseline

The effective running staging container must fail closed with externally effective capabilities disabled, including:

```text
SEND_EVENTS=false
ENABLE_EXTERNAL_DELIVERY=false
LIVE_WRITE=false
LIVE_WRITES=false
ODOO_WRITE=false
CALLBACK_DISPATCH=false
N8N_DELIVERY_ENABLED=false
VICIDIAL_WRITES_ENABLED=false
EXTERNAL_DIAL_ENABLED=false
PRODUCTION_CALLBACKS_ENABLED=false
N8N_PRODUCTION_WORKFLOWS_ENABLED=false
PRODUCTION_DIALING=DISABLED
```

The current application source must map and enforce the real supported variable names. An example file is not runtime evidence.

## Updating a workstream

Before starting work on an integration branch:

```bash
git fetch origin
git switch integration/<system>
git merge --ff-only origin/main
```

When a branch has unique commits and cannot fast-forward, rebase it in a trusted development environment, resolve conflicts, rerun the complete branch test suite, and force-push only with `--force-with-lease`. The production server remains read-only and must not perform this operation.

## Release flow

```text
integration branch
  -> pull request
  -> exact-head CI and review
  -> merge into protected main
  -> build once from merged SHA
  -> publish immutable digest
  -> staging deployment with writes disabled
  -> integration and rollback evidence
  -> explicit production approval
  -> production deployment of the identical digest
```

Server source paths, Compose project names, service names, health endpoints, and current safety controls must still be confirmed by the read-only runtime discovery before any deployment automation is enabled.
