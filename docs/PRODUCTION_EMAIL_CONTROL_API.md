# Production Email Control API

Date: 2026-09-12

## Purpose

This contract adds the missing fail-closed production authorization layer around the existing email transport. It does **not** create a second email-send API and it does not move provider authority out of Klyrow.

Canonical path remains:

`Odoo / n8n / product caller -> Middleware -> Klyrow -> Postal -> receiver`

Delivery/read-back remains:

`Postal/Klyrow event -> Middleware -> communications projection -> Odoo/product read-back`

## Existing canonical transport surfaces (preserved)

### Middleware product API

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `POST` | `/v1/communications/messages` | Canonical product submission for email/SMS. Email is production-gated before command creation. |
| `GET` | `/v1/communications/messages` | Tenant-scoped message list. |
| `GET` | `/v1/communications/messages/by-idempotency` | Idempotency read-back. |
| `GET` | `/v1/communications/messages/{messageId}` | Durable message state/read-back. |
| `GET` | `/v1/communications/messages/{messageId}/events` | Canonical lifecycle timeline. |
| `POST` | `/v1/communications/messages/{messageId}/cancel` | Cancel a non-terminal message where supported. |

The legacy singular alias `POST /v1/communication/messages` remains compatibility-only. New callers must use `/v1/communications/messages`.

### Middleware -> Klyrow private transport

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `POST` | Klyrow `/v1/email/messages` | Authenticated command-bound email submission. |
| `GET` | Klyrow `/v1/email/messages/{command_id}` | Authoritative provider-side read-back after uncertain outcomes. |

The Middleware Klyrow adapter retains command identity `email.message.send.v1`, target `klyrow-email`, and capability `EMAIL_DELIVERY`.

### Klyrow -> Middleware events

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `POST` | `/internal/provider-events/klyrow` | Signed durable ingress for delivery, usage, and supported inbound events. |

Accepted email lifecycle events include accepted, queued, submitted, sent, delivered, deferred, bounced, complained, rejected, failed, cancelled, unknown outcome, opened, clicked, and unsubscribed. Exact replay is deduplicated; changed content under an existing event identity is rejected.

## New production-control surface

Prefix: `/platform/v1/email/production`

These endpoints require a Keycloak machine identity with `azp=production-operator`, audience `middleware-api`, tenant binding, and the configured production-control scopes. Mutations additionally require exactly one `X-Correlation-ID` and `Idempotency-Key`.

| Method | Endpoint | Scope | Purpose |
| --- | --- | --- | --- |
| `GET` | `/platform/v1/email/production/status` | `email.production.read` | Read effective tenant production policy. |
| `GET` | `/platform/v1/email/production/readiness` | `email.production.read` | Return activation blockers; does not mutate provider/runtime state. |
| `GET` | `/platform/v1/email/production/quotas` | `email.production.read` | Read current minute/hour/day usage and limits. |
| `GET` | `/platform/v1/email/production/audit` | `email.production.read` | Read production-control audit history. |
| `POST` | `/platform/v1/email/production/authorize` | `email.production.write` | Record reviewed tenant/domain/sender/recipient/quota authorization. Does not start sending. |
| `POST` | `/platform/v1/email/production/activate` | `email.production.write` | Activate only when all fail-closed readiness gates pass. |
| `POST` | `/platform/v1/email/production/revoke` | `email.production.write` | Revoke authorization, return mode to SAFE, and close the kill switch. |
| `POST` | `/platform/v1/email/production/kill-switch` | `email.production.write` | Open/close new-send permission. Opening requires active authorization. |

## Production modes

- `SAFE`: no production email is authorized.
- `TRANSACTIONAL_CANARY`: explicit recipient allowlist; tight quota; transactional only.
- `TRANSACTIONAL_PRODUCTION`: transactional recipients within approved policy.
- `CAMPAIGN_PRODUCTION`: separate marketing authorization; consent/suppression still required.

Campaign mode is never inferred from transactional activation.

## Authorization model

An authorization records at minimum:

- tenant;
- approved domains;
- approved senders;
- recipient scope;
- optional explicit recipient allowlist;
- minute/hour/day quotas;
- valid-from / valid-until;
- change ID;
- approving actor;
- monitoring owner;
- requested mode.

`authorize` moves the policy to `AUTHORIZED_NOT_ACTIVE`. It does not open the send path.

`activate` moves it to `ACTIVE` and opens the kill switch only if readiness returns no blockers.

`revoke` closes the path and returns the policy to `SAFE`.

## Readiness / activation blockers

Activation fails closed when any required condition is missing, including:

- production authorization;
- non-SAFE production mode;
- `PRODUCTION_ACTIVATION_ID` deployment binding;
- effective Middleware email-delivery runtime gate;
- valid authorization time window;
- approved domains/senders;
- positive quota limits;
- registered Postal domain;
- Postal DNS check pass;
- DKIM rotation complete;
- post-rotation DNS recheck complete;
- Middleware send eligibility;
- domain production-ready certification.

A previous DNS pass alone is explicitly insufficient.

## Send-path enforcement order

For production email, Middleware applies the gates in this order:

1. original bearer and tenant authorization;
2. production policy active;
3. kill switch open;
4. authorization validity window;
5. approved domain;
6. approved sender;
7. mode/category rule (transactional vs marketing);
8. recipient scope / canary allowlist;
9. atomic minute/hour/day quota reservation;
10. existing verified sender/domain check;
11. existing suppression and consent pre-check;
12. existing command-policy authorization;
13. durable `email.message.send.v1` command handoff;
14. Klyrow adapter runtime gate;
15. Klyrow/Postal provider policy.

If existing suppression/consent logic suppresses before provider submission, the production quota reservation is released.

An exact idempotent replay returns the prior logical message and does not consume another quota reservation.

## Quota semantics

Quota buckets are tenant-scoped and durable for minute, hour, and day windows. Reservation occurs before a new provider command can be created. A failed or locally suppressed submission releases the reservation.

The quota layer is an application safety ceiling, not a substitute for Klyrow/provider rate or reputation controls.

## Audit and mutation idempotency

Every control mutation stores:

- tenant;
- action;
- actor;
- reason;
- correlation ID;
- previous policy;
- new policy;
- timestamp.

Control mutations are idempotent by tenant + action + actor + `Idempotency-Key`. Reusing the same key with different content returns conflict.

## Ownership boundaries

### Odoo

Business system of record. Odoo can request sends through the canonical communications API and read lifecycle state, but it does not own global production authorization.

### n8n

Workflow orchestrator only. It cannot activate production email and its provider writes remain separately controlled by `N8N_EXTERNAL_PROVIDER_WRITES`.

### Middleware

Owns platform authorization, tenant/sender/domain production policy, production quotas, kill switch, durable command handoff, callback normalization, and canonical read-back.

### Klyrow

Owns provider mail policy, sender/domain provider state, suppression/bounce/complaint handling, DKIM signing, reputation, and Postal integration.

### Postal

Provider transport; applications must not submit directly to Postal.

## Deployment requirement

The new control tables are created by `migrations/0012_email_production_control.sql`. The rollback is `migrations/rollback/0012_email_production_control.down.sql`.

The source change does **not** authorize live sending. Production remains blocked until the deployment has a real `production-operator` Keycloak identity/scopes and the domain registry has documented DKIM rotation/post-rotation certification and send eligibility.
