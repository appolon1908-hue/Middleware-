# Middleware Route, Event, and Command Catalog

## Binding rules

- Middleware is the only cross-system write authority.
- All effectful commands require a validated identity, derived tenant, capability, `Idempotency-Key`, correlation ID, durable command/operation state, and audit.
- Provider callbacks terminate at Middleware and require signature, timestamp, event ID, body digest, tenant mapping, and replay protection.
- Unknown outcomes are reconciled before resubmission.
- Every connector is `enabled_by_default=false`, `direct_n8n_access=false`, and `runtime_activation_authorized=false`.
- This catalog describes source contracts; it does not prove a route is deployed.

## Effectful adapter command families

| Connector | Principal repository | Command prefix | Capability | Read-back | Runtime state |
|---|---|---|---|---:|---|
| `odoo-19` | `appolon1908-hue/Odoo` | `crm.` | `ODOO_WRITE` | Yes | `UNVERIFIED_TEMPLATE_ONLY` |
| `klyrow-email` | `appolon1908-hue/klyrow.com` | `email.` | `EMAIL_DELIVERY` | Yes | `UNVERIFIED_TEMPLATE_ONLY` |
| `telnexa-sms` | `appolon1908-hue/telnexa` | `sms.` | `SMS_DELIVERY` | Yes | `UNVERIFIED_TEMPLATE_ONLY` |
| `postly-social` | `appolon1908-hue/social.codestra.co` | `social.` | `SOCIAL_PUBLISH` | Yes | `UNVERIFIED_TEMPLATE_ONLY` |
| `kyqra-crawler` | `appolon1908-hue/kyqra-crawler` | `crawler.` | `CRAWLER_EXECUTION` | Yes | `UNVERIFIED_TEMPLATE_ONLY` |
| `vicidial-restricted` | `appolon1908-hue/Vicidialer-Codestra` | `telephony.` | `PRODUCTION_DIALING` | Yes | `UNVERIFIED_TEMPLATE_ONLY` |
| `provisioning-service` | `appolon1908-hue/codestra-provisioning-service` | `provisioning.` | `PROVISIONING_WRITE` | Yes | `UNVERIFIED_TEMPLATE_ONLY` |
| `beyvra-nonfinancial` | `appolon1908-hue/beyvra-backend` | `beyvra.operations.` | `BEYVRA_OPERATIONS_WRITE` | Yes | `UNVERIFIED_TEMPLATE_ONLY` |

All eight capabilities are false in `config/capabilities.v2.json`.

## Signed inbound routes and canonical events

| Connector | Middleware ingress contract | Required source headers | Canonical inbound events |
|---|---|---|---|
| `odoo-19` | `POST /internal/v1/adapters/odoo/events` | `X-Odoo-Signature`, `X-Odoo-Timestamp`, `X-Odoo-Event-Id` | `crm.record.changed.v1`, `crm.activity.changed.v1` |
| `klyrow-email` | `POST /v1/webhooks/email/postal` | `X-Postal-Signature`, `X-Postal-Timestamp`, `X-Postal-Event-Id` | `email.message.delivered.v1`, `email.message.bounced.v1`, `email.message.complained.v1`, `email.message.unsubscribed.v1`, `email.inbound.received.v1` |
| `telnexa-sms` | `POST /v1/webhooks/sms/jasmin` | `X-Jasmin-Signature`, `X-Jasmin-Timestamp`, `X-Jasmin-Event-Id` | `sms.message.delivered.v1`, `sms.message.failed.v1`, `sms.inbound.received.v1`, `sms.recipient.opted-out.v1` |
| `postly-social` | `POST /v1/webhooks/social/postly` | `X-Postly-Signature`, `X-Postly-Timestamp`, `X-Postly-Event-Id` | `social.publication.completed.v1`, `social.publication.failed.v1`, `social.engagement.received.v1` |
| `kyqra-crawler` | `POST /v1/webhooks/crawler/kyqra` | `X-Kyqra-Signature`, `X-Kyqra-Timestamp`, `X-Kyqra-Event-Id` | `crawler.job.completed.v1`, `crawler.job.failed.v1`, `crawler.result.review-required.v1` |
| `vicidial-restricted` | `POST /internal/v1/adapters/vicidial/events` | `X-Vicidial-Signature`, `X-Vicidial-Timestamp`, `X-Vicidial-Event-Id` | `telephony.call.completed.v1`, `telephony.call.missed.v1`, `telephony.agent.status-changed.v1` |
| `provisioning-service` | `POST /internal/v1/adapters/provisioning/events` | `X-Provisioning-Signature`, `X-Provisioning-Timestamp`, `X-Provisioning-Event-Id` | `provisioning.operation.progressed.v1`, `provisioning.operation.completed.v1`, `provisioning.operation.failed.v1` |
| `beyvra-nonfinancial` | `POST /internal/v1/adapters/beyvra/events` | `X-Beyvra-Signature`, `X-Beyvra-Timestamp`, `X-Beyvra-Event-Id` | `beyvra.operations.report-ready.v1`, `beyvra.operations.support-escalated.v1`, `beyvra.operations.security-alerted.v1` |

