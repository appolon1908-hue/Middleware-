# Scrapper Turnkey Control Plane Integration

Status: contract and implementation boundary. No live route, credential, Odoo write, n8n execution, or production deployment is enabled by this branch.

## Ownership

Codestra Middleware is the only cross-system write boundary.

The scrapper owns tenant onboarding state, source catalogs, schedules, crawl jobs, evidence, reviews, and its durable inbox/outbox. Middleware owns service authorization, destination policy, event normalization, idempotency, retry, replay, dead-letter handling, Odoo mappings, n8n trigger contracts, and cross-system reconciliation.

n8n orchestrates only after Middleware durably accepts an event. Odoo receives only Middleware-approved projections. Neither n8n nor Odoo calls scrapper persistence directly.

## Routes

The intended private routes are:

```text
POST /v1/integrations/scrapper/events
GET  /v1/integrations/scrapper/events/{eventId}
POST /v1/integrations/scrapper/commands
GET  /v1/integrations/scrapper/commands/{commandId}
POST /v1/integrations/scrapper/reconciliation
GET  /v1/integrations/scrapper/reconciliation/{runId}
```

All routes are private, versioned, tenant-bound, and protected by service identity plus mTLS or a signed canonical request. They must not share a public website route.

## Event acceptance

Middleware acknowledges an event only after it has:

1. authenticated the scrapper service identity;
2. verified the tenant and event scope;
3. validated the JSON Schema version;
4. verified `X-Codestra-Message-ID`, timestamp, body digest, and HMAC signature;
5. rejected an expired or replayed nonce;
6. durably inserted the original envelope and digest;
7. inserted the normalized event and transactional outbox record in the same transaction.

A repeated event ID with the same digest returns the original receipt. The same ID with changed content is rejected as a semantic conflict.

## Reverse command delivery

Middleware writes a command to its outbox and delivers it to the scrapper private integration endpoint. The command ID is also the idempotency key. The scrapper responds only after the command is durably stored in PostgreSQL.

Allowed v1 command types are:

```text
scraper.crawl.requested
scraper.job.cancel.requested
scraper.source.validate.requested
```

Unknown types fail closed and cannot be converted into arbitrary URLs, SQL, workflow names, or internal function calls.

## Odoo and n8n flows

```text
scraper.business.batch.ready
  -> Middleware inbox
  -> policy / consent / suppression
  -> normalized Odoo projection command
  -> Middleware outbox
  -> Odoo adapter
  -> delivery receipt / reconciliation
```

```text
scraper.job.completed
  -> Middleware inbox
  -> approved n8n trigger contract
  -> n8n orchestration
  -> any reverse action returns through Middleware command API
```

Odoo is not authoritative for crawl state, evidence provenance, tenant identity, or idempotency. n8n is not authoritative for retry, duplicate detection, delivery receipts, or audit state.

## Required headers

```text
Authorization: Bearer <short-lived service token>
X-Codestra-Message-ID: <UUID>
X-Codestra-Timestamp: <Unix seconds>
X-Codestra-Signature: v1=<hex>;kid=<key-id>
X-Correlation-ID: <UUID>
X-Tenant-ID: <UUID>
Content-Type: application/json
```

The canonical signature input is the uppercase HTTP method, path, timestamp, message ID, tenant ID, SHA-256 body digest, and schema version separated by newlines.

## Failure classes

- `400` invalid schema or unsupported version: permanent.
- `401` invalid service identity or signature: permanent until credentials change.
- `403` tenant/scope/policy denial: permanent for the message.
- `409` message ID reused with different content: permanent semantic conflict.
- `425` timestamp or ordering precondition not yet satisfied: bounded retry.
- `429` rate or quota limit: retry using server guidance.
- `500`, `502`, `503`, `504`: retry with bounded exponential backoff.

Retries preserve the original event or command ID and body. A retry never creates a new business operation.

## Capability gates

The following remain disabled until the corresponding staging canary and independent approval exist:

```text
SCRAPPER_EVENT_DELIVERY_ENABLED=false
SCRAPPER_COMMAND_DELIVERY_ENABLED=false
ODOO_WRITE=false
N8N_DELIVERY_ENABLED=false
LIVE_WRITES=false
```

## Acceptance evidence

Before activation, the exact source and image digests must pass:

- schema and contract tests;
- duplicate event and changed-body conflict tests;
- timeout-after-success replay tests;
- expired timestamp and bad signature tests;
- cross-tenant denial tests;
- n8n duplicate trigger tests;
- Odoo idempotent upsert and reconciliation tests;
- dead-letter and audited replay tests;
- write-disabled staging canary;
- application rollback exercise.
