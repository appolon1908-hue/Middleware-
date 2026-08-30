# Middleware Complete-System Integration Authority

This directory is the human-readable companion to the machine-readable integration registries.

## Read in this order

1. [`COMPLETE_SYSTEM_INTEGRATION_MAP.md`](COMPLETE_SYSTEM_INTEGRATION_MAP.md) — all 54 repositories, isolation cells, authority, integration mode, and prohibitions.
2. [`INTEGRATION_STATUS_AND_ROADMAP.md`](INTEGRATION_STATUS_AND_ROADMAP.md) — what is done, partial, missing, blocked, and the ordered implementation program.
3. [`ROUTE_EVENT_COMMAND_CATALOG.md`](ROUTE_EVENT_COMMAND_CATALOG.md) — current effectful adapter prefixes, capabilities, signed routes, event types, state rules, and planned families.
4. [`CROSS_REPOSITORY_TEST_PLAN.md`](CROSS_REPOSITORY_TEST_PLAN.md) — static, contract, identity, idempotency, webhook, outbox, reconciliation, adapter, product, observability, and disposable E2E gates.

## Machine-readable authority

- `config/system-integration-registry.v3.json`
- `config/integration-cells.v1.json`
- `config/integration-status.v1.json`
- `config/product-integration-clients.v1.json`
- `config/repository-authorities.v1.json`
- `config/adapter-registry.v2.json`
- `config/control-plane-callers.v1.json`
- `contracts/platform/system-integration-registry.v3.schema.json`
- `scripts/validate_complete_system_integrations.py`

## Permanent boundary

```text
MIDDLEWARE_ONLY_CROSS_SYSTEM_WRITE_AUTHORITY=YES
DIRECT_N8N_PROVIDER_ACCESS=NO
FRONTEND_PROVIDER_CREDENTIALS=NO
UNKNOWN_OUTCOME_AUTO_RETRY=NO
LIVE_EFFECTS_ENABLED=NO
DEPLOYMENT_STATE=DISABLED
PRODUCTION_STATE=NO_GO
```

This source package does not deploy or activate any system.
