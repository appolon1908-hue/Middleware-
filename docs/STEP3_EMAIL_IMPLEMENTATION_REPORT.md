# Step 3 Email Implementation Report

Date: 2026-08-30

## Authority

Frozen SDK contract:

`appolon1908-hue/SDK-repository:feat/communications-api-v1-contracts@63c793e88cca5daecfb5c8a688b8674ab288c522`

Middleware branch:

`feat/communications-api-v1-email-runtime`

## Scope Implemented

Middleware now exposes the email subset of Communications API v1:

- `POST /v1/communications/messages`
- `GET /v1/communications/messages`
- `GET /v1/communications/messages/{messageId}`
- `GET /v1/communications/messages/{messageId}/events`
- `POST /v1/communications/messages/{messageId}/cancel`
- `GET /v1/communications/providers/health`
- `GET /v1/communications/reputation`
- `GET /v1/communications/usage`

The runtime maps `channel=email` requests to `email.message.send.v1` commands targeting `klyrow-email`, preserving tenant, actor, bearer authorization, scopes, correlation ID, and idempotency key. It maintains the canonical message read model and event timeline and updates that read model from signed Klyrow provider events accepted through the existing webhook ingress path.

Command-ledger state is reconciled into the canonical message model. An
uncertain provider outcome becomes `indeterminate`; it is never represented as
success and the Temporal command workflow does not automatically retry it.
Exact create replays reuse the original command, while signed provider callback
replays are deduplicated without duplicating timeline effects.

## Step 3 Completion Boundary

The email control-plane mapping, contract validation, fail-closed capability
gate, tenant isolation, idempotency, uncertain-outcome quarantine, command
read-back state mapping, and signed callback/replay behavior are implemented and
covered by automated tests. Completion requires the PR's exact-head and
merge-result CI checks to be green; the authoritative run is the GitHub check
set attached to PR #52.

## Safety Boundary

This branch does not enable live email delivery, Postal, Mautic, Keycloak, Kong, Caddy, n8n, Odoo, production DNS, or provider write flags.

## Known Follow-Up

The current Step 3 runtime uses an in-memory Communications read store even when command storage is Postgres-backed. Before production activation, this read model and its provider-event deduplication index must be backed by durable storage with migration and rollback coverage. The production Klyrow adapter and live provider read-back remain disabled until their cross-repository contract and activation gates pass.
