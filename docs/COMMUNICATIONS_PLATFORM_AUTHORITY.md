# Communications Platform Authority Boundary

This document defines how Codestra Middleware participates in the unified communications platform without duplicating the principal email, SMS, voice, gateway, identity or SDK repositories.

## Middleware role

`appolon1908-hue/Middleware-` remains the privileged cross-system control plane. For communications it owns:

- caller authentication revalidation and tenant/actor derivation;
- authorization, capability and policy enforcement;
- canonical command acceptance;
- semantic idempotency and request fingerprinting;
- durable command, operation, inbox, outbox and audit state;
- bounded retries and dead-letter handling;
- provider adapter invocation;
- indeterminate-state handling and reconciliation;
- destination read-back before final success where required;
- canonical event normalization and downstream dispatch;
- cross-repository release evidence for the integrated boundary.

Middleware does not own the provider runtime itself.

## Principal repositories

- Email runtime: `appolon1908-hue/klyrow.com`
- SMS runtime: `appolon1908-hue/telnexa`
- Voice/contact-center runtime: `appolon1908-hue/Vicidialer-Codestra`
- API gateway: `appolon1908-hue/Kong`
- Identity: `appolon1908-hue/Keycloak`
- Public TLS edge: `appolon1908-hue/Caddy`
- Developer SDK/contracts: `appolon1908-hue/SDK-repository`
- Communications architecture/coordination: `appolon1908-hue/communication-platform-`
- Shared infrastructure/deployment topology: `appolon1908-hue/Infustruction-repo`
- Orchestration: `appolon1908-hue/N8N`
- CRM/business state: `appolon1908-hue/Odoo`

## Required request path

```text
Application
  -> Codestra SDK
  -> Caddy
  -> Kong
  -> Keycloak-backed identity validation
  -> Middleware
  -> trusted provider adapter
  -> principal provider runtime
```

No SDK, browser, website, n8n workflow or provider may create a second privileged cross-system write path around Middleware.

## Communications command model

Provider-neutral commands should be accepted under versioned contracts and translated by Middleware into provider-specific operations. Common concepts include:

- send message;
- schedule message;
- cancel when supported;
- query operation status;
- retrieve message/event timeline;
- manage suppression/consent through governed commands where appropriate;
- query provider/channel health;
- reconcile an indeterminate operation.

The external SDK contract must not expose provider credentials or raw provider administration APIs.

## State model

Effectful communication commands must preserve uncertainty correctly:

```text
accepted
  -> queued
  -> dispatched
  -> provider_accepted
  -> completed

or

accepted -> rejected / suppressed / failed

or

dispatched -> indeterminate -> reconciliation -> completed / failed
```

An idempotency key must never be released for reuse after a provider may have accepted an operation with unknown outcome.

## Event model

Provider delivery events must arrive through a signed, authenticated or private governed ingress, be persisted durably, normalized to canonical event types and only then dispatched to downstream consumers.

Example canonical families:

- `communications.message.accepted`
- `communications.message.submitted`
- `communications.message.delivered`
- `communications.message.failed`
- `communications.message.bounced`
- `communications.message.complained`
- `communications.message.received`
- `communications.voice.call.started`
- `communications.voice.call.ended`
- `communications.voice.disposition.updated`
- `communications.provider.health.changed`

Exact event contracts belong in `SDK-repository` and the matching Middleware platform contracts.

## Security gates

Before production cutover, prove:

1. Keycloak issues the intended short-lived caller token.
2. Kong validates issuer, audience, scopes and route policy.
3. Middleware revalidates the accepted caller model without contradictory `azp`/audience assumptions.
4. Tenant binding cannot be overridden by client-supplied payload fields.
5. Idempotency is tenant + operation + canonical-request scoped.
6. Provider callbacks are replay-safe and tenant-bound.
7. Provider credentials remain server-side only.
8. Cross-provider direct writes are impossible by policy and network design.

## Cross-repository test requirements

Middleware changes affecting communications are not complete until matching contract or integration evidence exists against the involved provider repository and SDK contract. At minimum:

- exact-head contract validation;
- consumer/provider compatibility tests;
- authentication/authorization negative tests;
- duplicate/replay tests;
- timeout/indeterminate/reconciliation tests;
- provider read-back tests;
- event-signature and replay tests;
- staging smoke tests with production effects constrained;
- immutable participating SHAs in release evidence.

## Activation rule

Documentation, contracts and green source CI do not activate email, SMS or PSTN capabilities. Production effect flags and provider enablement require a separate explicitly approved release/cutover action.
