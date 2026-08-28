# Test Coverage Map

Frozen inputs: canonical main `844d13c7ba808653a7d982c63353bc67cdc9adef`; server capture `85b7898456abd4bdd0928b80ea925cafd8ad0f4c`; captured original source `7b9451b4db92982e5f0a4179d979ae94c043f943`. This document is analysis only.

Captured result: 207 passed, 3 skipped. Skipped tests remain gaps. Matching is thematic by filename and must be followed by contract-level parity tests; name similarity is not proof of behavioral equivalence.

| SERVER_TEST | MAIN_TEST | COVERAGE_STATUS | NEW_TEST_REQUIRED |
|---|---|---|---|
| tests/integration/test_durable_outbox.py | tests/integration/test_outbox_dispatch_lease.py | PARTIAL | contract parity plus infrastructure-backed duplicate/restart/failure cases |
| tests/integration/test_invalid_event_quarantine.py | NONE | MISSING | contract parity plus infrastructure-backed duplicate/restart/failure cases |
| tests/integration/test_telephony_reservation.py | NONE | MISSING | contract parity plus infrastructure-backed duplicate/restart/failure cases |
| tests/test_ai_services.py | NONE | MISSING | contract parity plus infrastructure-backed duplicate/restart/failure cases |
| tests/test_analytics.py | NONE | MISSING | contract parity plus infrastructure-backed duplicate/restart/failure cases |
| tests/test_appointments.py | NONE | MISSING | contract parity plus infrastructure-backed duplicate/restart/failure cases |
| tests/test_auth.py | NONE | MISSING | contract parity plus infrastructure-backed duplicate/restart/failure cases |
| tests/test_campaign_mappings.py | NONE | MISSING | contract parity plus infrastructure-backed duplicate/restart/failure cases |
| tests/test_daily_reporting.py | NONE | MISSING | contract parity plus infrastructure-backed duplicate/restart/failure cases |
| tests/test_delivery_policy.py | NONE | MISSING | contract parity plus infrastructure-backed duplicate/restart/failure cases |
| tests/test_entrypoints.py | NONE | MISSING | contract parity plus infrastructure-backed duplicate/restart/failure cases |
| tests/test_integrations_gateway.py | NONE | MISSING | contract parity plus infrastructure-backed duplicate/restart/failure cases |
| tests/test_ivr.py | NONE | MISSING | contract parity plus infrastructure-backed duplicate/restart/failure cases |
| tests/test_lead_reconciliation.py | NONE | MISSING | contract parity plus infrastructure-backed duplicate/restart/failure cases |
| tests/test_lead_reconciliation_api.py | NONE | MISSING | contract parity plus infrastructure-backed duplicate/restart/failure cases |
| tests/test_n8n_automation_contract.py | tests/test_canonical_contracts.py, tests/test_storage_contracts.py, services/connector-runtime/tests/test_storage_contract.py | PARTIAL | contract parity plus infrastructure-backed duplicate/restart/failure cases |
| tests/test_orchestration_contract.py | tests/test_canonical_contracts.py, tests/test_storage_contracts.py, services/connector-runtime/tests/test_storage_contract.py | PARTIAL | contract parity plus infrastructure-backed duplicate/restart/failure cases |
| tests/test_policy_engine.py | NONE | MISSING | contract parity plus infrastructure-backed duplicate/restart/failure cases |
| tests/test_postiz.py | NONE | MISSING | contract parity plus infrastructure-backed duplicate/restart/failure cases |
| tests/test_publisher_auth.py | NONE | MISSING | contract parity plus infrastructure-backed duplicate/restart/failure cases |
| tests/test_quarantine_security.py | tests/test_security.py | PARTIAL | contract parity plus infrastructure-backed duplicate/restart/failure cases |
| tests/test_realtime.py | NONE | MISSING | contract parity plus infrastructure-backed duplicate/restart/failure cases |
| tests/test_reliability.py | NONE | MISSING | contract parity plus infrastructure-backed duplicate/restart/failure cases |
| tests/test_scheduler.py | NONE | MISSING | contract parity plus infrastructure-backed duplicate/restart/failure cases |
| tests/test_schema_registry.py | NONE | MISSING | contract parity plus infrastructure-backed duplicate/restart/failure cases |
| tests/test_telephony_allocation.py | NONE | MISSING | contract parity plus infrastructure-backed duplicate/restart/failure cases |
| tests/test_transcription.py | NONE | MISSING | contract parity plus infrastructure-backed duplicate/restart/failure cases |
| tests/test_vicidial_dispositions.py | NONE | MISSING | contract parity plus infrastructure-backed duplicate/restart/failure cases |
| tests/test_vicidial_mapping_registry.py | NONE | MISSING | contract parity plus infrastructure-backed duplicate/restart/failure cases |
| tests/test_vicidial_mtls_client.py | NONE | MISSING | contract parity plus infrastructure-backed duplicate/restart/failure cases |
| tests/test_webphone.py | NONE | MISSING | contract parity plus infrastructure-backed duplicate/restart/failure cases |

## Mandatory infrastructure gaps

The three skipped captured tests do not count as PASS. Canonical acceptance must run PostgreSQL, Redis, NATS JetStream, Temporal, connector runtime, migrations, tenant isolation, idempotency, HMAC, JWT/OIDC, capability denial, inbox/outbox/replay/ledgers, all worker families, and provider mocks.
