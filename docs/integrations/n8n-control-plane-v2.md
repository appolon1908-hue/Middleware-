# Middleware ↔ n8n automation control plane v2

## Decision

Middleware is the only cross-system write boundary. n8n is an orchestration client of Middleware and does not connect directly to Odoo, Keycloak administration, VICIdial, Asterisk, Telnexa/Jasmin, Klyrow/Postal/Mautic, Postly/Postiz or social providers, Kyqra/Crawlee, product databases or provider APIs.

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

## Evidence language

This pull request defines a source-only design contract. The following are requirements, not completed implementation evidence:

```text
DESIGN_CONTRACT=PRESENT
IMPLEMENTATION=NOT_IMPLEMENTED
DATABASE_MIGRATIONS=PENDING
RUNTIME_API=PENDING
AUTHORIZATION_TESTS=PENDING
IDEMPOTENCY_AND_CONCURRENCY_TESTS=PENDING
STAGING_NO_EFFECT_EVIDENCE=PENDING
BACKUP_RESTORE_AND_ROLLBACK=PENDING
```

Do not report durable inbox, transactional outbox, tenant isolation, replay, lease recovery, retries, dead letters or reconciliation as `PASS` until the corresponding code and runtime tests exist on the exact reviewed SHA.

## Middleware responsibilities

- authenticate the exact n8n machine client;
- resolve the authoritative tenant, actor and workflow family from the durable job;
- enforce the client-to-workflow-family allowlist;
- enforce the command-prefix-to-scope/client allowlist;
- persist normalized events before dispatch;
- create automation jobs and attempts;
- grant and expire execution leases;
- require the active lease for step, command, completion and failure operations;
- enforce idempotency and semantic conflict detection;
- evaluate capabilities, integration pauses, consent and suppression;
- own provider and application credentials;
- translate commands into destination-specific adapters;
- reconcile unknown outcomes before retry;
- persist approvals, retries, dead letters and controlled replay;
- preserve correlation, causation and trace context;
- redact customer content and credentials from logs.

## Canonical authorization contract

`contracts/automation/operation-policy.v2.json` is the machine-readable source of truth for:

- granular OAuth scopes;
- allowed machine clients;
- workflow families assigned to each client;
- command prefixes assigned to each client;
- fields and lease context required by each endpoint;
- replay concurrency/fingerprint controls;
- authoritative tenant and actor derivation.

Generic `automation.execute` and `automation.command` scopes are prohibited.

## Dedicated social/Postly boundary

```text
workflow_family = social.postly
client          = n8n-social-automation
command_scope   = automation.command.social
command_prefix  = social.
repository      = appolon1908-hue/social.codestra.co
```

Postly retains provider OAuth tokens, social account truth, content/approval state and publication truth. n8n receives no provider tokens and cannot call Postly or social providers directly.

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

Every tenant-owned row includes `tenant_id`. Externally effective commands use a stable idempotency key and semantic request fingerprint. Exact replays return the original result. Conflicting replays are rejected without mutating the original record.

## Claim and lease rules

A wake-bound claim requires `job_id`, a one-use `delivery_token`, `workflow_key`, `workflow_version` and `execution_id`. Middleware grants the lease atomically only when the client is allowed to claim the job's workflow family.

A current lease token and execution ID are mandatory for heartbeat, step evidence, command requests, completion and failure. A stale execution cannot record a step, issue a command or finish a job after losing its lease.

## Command context

A governed command carries the job, lease, execution, workflow and step identity. It does not choose an authoritative tenant or actor. Middleware derives both from the job and token mapping.

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

Approval state is authoritative in Middleware and the approved operations surface. Long waits are persisted as `WAITING_APPROVAL`; n8n exits and receives a new resume job after approval. The requester cannot satisfy its own protected approval.

## Dead-letter replay

A replay request requires:

```text
protected approval ID
idempotency key
expected dead-letter version
original-effect fingerprint
safe-replay classification
replay reason
```

Middleware preserves the original tenant and refuses unsafe or stale replay requests. `automation.operations.replay.request` authorizes only the request; the effect also requires the capability, approval and record checks.

## Capability policy

All effectful capabilities remain disabled until separately approved staging and production canaries. Workflow activation does not enable a capability.

## Cross-repository dependencies

```text
N8N PR #1 governance baseline
N8N PR #9 automation contract
Keycloak PR #10 scoped machine identities
social.codestra.co PR #1 Postly domain contract
core/integration-contracts
platform/postgresql
platform/redis
integration/keycloak
core/event-ledger-outbox
core/webhook-inbox-replay
core/workers-scheduler
integration/n8n
integration/n8n-control-plane-v2-20260827
```

## Acceptance gates

```text
DESIGN_REVIEWED=PENDING_INDEPENDENT_APPROVAL
IMPLEMENTATION_COMPLETE=NO
RUNTIME_TEST_EVIDENCE=NO
EXTERNAL_EFFECTS_ENABLED=NO
PRODUCTION_CHANGED=NO
```
