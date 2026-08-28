# Codestra Middleware

This repository is the source of truth for reviewed middleware contracts and Git workstreams connecting Codestra applications, public sites, provider-host services, messaging, telephony, crawlers, identity, persistence, and monitoring.

> **Security notice:** this repository is currently public. Runtime source and tests must remain non-secret and environment-neutral. Never commit credentials, certificates, customer data, private configuration, or operational evidence.

## Operating model

1. Select the declared workstream in [`docs/INTEGRATION-BRANCHES.md`](docs/INTEGRATION-BRANCHES.md) or the supplemental site registry in [`architecture/workstreams.py`](architecture/workstreams.py).
2. Read its dependencies and communication links in [`config/connectivity-map.json`](config/connectivity-map.json) and [`architecture/site_architecture.py`](architecture/site_architecture.py).
3. Refresh the branch from the latest reviewed `main`.
4. Change only the declared component and the minimum required shared contracts.
5. Open a pull request and pass exact-head repository, workstream, connectivity, site-route, lead-intake, and project tests.
6. Merge into protected `main`.
7. Build one immutable artifact from the merged SHA.
8. Deploy that digest to staging with external effects disabled.
9. Run authentication, tenant-isolation, duplicate, replay, migration, integration, backup/restore, and rollback tests.
10. Deploy the identical accepted digest to production only after explicit approval.

`site/*`, `integration/*`, `platform/*`, `operations/*`, `core/*`, `observability/*`, and `testing/*` are review workstreams, not deployment branches.

## Canonical communication layer

```text
core/integration-contracts
```

This branch owns common event, HTTP, webhook, provider-transport, identity, tenant, correlation, causation, idempotency, compatibility, error, and observability rules.

Every other workstream depends directly or transitively on it. CI rejects disconnected branches, dependency cycles, unknown communication links, missing authentication, missing reliability behavior, missing contracts, and verification-only links represented as active.

The executable intake runtime persists each accepted signed event and its NATS JetStream outbox record in one PostgreSQL transaction. The outbox worker publishes only canonical `codestra.events.*` subjects and requires an explicit production activation identity plus a mounted NATS credential. Temporal is the declared durable workflow plane. RabbitMQ is not a central Codestra bus; it remains inside the Klyrow and Telnexa provider boundaries.

That same intake transaction appends a tenant-scoped, hash-chained canonical
event to a database-enforced immutable ledger. See
[`docs/IMMUTABLE-EVENT-LEDGER.md`](docs/IMMUTABLE-EVENT-LEDGER.md).

Critical Temporal workflows are implemented for reconciliation, delayed callbacks, provisioning with compensation, and operator-approved dead-letter recovery. See [`docs/TEMPORAL-WORKFLOWS.md`](docs/TEMPORAL-WORKFLOWS.md).

The sole durable event and command shapes live under `contracts/platform`; the
runtime validates against those files directly. Provider wire formats are
normalized projections, not alternate ledgers. See
[`docs/CANONICAL-CONTRACTS.md`](docs/CANONICAL-CONTRACTS.md).

Effectful requests use the tenant-scoped PostgreSQL command ledger and
`codestra.command-execution.v1` workflow. A command cannot become complete until
provider read-back matches its durable intent. See
[`docs/COMMAND-LEDGER.md`](docs/COMMAND-LEDGER.md).

## Application-server sites

Caddy currently exposes workstreams for:

```text
site/codestra                  codestra.co and www redirect
site/codestra-auth             auth.codestra.co — degraded HTTP 502
site/codestra-social           social.codestra.co / Postiz
site/codestra-ai               ai.codestra.co
site/beyvra                    public, www, platform, API, admin, staging
site/booked4seasons            root active; www TLS handshake degraded
site/breero                    production and staging frontends and APIs
```

`platform/caddy` owns the edge. `operations/application-host` owns route inventory, safe restart boundaries, host health, backup references, and change records.

## Provider-host stacks

The provider-host architecture adds aggregate site workstreams:

```text
site/klyrow
site/telnexa
site/kyqra-crawler
site/private-app-integration
site/codestra-business-scrapper
operations/provider-host
platform/nginx-provider
platform/mariadb
```

