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

Apply `migrations/0001_runtime.sql` before starting a non-test runtime.

## Outbox, retry and DLQ

The migration also creates a lease-based `middleware_outbox`. The store and generic worker implement `FOR UPDATE SKIP LOCKED`, bounded exponential retry, lease ownership and dead-letter transition.

No external provider handler is registered on this branch. `OUTBOX_DISPATCH_ENABLED=true` is explicitly rejected by the runtime safety configuration, and `workers/run_outbox.py` refuses to activate provider delivery.

## Fail-closed runtime

In staging/production:

- in-memory storage is prohibited;
- PostgreSQL and Redis are required;
- all external-effect flags must be false;
- outbox dispatch must be false;
- API docs are disabled;
- the application fails startup on unsafe or incomplete configuration.

This branch does not add Kong routes, mutate Keycloak, change Odoo/n8n/provider systems, or deploy to Server A. Deployment requires a separate reviewed exact-SHA staging change.
