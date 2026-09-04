# VICIdial to Odoo call-event pipeline

## Runtime ownership

```text
DID/SIP carrier -> Asterisk/VICIdial -> agent endpoint
                       |
                       | call-state evidence only
                       v
              VICIdial AMI event gateway
                       |
                       | signed canonical HTTPS event
                       v
                 Middleware inbox
                       |
                       | durable Odoo projection outbox
                       v
             Odoo authoritative call model
                       |
                       | Odoo bus notification
                       v
                 agent browser popup
```

Asterisk/VICIdial continues to carry SIP/RTP/WebRTC media. Middleware carries
only authenticated commands and lifecycle evidence. Odoo owns CRM state and its
own browser bus. n8n is not part of the live call-state or audio path.

## Canonical lifecycle events

The VICIdial adapter may publish only the following new lifecycle types through
`POST /api/v1/vicidial/events`:

```text
codestra.vicidial.call.lifecycle.created
codestra.vicidial.call.lifecycle.offered
codestra.vicidial.call.lifecycle.ringing
codestra.vicidial.call.lifecycle.answered
codestra.vicidial.call.lifecycle.connected
codestra.vicidial.call.lifecycle.held
codestra.vicidial.call.lifecycle.resumed
codestra.vicidial.call.lifecycle.transfer.started
codestra.vicidial.call.lifecycle.transfer.completed
codestra.vicidial.call.lifecycle.hangup
codestra.vicidial.call.lifecycle.completed
codestra.vicidial.call.lifecycle.ended
codestra.vicidial.call.lifecycle.failed
codestra.vicidial.call.lifecycle.missed
codestra.vicidial.call.lifecycle.recording.available
codestra.vicidial.call.lifecycle.disposition.required
```

Each event requires the canonical platform envelope and a strict payload with
`business_unit_id`, `campaign_id`, `call_id`, `asterisk_uniqueid`, `linkedid`,
`agent_id`, `extension`, `keycloak_subject`, monotonic `sequence`, `direction`,
and bounded optional call metadata. Phone numbers must be E.164. Extra payload
fields are rejected before durable acceptance.

## Durable processing

1. Middleware verifies the short-lived `vicidial-adapter` bearer identity,
   tenant authority, route scope, timestamp, raw-body HMAC, event ID,
   correlation ID, and idempotency key.
2. The durable inbox accepts one semantic event. Exact replays are duplicates;
   changed-body reuse is rejected.
3. `PostgresTelephonyProjectionStore` locks one accepted lifecycle event with
   `FOR UPDATE SKIP LOCKED` and creates exactly one
   `odoo-call-event` outbox row in the same transaction.
4. `TelephonyOutboxStore` leases only `odoo-call-event` rows. It cannot claim,
   retry, or dead-letter NATS, Temporal, email, SMS, social, or other outbox
   destinations.
5. `OdooCallEventDispatcher` signs the existing Odoo call-event endpoint and
   validates the returned call identity and state.
6. If the POST outcome is ambiguous, Middleware performs the signed read-only
   Odoo lookup `GET /codestra/api/v1/call-events/{event_id}`. It retries the POST
   only after a `404` proves the event was not persisted. Matching readback is
   treated as completion; unavailable or mismatched readback remains
   `reconciliation_required` and is never blindly resubmitted.

## Process entrypoint

The immutable Middleware image has a dedicated `telephony-worker` target:

```text
python -m workers.run_telephony_projection
```

Startup requires all of the following:

```text
TELEPHONY_ODOO_PROJECTION_ENABLED=true
EXTERNAL_DELIVERY_ENABLED=true
ODOO_WRITE=true
DATABASE_URL=<protected PostgreSQL URL>
ODOO_19_BASE_URL=<reviewed HTTPS Odoo origin>
ODOO_19_HMAC_SECRET=<protected secret, at least 32 bytes>
```

The checked-in template keeps all three activation switches false. Enabling
these values is a separate protected staging action, not a source-merge effect.
The dedicated worker has no VICIdial command credential and cannot place,
answer, transfer, or terminate calls.

## Required staging certification

Before any production consideration, deploy exact immutable source and execute
one synthetic campaign flow with no customer traffic:

1. `created -> offered -> ringing -> answered -> connected` reaches one assigned
   agent and opens the matching Odoo lead/customer.
2. Hold/resume and same-campaign transfer states remain monotonic.
3. Hangup/completion stores duration, cause, wrap-up, and one disposition.
4. Exact event replay creates no duplicate Odoo call event.
5. Out-of-order sequence is retained as evidence but does not regress state.
6. A forced ambiguous POST is reconciled by exact readback with zero duplicate
   delivery.
7. Middleware, event gateway, and Odoo restart tests prove no event gap.
8. Cross-tenant, cross-campaign, wrong-agent, wrong-extension, wrong-subject,
   invalid-signature, expired-timestamp, and changed-payload replays fail closed.
9. Odoo bus delivers the popup only to the mapped agent.
10. `CALLS_PLACED=0` remains true for source and no-effect tests; any real PSTN
    canary requires a separate approved activation.

## Merge and deployment order

```text
1. Odoo signed call-event readback endpoint
2. Middleware lifecycle contract and projection worker
3. VICIdial local AMI event gateway
4. protected synthetic staging deployment and certification
5. separate production activation decision
```
