## Summary

Describe the middleware behavior, API, worker, migration, integration, testing, or deployment-control change.

## Integration workstream

- Source branch:
- Declared branch scope from `docs/INTEGRATION-BRANCHES.md`:
- Runtime status from `config/integration-branches.json`:
- Dependency pull request(s), or `NONE`:
- Required merge order, or `INDEPENDENT`:

- [ ] The source branch matches the system being changed.
- [ ] Unrelated system changes were split into separate pull requests.
- [ ] The branch was updated from the latest reviewed `main` before exact-head validation.
- [ ] This workstream branch will not be deployed directly.
- [ ] A verification-only branch does not add or activate a production runtime without an approved architecture and activation record.

## Runtime scope

- API service(s):
- Worker service(s):
- Scheduled/cron service(s):
- Database migration revision(s):
- PostgreSQL, Redis, RabbitMQ, queue, outbox, inbox, webhook, or dead-letter impact:
- Odoo, n8n, VICIdial, Asterisk/PJSIP, Keycloak, Kong/Caddy, Telnexa, Klyrow, Postly, Mautic, Postal, Jasmin, Crawlee, Playwright, crawler, or provider impact:

## Security and repository hygiene

- [ ] No `.env`, passwords, tokens, private keys, certificates, production payloads, customer data, database/queue dumps, logs, packet captures, browser traces containing secrets, or runtime volumes are included.
- [ ] Dependencies are locked and installed reproducibly.
- [ ] Official/third-party GitHub Actions are pinned to immutable commit SHAs or container digests.
- [ ] Authentication, authorization, tenant isolation, input validation, and secret redaction were reviewed where affected.
- [ ] New webhooks enforce authentication/signatures, timestamp bounds, replay protection, idempotency, and deduplication.

## Validation

- [ ] Bootstrap repository validation passes.
- [ ] Workstream manifest validation passes.
- [ ] Formatting/lint and static type checks pass.
- [ ] Unit tests pass.
- [ ] PostgreSQL integration tests pass where affected.
- [ ] Redis/RabbitMQ/queue integration tests pass where affected.
- [ ] Migration upgrade and rollback tests pass where affected.
- [ ] Outbox/inbox, retry, lease, idempotency, replay, and dead-letter tests pass where affected.
- [ ] Cross-tenant and authorization tests pass where affected.
- [ ] Odoo, n8n, telephony, identity, gateway, SMS, email, marketing, crawler, browser, and provider contract tests pass where affected.
- [ ] Container build, health, readiness, graceful shutdown, and restart tests pass.
- [ ] Secret, dependency, and container vulnerability scans pass.

## Safety gates

- [ ] Staging starts fail closed with external delivery, live writes, callbacks, n8n delivery, Odoo writes, VICIdial writes, SMS/email/social delivery, crawler writes, browser writes, and dialing disabled.
- [ ] Effective safety values were verified from the running staging container, not only from an example file.
- [ ] No production capability is enabled by this pull request unless the approved activation record is linked below.
- [ ] Database, broker, queue, and external-effect rollback limitations are documented.

## Release evidence

- Exact reviewed branch-head SHA:
- Protected merged SHA:
- Immutable image digest:
- Staging deployment record:
- Test evidence:
- Backup/restore evidence:
- Rollback evidence:
- Production approval or `NOT_REQUESTED`:

## Deployment notes

List the exact Compose project and service names, migration commands, health checks, compatibility order, and rollback commands. The shared server deployment must not restart unrelated Odoo, n8n, PostgreSQL, Redis, Keycloak, Kong, Caddy, RabbitMQ, Mautic, Postal, Jasmin, crawler, browser-test, or provider services.
