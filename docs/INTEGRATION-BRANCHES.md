# Middleware integration branch architecture

## Purpose

Every middleware-connected system and each major platform, shared-core, testing, or observability concern has an isolated Git workstream. This prevents Odoo, n8n, telephony, messaging, marketing, identity, gateway, proxy, persistence, queue, crawler, browser testing, and monitoring changes from being mixed into one oversized branch.

These branches are code-review workstreams. They are **not** deployment environments and must never be deployed directly to staging or production.

A branch existing in GitHub does not prove that a corresponding service is installed, running, owned by this repository, or approved for deployment. Runtime status must be verified independently through the read-only server audit.

## Runtime status meanings

| Status | Meaning |
|---|---|
| `declared_active_scope` | The middleware architecture declares an active integration or platform responsibility. Live paths still require runtime confirmation before deployment. |
| `required_shared_primitive` | The capability is a required shared middleware concern, regardless of which external systems are active. |
| `configured_worker_not_observed` | Configuration references exist, but the available audit did not observe the expected worker. |
| `configured_runtime_not_confirmed` | Configuration references exist, but the active runtime and ownership are not confirmed. |
| `not_observed_on_middleware_host_verification_only` | A dedicated branch exists because the system may be integrated later or may run on another host, but it was not observed on the middleware host. Only contracts, tests, inventory, and verification work are allowed until its runtime and ownership are proven. |

## Active application and integration workstreams

| Branch | System | Scope |
|---|---|---|
| `integration/odoo-19` | Odoo 19 | CRM, contacts, leads, activities, campaigns, callbacks, appointments, delivery results, reconciliation, and Odoo adapter tests. |
| `integration/n8n` | n8n | Workflow automation, normalized event processing, signed webhooks, inactive-by-default workflow exports, replay protection, and adapter tests. |
| `integration/vicidial` | VICIdial | Campaigns, agents, dispositions, call results, callbacks, restricted adapter commands, read-back comparison, and write-denial tests. Direct middleware writes to VICIdial tables are prohibited. |
| `integration/asterisk-pjsip` | Asterisk/PJSIP | Endpoints, extensions, trunks, call infrastructure, health, authentication, routing contracts, and telephony tests. |
| `integration/telnexa-sms` | Telnexa | SMS submission, delivery status callbacks, inbound events, signatures, replay protection, suppression, rate limits, and reconciliation. |
| `integration/klyrow-email` | Klyrow | Email submission, lifecycle events, bounces, complaints, suppression, templates, deduplication, callbacks, and reconciliation. |
| `integration/postly-social` | Postly | Social-media polling, publishing and delivery events, account isolation, retries, callbacks, and reconciliation. |
| `integration/keycloak` | Keycloak | OIDC/JWKS validation, service identities, roles, claims, audience and issuer enforcement, authorization policy, and identity tests. The canonical issuer is `https://auth.codestra.co`. |

## Active platform workstreams

| Branch | Platform | Scope |
|---|---|---|
| `platform/kong` | Kong | API services, routes, plugins, authentication, mTLS, rate limits, allowlists, transformations, and gateway smoke tests. |
| `platform/caddy` | Caddy | Public HTTPS, reverse proxy, TLS, upstream health behavior, security headers, access restrictions, and edge validation. |
| `platform/postgresql` | PostgreSQL | Durable records, event ledger, outbox, audit, mappings, schema, migrations, least-privilege roles, backup/restore, and rollback tests. |
| `platform/redis` | Redis | Temporary queues, caching, leases, idempotency state, locks, retry scheduling, recovery behavior, and Redis integration tests. |

## Verification-only system workstreams

The following branches now exist as isolated workspaces, but their services were not observed on the middleware host. They do not authorize installation, migration, deployment, traffic routing, or capability activation.