Current manifests set a 1 MiB body limit and 300-second clock-skew window. Exact signature input and key rotation remain governed by each manifest and implementation tests.

## Forbidden Beyvra command families

```text
trade.
order.
wallet.
ledger.
hold.
payment.
withdrawal.
deposit.
transfer.
custody.
chain.
broker.
provider.
```

No n8n workflow, Middleware command, product frontend, or generic automation scope may cross this boundary.

## Product caller boundary

Product backends are Middleware clients, not provider adapters. Current caller families include MoneyBee, BREERO, LARIMÍA, freight, Beyvra, Kyqra, Klyrow, social Codestra, Kong compatibility forwarding, and n8n automation. Public websites and frontends use same-origin intake or their authoritative backend; they do not receive machine secrets or provider credentials.

## Public intake boundary

```text
browser
  -> same-origin server route
  -> Caddy
  -> Kong
  -> Middleware validation/idempotency/audit
  -> Odoo or approved downstream adapter
  -> destination read-back
```

A frontend response is not business success until Middleware durably accepts the operation. Direct browser calls to Odoo, n8n, or providers are prohibited.

## n8n automation boundary

n8n may claim jobs, heartbeat leases, submit step evidence, request allowlisted commands/approvals, read operation state, and request policy-permitted cancellation. It may not hold destination credentials, call providers/databases directly, mark an external operation successful, retry an unknown outcome without reconciliation, or perform financial/trading mutations.

## Canonical operation states

```text
ACCEPTED
QUEUED
SUBMITTED
UNKNOWN
RECONCILING
COMPLETED
FAILED
CANCELLED
SUPPRESSED
EXPIRED
```

Provider-specific evidence is retained separately. `UNKNOWN` is a safety state, not an automatic retry signal.

## Planned command families

```text
marketing.
ai.
communications.operator.
product.codestra.
product.moneybee.
product.breero.
product.freight.
product.larim-a.
product.booked4seasons.
product.restaurant.
```

Before activation each needs a principal owner, versioned contract, Keycloak/Kong policy, capability, idempotency/concurrency rules, read-back, negative/replay/cross-tenant tests, staging evidence, and independent approval.

## Safety state

```text
CONNECTORS_ACTIVE=NO
N8N_DIRECT_PROVIDER_ACCESS=NO
PUBLIC_PROVIDER_WRITE=NO
LIVE_EMAIL=NO
LIVE_SMS=NO
LIVE_SOCIAL=NO
LIVE_CRAWLER=NO
LIVE_DIALING=NO
LIVE_PROVISIONING=NO
LIVE_FINANCIAL_OR_TRADING_WRITE=NO
```
