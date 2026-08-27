# Middleware ↔ n8n Automation Control Plane v2

## Exact cross-repository contract

```text
N8N repository: appolon1908-hue/N8N
N8N contract branch: contract/automation-control-plane-v2
N8N contract SHA: e3a3e97ab0da0d7df78bba52b18904e5f83e6dbe
Middleware repository: appolon1908-hue/Middleware-
Middleware branch: contract/n8n-automation-control-plane-v2
Production activation: NOT AUTHORIZED
```

## Authority boundary

Middleware is the only cross-system mutation boundary. n8n is an orchestration engine and may call Middleware only.

n8n must never receive or use direct credentials for:

- Odoo or Odoo PostgreSQL;
- Keycloak administration;
- VICIdial, Asterisk, AMI, MariaDB, trunks, or carriers;
- Telnexa, Jasmin, SMPP, RabbitMQ, or provider accounts;
- Klyrow, Postal, Mautic, or provider administration;
- Kyqra, Crawlee, Playwright, Redis, or result databases;
- Postly or social-provider accounts;
- MoneyBee lenders, credit providers, funding, or payment providers;
- Breero, LARIM-A, Freight, Beyvra, or their databases.

Public provider callbacks terminate at Caddy/Kong/Middleware, not n8n.

## Durable handoff

In one PostgreSQL transaction Middleware writes:

```text
normalized_event
automation_job
automation_dispatch_outbox
audit_record
```

The outbox sends a private, authenticated wake containing only:

```json
{
  "job_id": "uuid",
  "workflow_key": "codestra.crm.lead-intake.v1",
  "workflow_version": 1,
  "correlation_id": "correlation-id",
  "delivery_token": "one-use-signed-token"
}
```

n8n must atomically claim the durable job before reading the safe payload or requesting an effect.

## Required API surface

```text
POST /v2/automation/jobs/claim
GET  /v2/automation/jobs/{job_id}
POST /v2/automation/jobs/{job_id}/heartbeat
POST /v2/automation/jobs/{job_id}/steps
POST /v2/automation/jobs/{job_id}/complete
POST /v2/automation/jobs/{job_id}/fail

POST /v2/automation/commands
GET  /v2/automation/commands/{command_id}

POST /v2/automation/approvals
GET  /v2/automation/approvals/{approval_id}

POST /v2/automation/dead-letters/{dead_letter_id}/replay
POST /v2/automation/jobs/reconcile
GET  /v2/automation/capabilities/{capability}
```

## Durable tables

Implement additive, tenant-scoped schema for:

```text
automation_workflows
automation_jobs
automation_job_attempts
automation_job_steps
automation_job_leases
automation_dispatch_outbox
automation_commands
automation_command_attempts
automation_approvals
automation_dead_letters
automation_reconciliation_runs
automation_reconciliation_items
```

Every externally meaningful row carries tenant, event, correlation, causation, idempotency, actor, workflow version, capability, timestamps, state, optimistic version, and safe audit metadata.

## Job states

```text
PENDING
DISPATCHING
CLAIMED
RUNNING
WAITING_APPROVAL
WAITING_TIMER
WAITING_COMMAND
RETRY_SCHEDULED
COMPLETED
FAILED_TERMINAL
DEAD_LETTER
CANCELLED
```

Lease tokens prevent stale n8n executions from completing or failing a job. A timeout is `UNKNOWN` and requires destination reconciliation before another external submission.

## Security

Use separate short-lived Keycloak service identities for platform, CRM, telephony, messaging, crawler, product, privacy, and operations automation. Every token audience targets Middleware only.

All links require:

```text
Authorization: Bearer <short-lived token>
X-Correlation-ID
X-Causation-ID
Idempotency-Key
traceparent when available
```

Private wake delivery additionally requires a one-use delivery token, source allowlist, rate limit, replay protection, and bounded timestamp policy.

## Capability enforcement

Capabilities are evaluated by Middleware at claim time and immediately before every external effect. n8n activation never enables a capability.

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
LENDERS_LIVE_SUBMISSION
ENABLE_EXTERNAL_DELIVERY
```

All remain false until separate exact-SHA canary approval.

## Matching Middleware branches

```text
contract/n8n-automation-control-plane-v2
integration/n8n-automation-v2
integration/odoo-n8n-automation-v2
integration/moneybee-n8n-automation-v2
integration/keycloak-n8n-automation-v2
```

Provider/product adapter work remains in its existing focused integration branch.

## Required tests

```text
tenant isolation
exact replay
conflicting replay
concurrent duplicate
lease loss
expired job
capability disabled
unknown outcome reconciliation
bounded retry
dead-letter durability
protected replay
approval rejection
Middleware restart
n8n restart
Redis outage without business-data loss
PostgreSQL outage fail closed
zero external effects in staging
backup/restore
rollback rehearsal
```

## Release rule

```text
reviewed feature branch
 -> exact-head CI and approval
 -> protected merge
 -> immutable image from merged SHA
 -> staging with every external capability false
 -> duplicate/replay/tenant/restart/rollback evidence
 -> separate production workflow activation approval
 -> separate capability canary approval
```

No live service, workflow, credential, database, route, or provider state is changed by this contract document.
