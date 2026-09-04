# VICIdial lifecycle projection to Odoo

## Data path

```text
Asterisk/VICidial
  -> read-only AMI observer
  -> signed /api/v1/vicidial/events ingress
  -> Middleware durable inbox + immutable event ledger + NATS outbox
  -> dedicated durable JetStream consumer
  -> tenant-bound signed Odoo call-event endpoint
  -> Odoo call state + Odoo Bus screen pop
```

The worker consumes only the explicit `codestra.vicidial.call.lifecycle.*`
event allowlist. It does not transport RTP/SRTP audio and has no AMI, ARI,
originate, campaign-write, callback, or production-dialing permission.

The shared VICidial ingress also retains the pre-existing SDK compatibility
event `codestra.events.call_disposition_updated`. That event remains accepted by
the normal route but is outside the lifecycle subject and cannot be consumed by
this projection worker. The lifecycle authority is pinned to protected Keycloak
`main` merge `922d039b5143f3ac738e88998036355562a8dd5d`; it authorizes the exact
`codestra.vicidial.call.lifecycle.*` subset plus the already published canonical
VICIdial events.

## Delivery discipline

Every event is first registered in a persistent SQLite state ledger mounted at
`VICIDIAL_ODOO_STATE_PATH`. Registration and state transitions use serialized
transactions, and terminal `delivered` or `failed` states cannot be downgraded.
The ledger file is forced to mode `0600`.

An exact success response is accepted only when Odoo returns matching event,
tenant, call, type, sequence, and `recorded=true` evidence. A timeout or
ambiguous HTTP response is followed by signed status read-back. Until Odoo
proves a 404, redelivery performs read-back only and never blindly repeats the
write.

Odoo HTTP 409 responses are also fail-closed. Only an identity-matching
`sequence_gap` response with `retryable=true`, `recorded=false`, and consistent
`expected_sequence`/`current_sequence` evidence may be retried. Stale sequence,
lifecycle transition, and event-identity conflicts are terminal. Unknown or
malformed conflict evidence remains outcome-unknown and is reconciled rather
than guessed.

The worker sends JetStream progress acknowledgements while an Odoo request or
read-back is active and starts every message in a fetched batch immediately, so
one slow event cannot let later deliveries expire behind it.

## Activation sequence

1. Protected Keycloak merge `922d039b5143f3ac738e88998036355562a8dd5d`
   is the immutable lifecycle identity authority.
2. Merge and deploy the exact Odoo projection endpoint and screen-pop gate.
3. Merge this Middleware worker and its protected Keycloak authority lock.
4. Deploy a protected staging candidate with the worker disabled.
5. Bind NATS and Odoo secrets outside Git.
6. Enable `VICIDIAL_ODOO_PROJECTION_ENABLED=true` with
   `VICIDIAL_ODOO_SYNTHETIC_ONLY=true` only for `TEST_SYN`.
7. Certify created -> ringing -> connected -> hangup -> completed, duplicate,
   out-of-order, restart, and read-back behavior.

Production remains a separate activation release requiring an exact activation
ID, `ODOO_WRITE`, the external-delivery umbrella, rollback evidence, and
`PRODUCTION_DIALING=DISABLED`.