| Branch | System | Allowed scope before runtime confirmation |
|---|---|---|
| `platform/rabbitmq` | RabbitMQ | AMQP contracts, exchange/queue/binding design, publisher confirms, consumer acknowledgements, dead-letter and retry policy, TLS/authentication requirements, compatibility tests, and runtime inventory. |
| `integration/mautic` | Mautic | Contact, campaign, segment, API and webhook contracts, authentication, idempotent synchronization, event mapping, reconciliation tests, and runtime inventory. |
| `integration/postal-email` | Postal | Middleware-facing email API and lifecycle-event contracts, bounces, complaints, suppression, signatures, deduplication, reconciliation tests, and runtime inventory. |
| `integration/jasmin-sms` | Jasmin | Middleware-facing HTTP/SMPP submission and delivery-receipt contracts, inbound messages, authentication, replay protection, suppression, rate limits, reconciliation tests, and runtime inventory. |
| `integration/crawlee` | Crawlee | Crawl-job contracts, policies, tenant/job isolation, queue ownership, result ingestion, retry/replay behavior, deterministic fixtures, and runtime inventory. |
| `testing/playwright` | Playwright | Browser end-to-end tests, authentication tests, synthetic no-write canaries, deterministic test data, trace/artifact controls, and verification of where Playwright is allowed to run. |

Postal and Jasmin may be underlying provider-host components while Klyrow and Telnexa remain the middleware-facing product integrations. Their branches should contain middleware adapter contracts and tests unless a separate architecture decision explicitly assigns the underlying service source and deployment configuration to this repository.

RabbitMQ must not replace Redis queues or be introduced as an additional broker merely because its branch exists. A broker decision requires runtime evidence, an architecture record, migration and rollback design, queue-semantics tests, operational ownership, and explicit approval.

Playwright is a test workstream, not a production middleware service. Browser tests must use no-write or isolated test targets unless a specific controlled test explicitly authorizes writes.

## Shared middleware core

| Branch | Scope |
|---|---|
| `core/event-ledger-outbox` | Canonical normalized events, durable event ledger, transactional outbox, leases, retries, dead letters, audit, and reconciliation. |
| `core/webhook-inbox-replay` | Signed inbound inbox, timestamp bounds, replay protection, idempotency, deduplication, quarantine, and controlled replay. |
| `core/workers-scheduler` | Background workers, schedulers, concurrency, queue ownership, graceful shutdown, retries, health, readiness, and restart behavior. |

## Operations and monitoring workstreams

| Branch | Component | Scope |
|---|---|---|
| `observability/prometheus` | Prometheus | Metrics collection, scrape configuration, recording rules, retention, and Prometheus validation. |
| `observability/grafana` | Grafana | Dashboards, data sources, access controls, release identity panels, and provisioning. |
| `observability/alertmanager` | Alertmanager | Alert routing, grouping, inhibition, receiver contracts, escalation, and notification tests. |
| `observability/loki` | Loki | Central logs, labels, retention, queries, tenant boundaries, secret redaction, and validation. |
| `observability/blackbox-exporter` | Blackbox Exporter | HTTP, HTTPS, TCP and TLS probes, target definitions, authentication-safe checks, and alerts. |
| `observability/node-exporter` | Node Exporter | Host metrics, filesystem and network collection, collector restrictions, and host alerts. |
| `observability/cadvisor` | cAdvisor | Container resource metrics, labels, access restrictions, retention, and container alerts. |
| `observability/postgresql-exporter` | PostgreSQL Exporter | Least-privilege monitoring role, database metrics, custom queries, and alerts. |
| `observability/redis-exporter` | Redis Exporter | Exporter authentication, queue and memory metrics, replication metrics, and alerts. |

## Other configured but runtime-unverified workstreams

| Branch | Status | Allowed work |
|---|---|---|
| `integration/kyqra` | Configuration mentions Kyqra, but the available audit did not observe a running Kyqra worker on the middleware host. | Contracts, tests, and runtime verification only until the running service, endpoint, owner, source path, and deployment path are confirmed. |
| `integration/beyvra` | Configuration mentions Beyvra, but its active middleware-host runtime was not confirmed by the available audit. | Contracts, tests, and runtime verification only until the active service, endpoint, owner, source path, and deployment path are confirmed. |

No verification-only branch authorizes deployment or activation merely because configuration references or a Git branch exist.

