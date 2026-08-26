# Codestra Middleware

This repository is the intended source of truth for Codestra's self-hosted middleware application running on Application Server A.

> **Security notice:** this repository is currently public. Keep it limited to non-secret bootstrap files until its visibility is changed to private. Do not import Codestra middleware source, integration configuration, customer data, credentials, certificates, or operational evidence while it is public.

## Operating model

1. Create a feature branch.
2. Change application code, tests, database migrations, workers, or non-secret deployment templates.
3. Open a pull request and pass CI.
4. Deploy the reviewed exact commit SHA to staging with every external-write capability disabled.
5. Run database, Redis, webhook, Odoo, n8n, VICIdial, authentication, idempotency, retry, and rollback tests as applicable.
6. Build and publish an immutable image for the accepted SHA.
7. Deploy the exact accepted image digest to production after explicit approval.

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

The server must consume reviewed artifacts through read-only credentials. Production must deploy an exact commit SHA or immutable container digest; it must not build from an unreviewed branch or accept manual source edits inside a running container.
