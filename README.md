# Codestra Middleware

This repository is the intended source of truth for Codestra's self-hosted middleware application running on Application Server A.

> **Security notice:** this repository is currently public. Keep it limited to non-secret bootstrap files until its visibility is changed to private. Do not import Codestra middleware source, integration configuration, customer data, credentials, certificates, or operational evidence while it is public.

## Operating model

1. Select the system workstream defined in [`docs/INTEGRATION-BRANCHES.md`](docs/INTEGRATION-BRANCHES.md).
2. Read its dependencies and communication connections in [`config/connectivity-map.json`](config/connectivity-map.json).
3. Update the workstream from the latest reviewed `main` and confirm `main` remains an ancestor of the active work.
4. Change code, tests, migrations, workers, configuration templates, contracts, or monitoring definitions only within the declared scope.
5. Open a pull request and pass exact-head CI, dependency-graph validation, communication-contract validation, and review.
6. Merge into protected `main`.
7. Build one immutable image from the protected merged SHA.
8. Deploy that digest to staging with all external effects disabled.
9. Run database, queue, webhook, Odoo, n8n, telephony, messaging, identity, gateway, crawler, browser, monitoring, backup/restore, and rollback tests as applicable.
10. Deploy the identical accepted digest to production only after explicit approval.

`integration/*`, `platform/*`, `core/*`, `observability/*`, and `testing/*` are review workstreams, not deployment branches. Never deploy them directly.

## Shared communication baseline

The canonical cross-system workstream is:

```text
core/integration-contracts
```

It owns the common event envelope, HTTP and webhook conventions, authentication and tenant metadata, correlation and causation rules, idempotency, compatibility policy, error semantics, observability names, and connection registry.

Every other workstream depends directly or transitively on this contract branch. Shared contract changes merge first; affected branches are then refreshed from the new `main` before implementation continues.

The repository validates:

- every workstream has an explicit dependency declaration;
- the dependency graph is acyclic;
- every workstream connects to `core/integration-contracts`;
- every system participates in at least one declared communication connection;
- every connection declares transport, authentication, reliability, ownership, runtime status, and contract;
- verification-only systems cannot be represented as active runtime connections.

See [`docs/CONNECTIVITY-AND-COMMUNICATION.md`](docs/CONNECTIVITY-AND-COMMUNICATION.md).

## Managed and connected systems

Application integrations:

- Odoo 19
- n8n
- VICIdial
- Asterisk/PJSIP
- Telnexa SMS
- Klyrow email
- Postly social media
- Keycloak

Platform dependencies:

- Kong
- Caddy
- PostgreSQL
- Redis

Operations and monitoring:

- Prometheus
- Grafana
- Alertmanager
- Loki
- Blackbox Exporter
- Node Exporter
- cAdvisor
- PostgreSQL Exporter
- Redis Exporter

## Runtime-verification workstreams

Dedicated branches also exist for systems that were not observed as running services on the middleware host:

- `platform/rabbitmq`
- `integration/mautic`
- `integration/postal-email`
- `integration/jasmin-sms`
- `integration/crawlee`
- `testing/playwright`

These branches isolate contracts, tests, inventory, and future integration work. Their existence does not prove installation or authorize deployment. Runtime location, ownership, source path, credentials, network exposure, data responsibilities, migration strategy, rollback, and activation approval must be established first.

Kyqra and Beyvra also have runtime-verification branches because configuration references exist but their active middleware-host runtime is not fully confirmed.

## Repository scope

Commit:

- middleware API and worker source;
- tests and database migrations;
- Dockerfiles and non-secret Compose templates;
- non-secret configuration examples;
- canonical API, event, webhook, identity, and observability contracts;
- CI, validation, deployment, backup, rollback, and operational documentation;
- versioned n8n workflow exports only when they contain no credentials;
- monitoring rules, dashboards, alerts, and exporter configuration without secrets;
- contract and test definitions for verification-only integrations.

Never commit:

- `.env` files, passwords, tokens, private keys, certificates, or live connection strings;
- PostgreSQL, Redis, RabbitMQ, queue, outbox, inbox, dead-letter, or runtime data;
- Odoo, n8n, VICIdial, Asterisk, Telnexa, Klyrow, Postly, Mautic, Postal, Jasmin, Keycloak, Kong, Caddy, crawler, or provider credentials;
- production webhook payloads or customer personally identifiable information;
- browser traces, screenshots, videos, or HAR files containing credentials or customer data;
- logs, backups, generated evidence containing secrets, or files edited inside a running container.

## Bootstrap controls

- [`docs/INTEGRATION-BRANCHES.md`](docs/INTEGRATION-BRANCHES.md) defines the isolated branch architecture, runtime status, dependency order, and merge rules.
- [`docs/CONNECTIVITY-AND-COMMUNICATION.md`](docs/CONNECTIVITY-AND-COMMUNICATION.md) defines cross-system topology, shared communication rules, and branch synchronization.
- [`config/integration-branches.json`](config/integration-branches.json) is the machine-readable canonical workstream list.
- [`config/connectivity-map.json`](config/connectivity-map.json) is the machine-readable dependency and connection registry.
- [`contracts/event-envelope.schema.json`](contracts/event-envelope.schema.json) defines the canonical asynchronous event envelope.
- [`contracts/http-conventions.md`](contracts/http-conventions.md) defines authentication, tenant, idempotency, webhook, retry, health, and error behavior.
- [`contracts/observability-conventions.md`](contracts/observability-conventions.md) defines release identity, metrics, logs, tracing, dashboards, and alerts.
- [`docs/SERVER-CONNECTION.md`](docs/SERVER-CONNECTION.md) explains how to make the repository private, create a separate read-only deploy key, inventory the live middleware safely, import only authoritative source, and deploy immutable artifacts without restarting unrelated services.
- [`scripts/discover_middleware_runtime.sh`](scripts/discover_middleware_runtime.sh) performs read-only Docker discovery and prints only allowlisted non-secret runtime controls.
- [`scripts/run_ci.sh`](scripts/run_ci.sh) runs bootstrap checks and delegates to `scripts/project_ci.sh` after the actual application source and locked dependency pipeline are imported.
- [`config/preproduction-safety.env.example`](config/preproduction-safety.env.example) records the fail-closed staging baseline. It is not proof that the live application recognizes every variable; the source import must map and enforce the actual controls.

The server must consume reviewed artifacts through read-only credentials. Production must deploy an exact commit SHA or immutable container digest; it must not build from an unreviewed branch or accept manual source edits inside a running container.