## Branch rules

1. Every workstream starts from the same latest reviewed `main` SHA.
2. No direct integration commits go to `main`.
3. A branch may change only its declared system plus the minimum shared contract required for that system.
4. Shared event, inbox/outbox, worker, PostgreSQL, Redis, or broker behavior belongs in the corresponding `core/*` or `platform/*` branch rather than being duplicated.
5. Do not commit credentials, live `.env` files, private keys, certificates, database or queue data, customer payloads, logs, packet captures, browser traces containing secrets, or runtime volumes.
6. Every branch must include applicable tests for authentication, authorization, tenant isolation, idempotency, retry/replay, duplicates, failure recovery, and disabled-capability behavior.
7. External writes remain disabled in staging unless a test uses a controlled fake or isolated test target.
8. Verification-only branches may not add a production service, route, port, credential, database, queue, or external capability without an approved architecture and activation record.
9. Workstream branches merge only through pull requests after exact-head validation.
10. After merge, update or recreate the workstream from current `main` before unrelated work begins. Do not allow silent long-term drift.
11. Production deploys only an immutable image built from a reviewed merged SHA. Never deploy `integration/*`, `platform/*`, `core/*`, `observability/*`, or `testing/*` directly.
12. The production server retains read-only Git access and may not rebase, force-push, resolve branch conflicts, or push source changes.

## Cross-system changes

Split multi-system work whenever practical:

```text
shared event, broker, or persistence contract
  -> merge first
system-specific adapter
  -> update from new main and merge next
Kong route and policy
  -> merge after upstream contract stabilizes
Caddy edge configuration
  -> merge after Kong/upstream validation
browser tests and synthetic canaries
  -> merge after the tested behavior stabilizes
metrics, dashboards and alerts
  -> merge with the final observable behavior
```

Use stacked pull requests when dependencies are unavoidable. Every pull request must state its exact dependency and merge order. Do not combine Odoo, n8n, telephony, SMS, email, marketing, crawler, broker, Kong, Caddy, database changes, browser testing, and production activation in one pull request.

## Recommended dependency order

1. `platform/postgresql`
2. `platform/redis`
3. `integration/keycloak`
4. `core/event-ledger-outbox`
5. `core/webhook-inbox-replay`
6. `core/workers-scheduler`
7. Confirmed application adapters: Odoo 19, n8n, VICIdial, Asterisk/PJSIP, Telnexa, Klyrow, and Postly
8. Verification-only adapters: Mautic, Postal, Jasmin, and Crawlee, only after runtime and ownership confirmation
9. `platform/rabbitmq`, only after an approved broker architecture decision and migration/rollback evidence
10. `platform/kong`
11. `platform/caddy`
12. `testing/playwright` against staging or isolated targets
13. Exporters, Prometheus, Loki, Alertmanager, and Grafana
14. Kyqra or Beyvra only after runtime verification

This order is guidance, not approval to merge or deploy untested work.

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

Any RabbitMQ, Mautic, Postal, Jasmin, Crawlee, or browser-write capability introduced later must have an explicit fail-closed control and a test proving that omission or malformed values do not enable it.

The actual middleware source must map and enforce its supported variable names. An example file is not runtime evidence.

## Updating a workstream

Before beginning work:

```bash
git fetch origin
git switch <workstream-branch>
git merge --ff-only origin/main
```

When a branch has unique commits and cannot fast-forward, rebase it in a trusted development environment, resolve conflicts, rerun the complete branch test suite, and force-push only with `--force-with-lease`. Never perform this operation from the production server.

## Release flow

```text
workstream branch
  -> pull request
  -> exact-head CI and review
  -> merge into protected main
  -> build once from protected merged SHA
  -> publish immutable image digest
  -> staging deployment with all external effects disabled
  -> integration, backup/restore and rollback evidence
  -> explicit production approval
  -> production deployment of the identical digest
```

Server source paths, Compose project names, service names, health endpoints, and effective safety controls must still be confirmed through read-only runtime discovery before deployment automation is enabled.
