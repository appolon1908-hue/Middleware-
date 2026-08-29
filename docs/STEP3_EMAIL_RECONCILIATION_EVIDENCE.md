# Step 3 Email Reconciliation Evidence

Date: 2026-08-29

## Implemented

- New email messages start with canonical `accepted` and `queued` events.
- Idempotency keys prevent duplicate command creation for replayed requests.
- Reused idempotency keys with changed payloads return conflict.
- Provider events from Klyrow update message status and append canonical timeline events.
- Cross-tenant reads are denied before read-back data is returned.
- Cancellation is rejected for terminal states.

## Remaining Before Production

- Persist the Communications read model in durable storage.
- Add provider timeout fixtures for before-acceptance and possible-after-acceptance outcomes.
- Add read-back reconciliation that marks uncertain provider submission as `indeterminate` until Klyrow proves delivery, failure, or non-acceptance.
- Add event deduplication storage for repeated provider event IDs at the communications read-model layer.