Klyrow includes its gateway/API, worker, billing API/worker/scheduler, SMTP relay, Mautic, Postal, RabbitMQ, PostgreSQL, MariaDB, Prometheus, Grafana, and public route contracts.

Telnexa includes Jasmin SMS, billing, Keycloak, RabbitMQ, Redis, PostgreSQL, Prometheus, Node Exporter, public routes, and internal mTLS access.

Kyqra includes the crawler API, HTTP worker, browser worker, callback worker, PostgreSQL, Redis, and `crawler.kyqra.com`.

The private integration gateway remains loopback/internal-mTLS only. The Codestra Business Scrapper source at `/opt/codestra-business-scrapper` remains recorded as not deployed.

See [`docs/SITE-ARCHITECTURE.md`](docs/SITE-ARCHITECTURE.md).

## Forms, crawler results, and scraper results to Odoo

The only approved write path is:

```text
website form / crawler result / approved scraper result
                    -> edge or private integration gateway
                    -> durable signed inbox
                    -> core/lead-intake-normalization
                    -> consent, suppression, provenance, dedupe, review policy
                    -> transactional outbox
                    -> integration/odoo-19
                    -> Odoo CRM
```

No site, crawler, scraper, n8n workflow, provider service, or browser test writes directly to Odoo.

Public forms may create or update `new` leads after validation, consent, and suppression checks. Crawler and scraper discoveries enter Odoo as `review_pending` with `review_required=true` and `allow_external_contact=false`.

See:

- [`contracts/lead-intake.schema.json`](contracts/lead-intake.schema.json)
- [`contracts/odoo-lead-command.schema.json`](contracts/odoo-lead-command.schema.json)
- [`docs/LEAD-INGESTION-TO-ODOO.md`](docs/LEAD-INGESTION-TO-ODOO.md)

## Repository scope

Commit only application source, workers, tests, migrations, locked dependencies, Dockerfiles, non-secret templates, contracts, route registries, credential-free workflow exports, monitoring configuration, and operational documentation.

Never commit:

- `.env`, passwords, tokens, private keys, certificates, or live connection strings;
- PostgreSQL, MariaDB, Redis, RabbitMQ, inbox, outbox, dead-letter, session, or runtime data;
- Odoo, n8n, telephony, SMS, email, marketing, crawler, identity, gateway, or provider credentials;
- production payloads or customer personally identifiable information;
- browser traces, screenshots, videos, or HAR files containing credentials or customer data;
- logs, backups, or secret-bearing evidence;
- files edited inside a running production container.

## Canonical controls

- [`config/integration-branches.json`](config/integration-branches.json) — base workstream manifest and synchronization policy.
- [`architecture/workstreams.py`](architecture/workstreams.py) — supplemental site/provider workstreams and runtime-status updates.
- [`architecture/routes.py`](architecture/routes.py) — Caddy/Nginx routes, stack membership, and lead sources.
- [`architecture/site_architecture.py`](architecture/site_architecture.py) — supplemental dependency, communication, stack, and Odoo-intake graph.
- [`config/connectivity-map.json`](config/connectivity-map.json) — base dependency and communication graph.
- [`contracts/event-envelope.schema.json`](contracts/event-envelope.schema.json) — canonical asynchronous event.
- [`contracts/http-conventions.md`](contracts/http-conventions.md) — HTTP, identity, idempotency, webhook, retry, health, and error rules.
- [`contracts/provider-transport-conventions.md`](contracts/provider-transport-conventions.md) — Caddy/Nginx, mTLS, RabbitMQ, SMTP, SMS, database, and provider transport rules.
- [`contracts/observability-conventions.md`](contracts/observability-conventions.md) — release identity, metrics, logs, traces, dashboards, and alerts.
- [`docs/SERVER-CONNECTION.md`](docs/SERVER-CONNECTION.md) — read-only server/Git connection and safe source import.
- [`scripts/discover_middleware_runtime.sh`](scripts/discover_middleware_runtime.sh) — read-only middleware-host inventory.
- [`scripts/audit_all_workstream_sync.py`](scripts/audit_all_workstream_sync.py) — base and supplemental branch synchronization audit.
