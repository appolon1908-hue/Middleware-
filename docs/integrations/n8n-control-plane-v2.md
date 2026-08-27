# Middleware ↔ n8n automation control plane v2

## Decision

Middleware is the only cross-system write boundary. n8n is an orchestration client of Middleware and does not connect directly to Odoo, Keycloak administration, VICIdial, Asterisk, Telnexa/Jasmin, Klyrow/Postal/Mautic, Kyqra/Crawlee, Postly, product databases or provider APIs.

```text
Provider/application event
  -> Middleware authenticated inbox
  -> canonical event + automation job + dispatch outbox
  -> private n8n wake
  -> n8n atomic claim
  -> governed Middleware commands
  -> destination adapter and read-back
  -> Middleware reconciliation
  -> terminal automation result
```

## Middleware responsibilities

- authenticate the n8n machine client;
- resolve the authoritative tenant and actor;
- validate workflow key and major version;
- persist normalized events before dispatch;
- create automation jobs and attempts;
- grant and expire execution leases;
- enforce idempotency and semantic conflict detection;
- evaluate capabilities, integration pauses, consent and suppression;
- own provider and application credentials;
- translate commands into destination-specific adapters;
- reconcile unknown outcomes before retry;
- persist approvals, retries, dead letters and controlled replay;
- preserve correlation, causation and trace context;
- redact customer content and credentials from logs.

## Durable models

```text
automation_jobs
automation_job_attempts
automation_job_steps
automation_job_leases
automation_approvals
automation_commands
automation_command_attempts
automation_dead_letters
automation_reconciliation_runs
automation_dispatch_outbox
```

Every tenant-owned row includes `tenant_id`. Externally effective commands use a stable idempotency key and a semantic request fingerprint. Exact replays return the original result. Conflicting replays are rejected without mutating the original record.

## Job lifecycle

```text
PENDING -> DISPATCHING -> CLAIMED -> RUNNING
RUNNING -> WAITING_APPROVAL | WAITING_TIMER | WAITING_COMMAND
RUNNING -> RETRY_SCHEDULED | COMPLETED | FAILED_TERMINAL | DEAD_LETTER | CANCELLED
```

A lease token is required for heartbeat, step, completion and failure operations. A stale execution cannot complete a job after its lease is lost.

## Private trigger pattern

Middleware writes the job and dispatch outbox in one transaction. Its worker sends n8n a private wake containing identifiers and a one-use delivery token. n8n then calls the claim API to receive the safe payload and policy snapshot.

Public provider callbacks never terminate at n8n. A lost wake is recoverable from the outbox, and a dead n8n worker is recoverable through lease expiry.

## Command semantics

A command may be:

```text
ACCEPTED
BLOCKED
SUBMITTED
UNKNOWN
COMPLETED
FAILED
CANCELLED
```

A timeout or interrupted response produces `UNKNOWN`. Middleware checks the destination before retrying an externally effective command.

## Human approvals

Approval state is authoritative in Middleware and the approved operations surface. Long waits are persisted as `WAITING_APPROVAL`; n8n exits and receives a new resume job after approval.

Sensitive approval classes include:

```text
CAMPAIGN_OWNER
UNDERWRITER
TELEPHONY_OWNER
PRIVACY_OFFICER
TWO_PERSON
CONTENT_OWNER
FINANCE_POLICY
RELEASE_OWNER
```

## Capability policy

All effectful capabilities remain disabled until a separately approved staging and production canary. Workflow activation does not enable a capability.

Examples:

```text
ODOO_WRITE
PRODUCTION_DIALING
CALLBACK_DISPATCH
SMS_SEND
EMAIL_SEND
SOCIAL_PUBLISH
CRAWLER_EXECUTION
CRAWLER_WRITEBACK
LEAD_PUBLISH
PRIVACY_WRITE
DEAD_LETTER_REPLAY
PAYMENT_EXECUTION
```

## Cross-repository dependencies

```text
core/integration-contracts
platform/postgresql
platform/redis
integration/keycloak
core/event-ledger-outbox
core/webhook-inbox-replay
core/workers-scheduler
integration/n8n
```

The N8N contract branch is `appolon1908-hue/N8N:contract/automation-control-plane-v2-20260827`.

## Acceptance

```text
DIRECT_N8N_SERVICE_ACCESS=DENIED
DURABLE_INBOX_BEFORE_ACK=PASS
TRANSACTIONAL_OUTBOX=PASS
EXACT_REPLAY=PASS
CONFLICTING_REPLAY=PASS
CONCURRENT_DUPLICATE=PASS
TENANT_ISOLATION=PASS
LEASE_RECOVERY=PASS
UNKNOWN_OUTCOME_RECONCILIATION=PASS
BOUNDED_RETRY=PASS
DEAD_LETTER=PASS
CONTROLLED_REPLAY=PASS
CAPABILITIES_DEFAULT_FALSE=PASS
PRODUCTION_CHANGED=NO
```
