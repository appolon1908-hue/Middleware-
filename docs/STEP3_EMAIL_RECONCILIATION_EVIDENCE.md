# Step 3 Email Reconciliation Evidence

Date: 2026-08-30

## Implemented

- New email messages start with canonical `accepted` and `queued` events.
- Idempotency keys prevent duplicate command creation for replayed requests.
- Reused idempotency keys with changed payloads return conflict.
- A replayed create request returns the original message and leaves exactly one
  message intent and one command operation in the in-memory stores.
- Command-ledger `reconciliation_required` state is surfaced as canonical
  message status `indeterminate`, with the operation error retained for
  read-back.
- The Temporal email timeout fixture performs exactly one provider execution
  attempt, performs no read-back after the uncertain result, and terminates in
  `reconciliation_required`. It does not resubmit the command.
- Provider events from Klyrow update message status and append canonical timeline events.
- Provider event IDs are deduplicated at the communications read-model layer.
  Exact signed callback replays do not append a second event; reuse with changed
  content is rejected by the durable inbox as an idempotency conflict.
- Cross-tenant reads are denied before read-back data is returned.
- Cancellation is rejected for terminal states.

## Remaining Before Production

- Persist the Communications read model in durable storage.
- Replace the in-memory provider-event deduplication index with the same durable
  transaction as the future Communications read model.
- Bind the production Klyrow adapter and authoritative provider read-back only
  after the cross-repository contract and activation gates pass.
