# Odoo agent-event ingress

This endpoint closes the Odoo-to-Middleware handoff for the two agent onboarding
events. It is an ingestion boundary, not an activation switch.

## Contract

Odoo posts a canonical signed envelope to:

`POST /api/v1/odoo/events`

The route accepts the existing Odoo activity/lead event types plus:

- `codestra.odoo.agent.provisioning_requested`
- `codestra.odoo.agent.activation_email_requested`

Authentication has two independent parts:

1. A short-lived Keycloak bearer token whose `azp` is `odoo-integration`,
   includes `odoo.events.publish`, carries an explicit tenant claim, and is
   no longer than five minutes.
2. An HMAC-SHA256 envelope signature over the exact request body using the
   canonical `v1` method/path/timestamp/event/source/body-digest string.

The production integration API reads the HMAC key from the protected
`ODOO_EVENTS_HMAC_SECRET_FILE` binding. A text
`ODOO_EVENTS_HMAC_SECRET` or the canonical
`WEBHOOK_SECRET_ODOO_INTEGRATION` environment binding is supported for
controlled non-production deployments. No credential value belongs in source
control.

## Durable acceptance

After envelope and specialized payload validation, the handler commits these
records in one database transaction:

- the canonical `middleware_inbox` identity and semantic digest;
- the immutable tenant hash-chain entry in `middleware_event_ledger`; and
- a `middleware_outbox` publication intent for `nats-jetstream`.

The event ID and idempotency key are unique per tenant. An identical retry
returns HTTP 200 with `status=duplicate`; a new durable acceptance returns
HTTP 202 with `status=accepted`. Reuse with a different semantic payload is
rejected with HTTP 409.

## Agent safety invariants

The provisioning payload must remain disabled-by-default: it cannot request
immediate activation, plaintext passwords, production dialing, live call
control, or WebRTC credential issuance.

The activation-email payload must identify the Keycloak execute-actions mode,
the approved template, and the required password/TOTP actions. It may carry
only a credential-free HTTPS login URL; passwords, tokens, secrets, private
keys, recovery codes, or persisted action links are rejected.

The handler performs no Keycloak mutation, Postal/Klyrow send, Odoo write, or
production dialing. Downstream consumers must complete their own capability
and provider read-back gates before any external effect is enabled.
