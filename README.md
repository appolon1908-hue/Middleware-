# Codestra Middleware

This repository is the intended source of truth for Codestra's self-hosted middleware application running on Application Server A.

> **Security notice:** this repository is currently public. Keep it limited to non-secret bootstrap files until its visibility is changed to private. Do not import Codestra middleware source, integration configuration, customer data, credentials, certificates, or operational evidence while it is public.

## Operating model

1. Select the system workstream defined in [`docs/INTEGRATION-BRANCHES.md`](docs/INTEGRATION-BRANCHES.md).
2. Update that branch from the latest reviewed `main`.
3. Change code, tests, migrations, workers, configuration templates, or monitoring definitions only within the declared scope.
4. Open a pull request and pass exact-head CI and review.
5. Merge into protected `main`.
6. Build one immutable image from the protected merged SHA.
7. Deploy that digest to staging with all external effects disabled.
8. Run database, Redis, webhook, Odoo, n8n, telephony, messaging, identity, gateway, monitoring, backup/restore, and rollback tests as applicable.
9. Deploy the identical accepted digest to production only after explicit approval.

`integration/*`, `platform/*`, `core/*`, and `observability/*` are review workstreams, not deployment branches. Never deploy them directly.

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

Kyqra and Beyvra have runtime-verification branches because configuration references exist but their active middleware-host runtime is not fully confirmed. RabbitMQ, Mautic, Postal, Jasmin, Crawlee, and Playwright were not observed on the middleware host and therefore do not have active branches.

## Repository scope

Commit:

- middleware API and worker source;
- tests and database migrations;
- Dockerfiles and non-secret Compose templates;
- non-secret configuration examples;
- CI, validation, deployment, backup, rollback, and operational documentation;
- versioned n8n workflow exports only when they contain no credentials;
- monitoring rules, dashboards, alerts, and exporter configuration without secrets.

Never commit:

- `.env` files, passwords, tokens, private keys, certificates, or live connection strings;
- PostgreSQL or Redis data, dumps, runtime volumes, queues, or dead-letter payloads;
- Odoo, n8n, VICIdial, Asterisk, Telnexa, Klyrow, Postly, Keycloak, Kong, Caddy, or provider credentials;
- production webhook payloads or customer personally identifiable information;
- logs, backups, generated evidence containing secrets, or files edited inside a running container.

## Bootstrap controls

- [`docs/INTEGRATION-BRANCHES.md`](docs/INTEGRATION-BRANCHES.md) defines the complete isolated branch architecture, runtime status, dependency order, and merge rules.
- [`config/integration-branches.json`](config/integration-branches.json) is the machine-readable canonical workstream list.
- [`docs/SERVER-CONNECTION.md`](docs/SERVER-CONNECTION.md) explains how to make the repository private, create a separate read-only deploy key, inventory the live middleware safely, import only authoritative source, and deploy immutable artifacts without restarting unrelated services.
- [`scripts/discover_middleware_runtime.sh`](scripts/discover_middleware_runtime.sh) performs read-only Docker discovery and prints only allowlisted non-secret runtime controls.
- [`scripts/run_ci.sh`](scripts/run_ci.sh) runs bootstrap checks and delegates to `scripts/project_ci.sh` after the actual application source and locked dependency pipeline are imported.
- [`config/preproduction-safety.env.example`](config/preproduction-safety.env.example) records the fail-closed staging baseline. It is not proof that the live application recognizes every variable; the source import must map and enforce the actual controls.

The server must consume reviewed artifacts through read-only credentials. Production must deploy an exact commit SHA or immutable container digest; it must not build from an unreviewed branch or accept manual source edits inside a running container.
