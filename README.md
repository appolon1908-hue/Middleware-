# Codestra Middleware

This repository is the intended source of truth for Codestra's self-hosted middleware application running on Application Server A.

> **Security notice:** this repository is currently public. Keep it limited to non-secret bootstrap files until its visibility is changed to private. Do not import Codestra middleware source, integration configuration, customer data, credentials, certificates, or operational evidence while it is public.

## Operating model

1. Select the integration workstream defined in [`docs/INTEGRATION-BRANCHES.md`](docs/INTEGRATION-BRANCHES.md).
2. Update that system's branch from the latest reviewed `main`.
3. Change application code, tests, database migrations, workers, or non-secret deployment templates only within the declared branch scope.
4. Open a pull request and pass exact-head CI and review.
5. Deploy the reviewed merged commit SHA to staging with every external-write capability disabled.
6. Run database, Redis, webhook, Odoo, n8n, VICIdial, authentication, idempotency, retry, and rollback tests as applicable.
7. Build and publish an immutable image for the accepted merged SHA.
8. Deploy the exact accepted image digest to production after explicit approval.

Integration branches are review workstreams, not deployment branches. Never deploy `integration/*` directly.

## Repository scope

Commit:

- middleware API and worker source;
- tests and database migrations;
- Dockerfiles and non-secret Compose templates;
- non-secret configuration examples;
- CI, validation, deployment, backup, rollback, and operational documentation;
- versioned n8n workflow exports only when they contain no credentials.

Never commit:

- `.env` files, passwords, tokens, private keys, certificates, or live connection strings;
- PostgreSQL or Redis data, dumps, runtime volumes, queues, or dead-letter payloads;
- Odoo, n8n, VICIdial, Keycloak, Kong, or provider credentials;
- production webhook payloads or customer personally identifiable information;
- logs, backups, generated evidence containing secrets, or files edited inside a running container.

## Bootstrap controls

- [`docs/INTEGRATION-BRANCHES.md`](docs/INTEGRATION-BRANCHES.md) defines isolated workstreams for Odoo, n8n, Kong, Caddy, Keycloak, PostgreSQL, Redis, VICIdial, Jasmin SMS, Postal email, Kyqra crawler, webhook inbox/outbox, workers, and observability.
- [`docs/SERVER-CONNECTION.md`](docs/SERVER-CONNECTION.md) explains how to make the repository private, create a separate read-only deploy key, inventory the live middleware safely, import only authoritative source, and deploy immutable artifacts without restarting unrelated services.
- [`scripts/discover_middleware_runtime.sh`](scripts/discover_middleware_runtime.sh) performs read-only Docker discovery and prints only allowlisted non-secret runtime controls.
- [`scripts/run_ci.sh`](scripts/run_ci.sh) runs bootstrap checks and delegates to `scripts/project_ci.sh` after the actual application source and locked dependency pipeline are imported.
- [`config/preproduction-safety.env.example`](config/preproduction-safety.env.example) records the fail-closed staging baseline. It is not proof that the live application recognizes every variable; the source import must map and enforce the actual controls.

The server must consume reviewed artifacts through read-only credentials. Production must deploy an exact commit SHA or immutable container digest; it must not build from an unreviewed branch or accept manual source edits inside a running container.
