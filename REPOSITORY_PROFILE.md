# Repository Profile — `Middleware-`

## Identity

- **Repository:** `appolon1908-hue/Middleware-`
- **Category:** Platform control plane — integration and writes
- **Visibility:** `private`
- **Default branch:** `main`
- **Authority:** Only privileged cross-system write and command authority
- **Status:** Active central integration runtime with durable command, event, provider, audit, and reconciliation boundaries.

## Purpose

Authenticates and authorizes cross-system commands, enforces tenant and policy controls, manages idempotency, inbox/outbox, retries, dead letters, reconciliation, audit, and governed adapters to business and provider systems.

## Owns

- Cross-system command, event, delivery, and reconciliation ledger
- Tenant isolation, policy, consent, suppression, idempotency, correlation, retry, and audit enforcement
- Governed adapters to Odoo, n8n, email, SMS, voice, crawler, provisioning, and product systems

## Does not own

- Provider-native runtime internals
- Product frontend presentation
- Trust in client-supplied tenant, actor, role, scope, or provider fields without validation

## Key integrations

- Caddy, Kong, and Keycloak
- Odoo and n8n
- Klyrow, Telnexa, VICIdial, Kyqra, provisioning, and product APIs
- `SDK-repository` contracts

## Current priorities

1. Complete provider-neutral email, SMS, and voice runtime mappings
2. Eliminate source/runtime route drift and prove contract compatibility
3. Prove uncertain-outcome reconciliation without duplicate effects
4. Maintain global live-write and provider-delivery kill switches until launch approval

## Governance and safety

- Promotion model: `feature/docs/fix/security/upgrade -> development -> test -> staging -> production -> main`.
- Every effectful command requires validated identity, tenant, authorization, policy, idempotency, durable state, and provider read-back where applicable.
- Never commit provider credentials, customer payloads, database dumps, HMAC secrets, private keys, or bearer tokens.
- Merge is source acceptance only; live writes and provider effects remain separately enabled.
- This document does not send email/SMS, place calls, write Odoo, activate n8n, dispatch crawler jobs, or deploy Middleware.

## Account-wide catalog

See `appolon1908-hue/documentaions/REPOSITORY_CATALOG.md`.
