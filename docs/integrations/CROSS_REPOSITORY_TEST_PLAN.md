# Cross-Repository Integration Test Plan

## Safety rule

No test may enable a live provider effect. Use synthetic tenants, disposable databases, private networks, test credentials, and provider simulators. Keep every capability flag false.

## Required layers

### Registry and authority

- exactly 54 unique repositories;
- one isolation cell per system;
- Middleware is the only cross-system write authority;
- principal repositories match the authority registry;
- legacy and placeholder systems stay disabled;
- all connector activation fields stay false.

### Identity and tenancy

Reject missing or invalid tokens, wrong issuer/audience/client, expired tokens, missing scope, tenant mismatch, cross-tenant identifiers, wildcard tenant access, and unauthorized role combinations.

### Idempotency and concurrency

Prove first-write acceptance, exact replay, changed-body conflict, one result under concurrency, optimistic-version rejection, stale-lease rejection, restart-safe replay, and tenant-scoped keys.

### Signed callbacks

For Odoo, Klyrow, Telnexa, Postiz, Kyqra, VICIdial, provisioning, and Beyvra events, prove signature and timestamp validation, event-ID replay control, body limits, trusted tenant mapping, durable acknowledgement, and changed-body conflict.

### Outbox and reconciliation

Prove atomic command/audit/outbox persistence, lease recovery, bounded retry, dead letters, transport deduplication, and protected replay. A timeout after possible destination acceptance must enter `UNKNOWN`, perform authoritative read-back, and reach `RECONCILING` before completion or failure. A second external action is forbidden until resubmission is proven safe.

### Adapter checks

- **Odoo:** mappings, campaign isolation, read-back, false-success prevention.
- **Klyrow:** consent, suppression, sender/domain eligibility, signed delivery events, no duplicate email.
- **Telnexa:** E.164, Unicode, segments, opt-out, DLR/inbound events, no duplicate SMS.
- **VICIdial:** campaign isolation, agent/supervisor scope, no public administration or dialing.
- **Postiz:** account authorization, approvals, provider references, no duplicate publication.
- **Kyqra:** robots/domain policy, private-network denial, signed result events, no direct Odoo write.
- **Provisioning:** plan-only default, compensation, read-back, drift, and secret rejection.
- **Beyvra:** allow only nonfinancial operations and reject every financial/trading command family.

### Product callers

For Codestra, MoneyBee, BREERO, Freight, LARIMÍA, Booked4Seasons, restaurant, Telnexa web, and Klyrow web, prove same-origin intake, least-privilege product identity, allowed and forbidden targets, tenant isolation, safe status reads, and no browser provider credentials.

### Observability and analytics

Prove private metrics endpoints, safe labels, governed Alertmanager handoff, approved Grafana datasources, curated read-only Superset datasets, non-mutating exporters/probes, and no OpenBao initialization outside its isolated test environment.

### Disposable journey

```text
synthetic caller -> Caddy simulator -> Kong policy -> Keycloak fixture
-> Middleware -> disposable persistence/transport -> provider simulator
-> signed callback -> reconciliation -> read model -> SDK/dashboard consumer
```

Exercise success, denial, replay, concurrency, cross-tenant, timeout, unknown-outcome, dead-letter, and rollback paths.

## Exit gate

```text
STATIC_REGISTRY=PASS
CONTRACT_COMPATIBILITY=PASS
IDENTITY_TENANT_ISOLATION=PASS
IDEMPOTENCY_CONCURRENCY=PASS
WEBHOOK_REPLAY=PASS
OUTBOX_RECONCILIATION=PASS
ADAPTER_TESTS=PASS
PRODUCT_CALLER_TESTS=PASS
OBSERVABILITY_READ_ONLY=PASS
DISPOSABLE_E2E=PASS
LIVE_EFFECTS_ENABLED=NO
DEPLOYMENT_STATE=DISABLED
```
