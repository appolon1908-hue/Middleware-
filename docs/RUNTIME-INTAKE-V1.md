# Middleware intake runtime v1

This branch converts the reviewed middleware ingress contracts into executable FastAPI source without enabling any external delivery.

## Runtime surface

Health:
- `GET /health`
- `GET /ready`
- `GET /version`

Authenticated signed ingress:
- `POST /api/v1/odoo/events`
- `POST /api/v1/n8n/results`
- `POST /api/v1/vicidial/events`
- `POST /api/v1/telnexa/events`
- `POST /api/v1/klyrow/events`
- `POST /api/v1/kyqra/results`
- `POST /api/v1/kyqra/progress`
- `POST /api/v1/postly/events`

The route set is loaded from `config/api-webhook-contracts.json`; code and contract cannot silently drift.

## Security

Every ingress request must pass all of these checks before durable acceptance:

1. canonical Keycloak issuer `https://auth.codestra.co/realms/codestra`;
2. audience exactly `middleware-api`;
3. `azp` exactly matches the producer assigned to the route;
4. the route's least-privilege scope is present;
5. all required signed-webhook headers are present;
6. timestamp is inside the configured maximum skew (maximum 300 seconds);
7. HMAC-SHA256 signature matches the exact raw body and canonical request fields;
8. header event, tenant, source, correlation and idempotency values match the body;
9. event type is explicitly allowed for that producer/route.

Webhook HMAC secrets are separate per producer and must be injected outside Git.

## Durable inbox and replay behavior

Production/staging require PostgreSQL and Redis.

PostgreSQL is the correctness boundary. `middleware_inbox` has unique constraints for tenant/event and tenant/idempotency key. An identical retry returns the original logical result as `duplicate=true`; reusing the same event/idempotency identity with a different body is a `409`.

Redis is a short lease guard against concurrent duplicate processing. PostgreSQL remains authoritative if Redis state expires.

Apply every numbered migration through `0003_immutable_event_ledger` before
starting a non-test runtime.

## Outbox, JetStream, retry and DLQ

The same PostgreSQL transaction that accepts a new inbox event now creates its `nats-jetstream` outbox row. The store and worker implement `FOR UPDATE SKIP LOCKED`, bounded exponential retry, lease ownership, unknown-outcome quarantine, and dead-letter transition. JetStream publication uses a domain-separated `codestra.events.*` subject and a deterministic `Nats-Msg-Id`; the outbox is completed only after the server acknowledges the publish.

`workers/run_outbox.py` registers only the NATS JetStream transport. Provider, Odoo, n8n, telephony, SMS, email, social, and crawler writes are not registered. Dispatch requires `SEND_EVENTS=true`, `OUTBOX_DISPATCH_ENABLED=true`, and a non-disabled `NATS_DISPATCH_MODE` together. Production additionally requires `PRODUCTION_ACTIVATION_ID`, an exact immutable release identity, TLS, and a mounted NATS service credential.

Staging may exercise the event plane only with `NATS_DISPATCH_MODE=isolated`, stream `CODESTRA_STAGING_EVENTS`, and subjects below `codestra.staging.events.*`. It cannot use the production stream or subject namespace, and provider/business delivery flags remain disabled. `NATS_ALLOW_INSECURE_TEST_CONNECTION` exists only for a disposable localhost server in test/development; staging and production require TLS and a mounted service credential.

## Fail-closed runtime

In staging/production:

- the environment-specific runtime profile and resource identities must match;
- in-memory storage is prohibited;
- PostgreSQL and Redis are required;
- all provider/business external-effect flags must be false;
- JetStream dispatch is disabled unless separately production-authorized;
- API docs are disabled;
- the application fails startup on unsafe or incomplete configuration.

This branch does not add Kong routes, mutate Keycloak, change Odoo/n8n/provider systems, or deploy to Server A. Deployment requires a separate reviewed exact-SHA staging change.
