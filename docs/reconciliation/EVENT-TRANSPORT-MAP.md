# Event Transport and Temporal Responsibility Map

Frozen inputs: canonical main `844d13c7ba808653a7d982c63353bc67cdc9adef`; server capture `85b7898456abd4bdd0928b80ea925cafd8ad0f4c`; captured original source `7b9451b4db92982e5f0a4179d979ae94c043f943`. This document is analysis only.

Simple synchronous reads remain synchronous. Temporal candidates are delayed callbacks, long-running provisioning, reconciliation, dead-letter recovery, multi-step provider operations, and scheduled retries.

| SERVER_FLOW | CURRENT_TRANSPORT | DURABLE_STATE | TARGET_TRANSPORT | DECISION |
|---|---|---|---|---|
| HTTP webhook acknowledgement | direct FastAPI handler | PostgreSQL inbox + immediate ack | NATS event after transaction | durable ingress; never n8n-before-ack |
| integration_event/integration_delivery | PostgreSQL polling outbox | canonical middleware_outbox | NATS JetStream | retain semantics, consolidate schema |
| event_inbox/outbox_event | second PostgreSQL queue family | canonical inbox/outbox | NATS JetStream | backfill/consolidate; no dual truth |
| scheduler poll | local worker loop | Temporal schedule or DB lease | Temporal | missed/overlap/restart workflow |
| reconciliation | worker polling/direct read-back | command ledger | Temporal | long-running unknown-outcome workflow |
| sync jobs | sync_job + checkpoint | durable command/cursor | NATS + Temporal as needed | resource-specific contracts |
| callbacks | direct HTTP/state rows | signed inbox + command | NATS/Temporal delay | delayed callback workflow candidate |
| Redis realtime | in-memory stand-in/configured Redis | ephemeral replay only | direct/Redis ephemeral | never durable truth |
