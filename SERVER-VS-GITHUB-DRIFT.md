# Middleware server versus GitHub drift

This import intentionally preserves server reality and does not reconcile it with the prior branch contents. Deleted paths are GitHub-only; added paths are server-only; modified paths differ.

## Diff summary

```text
.dockerignore                                      |   40 +-
 .github/pull_request_template.md                   |   91 --
 .github/workflows/connector-runtime-api-ci.yml     |   91 --
 .github/workflows/connector-sdk-ci.yml             |   68 --
 .github/workflows/connector-storage-ci.yml         |   66 --
 .github/workflows/middleware-ci.yml                |  212 ----
 .github/workflows/release.yml                      |  188 ----
 .gitignore                                         |   72 +-
 Dockerfile.runtime                                 |   40 -
 README.md                                          |  174 +--
 app/__init__.py                                    |   10 +-
 app/canonical_contracts.py                         |   58 -
 app/commands.py                                    |  732 ------------
 app/config.py                                      |  664 -----------
 app/contracts.py                                   |   36 -
 app/main.py                                        |  453 ++------
 app/models.py                                      |   59 -
 app/nats_transport.py                              |  124 --
 app/observability.py                               |  207 ----
 app/replay.py                                      |  107 --
 app/runtime.py                                     |  116 --
 app/runtime_safety.py                              |   53 -
 app/security.py                                    |  298 -----
 app/service.py                                     |  113 --
 app/storage.py                                     | 1020 -----------------
 app/temporal_activities.py                         |  129 ---
 app/temporal_runtime.py                            |   55 -
 app/temporal_transport.py                          |   71 --
 app/temporal_workflows.py                          |  416 -------
 app/worker.py                                      |  216 ----
 architecture/CODESTRA_INTEGRATION_FABRIC_V2.md     |  134 ---
 architecture/__init__.py                           |    1 -
 architecture/routes.py                             |  260 -----
 architecture/site_architecture.py                  |  311 -----
 architecture/workstreams.py                        |  239 ----
 config/adapter-registry.v2.json                    |   13 -
 config/api-webhook-contracts.json                  |  155 ---
 config/beyvra-identity-event-contract.json         |   63 --
 config/caddy/auth.codestra.co.caddy.example        |   38 -
 config/capabilities.v2.json                        |   21 -
 config/connectivity-map.json                       |  624 -----------
 config/environments/production.runtime.env.example |   37 -
 config/environments/staging.runtime.env.example    |   36 -
 config/identity-access-map.json                    |    1 -
 config/integration-branches.json                   |  248 ----
 config/preproduction-safety.env.example            |   42 -
 config/runtime-profiles.v1.json                    |   69 --
 config/runtime-source-state.json                   |   22 -
 config/runtime.env.example                         |   77 --
 config/system-ownership.v2.json                    |   19 -
 connectors/capabilities.v1.json                    |   12 -
 connectors/generated/command-registry.v1.json      |    1 -
 connectors/generated/keycloak-clients.v1.json      |    1 -
 connectors/generated/kong-routes.v1.json           |    1 -
 connectors/generated/n8n-workflow-packs.v1.json    |    1 -
 .../manifests/beyvra-nonfinancial.connector.json   |    1 -
 connectors/manifests/klyrow-email.connector.json   |    1 -
 connectors/manifests/kyqra-crawler.connector.json  |    1 -
 connectors/manifests/odoo-19.connector.json        |    1 -
 connectors/manifests/postly-social.connector.json  |    1 -
 .../manifests/provisioning-service.connector.json  |    1 -
 connectors/manifests/telnexa-sms.connector.json    |    1 -
 .../manifests/vicidial-restricted.connector.json   |    1 -
 contracts/automation/n8n-control-plane.v2.json     |  116 --
 contracts/automation/operation-policy.v2.json      |  396 -------
 contracts/beyvra-identity-provisioned.schema.json  |   83 --
 contracts/connectors/cloudevent.v1.schema.json     |    1 -
 .../connectors/connector-management-api.v1.yaml    |  542 ---------
 .../connectors/connector-manifest.v1.schema.json   |    1 -
 contracts/event-envelope.schema.json               |    6 -
 contracts/http-conventions.md                      |  119 --
 contracts/lead-intake.schema.json                  |  253 -----
 contracts/observability-conventions.md             |  125 ---
 contracts/odoo-lead-command.schema.json            |  190 ----
 contracts/platform/command-envelope.v1.schema.json |   66 --
 contracts/platform/contract-catalog.v1.json        |   37 -
 contracts/platform/event-envelope.v1.schema.json   |   82 --
 contracts/platform/integration-fabric-api.v2.yaml  |  272 -----
 contracts/provider-transport-conventions.md        |  125 ---
 contracts/release-manifest.v1.schema.json          |  110 --
 contracts/runtime-safety-readback.v1.schema.json   |   66 --
 docs/BEYVRA-IDENTITY-EVENT.md                      |   32 -
 docs/CANONICAL-CONTRACTS.md                        |   27 -
 docs/CI-ENVIRONMENTS-AND-HANDOFF.md                |  129 ---
 docs/COMMAND-LEDGER.md                             |   43 -
 docs/CONNECTIVITY-AND-COMMUNICATION.md             |  211 ----
 docs/IDENTITY-API-WEBHOOK-CONTRACTS.md             |  114 --
 docs/IMMUTABLE-EVENT-LEDGER.md                     |   28 -
 docs/INTEGRATION-BRANCHES.md                       |  160 ---
 docs/LEAD-INGESTION-TO-ODOO.md                     |  142 ---
 docs/RELEASE-SUPPLY-CHAIN.md                       |   76 --
 docs/RUNTIME-ENVIRONMENT-LOCKS.md                  |   34 -
 docs/RUNTIME-INTAKE-V1.md                          |   99 --
 docs/SERVER-A-GIT-SYNC.md                          |  130 ---
 docs/SERVER-CONNECTION.md                          |  494 --------
 docs/SITE-ARCHITECTURE.md                          |  231 ----
 docs/SYNTHETIC-STAGING-ACCEPTANCE.md               |   79 --
 docs/TEMPORAL-WORKFLOWS.md                         |   37 -
 docs/auth-codestra-co-edge-repair.md               |   57 -
 docs/auth-codestra-co-keycloak-contract.md         |   75 --
 docs/branches/INTEGRATION_FABRIC_BRANCH_MAP.md     |   43 -
 docs/connectors/CODESTRA_CONNECTOR_SDK_V1.md       |  155 ---
 docs/connectors/CONNECTOR_RUNTIME_API_V1.md        |   90 --
 .../CONNECTOR_SDK_STANDARDS_PROFILE_V1.md          |  133 ---
 docs/connectors/CONNECTOR_STORAGE_V1.md            |    5 -
 docs/integrations/beyvra-n8n-v2.md                 |   39 -
 docs/integrations/n8n-control-plane-v2.md          |  170 ---
 docs/releases/2026-08-26-server-a-sync.md          |   30 -
 middleware/__init__.py                             |    1 -
 middleware/connector_sdk/__init__.py               |  126 ---
 middleware/connector_sdk/catalog.py                |  200 ----
 middleware/connector_sdk/errors.py                 |   61 -
 middleware/connector_sdk/generation.py             |  114 --
 middleware/connector_sdk/interfaces.py             |  131 ---
 middleware/connector_sdk/manifest.py               |  677 -----------
 middleware/connector_sdk/models.py                 |  286 -----
 middleware/connector_sdk/registry.py               |  294 -----
 middleware/connector_sdk/runtime.py                |  243 ----
 middleware/connector_sdk/standards.py              |  258 -----
 middleware/connector_sdk/webhooks.py               |  446 --------
 pytest.ini                                         |    3 -
 requirements-runtime.in                            |   12 -
 requirements-runtime.txt                           | 1069 ------------------
 requirements-test.in                               |    5 +-
 requirements-test.txt                              | 1097 ------------------
 scripts/audit_all_workstream_sync.py               |  103 --
 scripts/audit_workstream_sync.py                   |  120 --
 scripts/discover_auth_codestra_edge.sh             |   98 --
 scripts/discover_middleware_runtime.sh             |  121 --
 scripts/generate_connector_artifacts.py            |   68 --
 scripts/integration_ci.sh                          |   72 --
 scripts/migrate_runtime.py                         |   32 -
 scripts/nats_integration_ci.sh                     |   63 --
 scripts/project_ci.sh                              |   36 -
 scripts/release_manifest.py                        |  559 ---------
 scripts/run_ci.sh                                  |   67 --
 scripts/scaffold_connector.py                      |  164 ---
 scripts/staging_synthetic_acceptance.py            |  326 ------
 scripts/synthetic_acceptance_ci.sh                 |  103 --
 scripts/temporal_integration_ci.sh                 |   21 -
 scripts/validate_beyvra_identity_contract.py       |   92 --
 scripts/validate_connectivity_contracts.py         |  516 ---------
 scripts/validate_connector_sdk.py                  |  318 ------
 scripts/validate_identity_webhook_contracts.py     |  567 ----------
 scripts/validate_integration_fabric.py             |   95 --
 scripts/validate_n8n_flow.py                       |   68 --
 scripts/validate_release_supply_chain.py           |  195 ----
 scripts/validate_repository.py                     |  300 -----
 scripts/validate_runtime_profiles.py               |   92 --
 scripts/validate_site_routes_and_leads.py          |  325 ------
 scripts/validate_site_workstreams.py               |  286 -----
 scripts/validate_workstream_manifest.py            |  219 ----
 scripts/verify_event_ledger.py                     |   54 -
 services/connector-runtime/alembic.ini             |   31 -
 services/connector-runtime/migrations/env.py       |   33 -
 .../connector-runtime/migrations/script.py.mako    |   20 -
 .../versions/20260828_0001_connector_runtime.py    |  176 ---
 .../versions/20260828_0002_tenant_parent_fks.py    |   98 --
 .../versions/20260828_0003_management_api.py       |   44 -
 .../20260828_0004_webhook_ingress_lookup.py        |  138 ---
 services/connector-runtime/pyproject.toml          |   38 -
 .../connector-runtime/scripts/test_postgres.sh     |   75 --
 .../src/codestra_connector_runtime/__init__.py     |    3 -
 .../src/codestra_connector_runtime/api/__init__.py |    1 -
 .../src/codestra_connector_runtime/api/app.py      |  702 ------------
 .../src/codestra_connector_runtime/api/auth.py     |  228 ----
 .../src/codestra_connector_runtime/api/config.py   |  101 --
 .../src/codestra_connector_runtime/api/crypto.py   |  106 --
 .../src/codestra_connector_runtime/api/cursor.py   |   88 --
 .../src/codestra_connector_runtime/api/database.py |   74 --
 .../src/codestra_connector_runtime/api/problems.py |  110 --
 .../codestra_connector_runtime/api/repository.py   | 1184 --------------------
 .../src/codestra_connector_runtime/api/schemas.py  |  185 ---
 .../api/webhook_ingress.py                         |  240 ----
 .../src/codestra_connector_runtime/db.py           |   48 -
 .../src/codestra_connector_runtime/main.py         |    5 -
 .../src/codestra_connector_runtime/storage.py      |  108 --
 .../connector-runtime/tests/test_api_helpers.py    |   99 --
 .../connector-runtime/tests/test_management_api.py |  405 -------
 .../tests/test_storage_contract.py                 |  217 ----
 .../tests/test_storage_tenant_foreign_keys.py      |  208 ----
 tests/__init__.py                                  |    0
 tests/conftest.py                                  |  130 ---
 tests/integration/conftest.py                      |   56 -
 tests/integration/test_nats_jetstream.py           |  187 ----
 tests/integration/test_outbox_dispatch_lease.py    |  161 ---
 tests/integration/test_postgres_redis.py           |  746 ------------
 tests/integration/test_synthetic_acceptance.py     |  345 ------
 tests/integration/test_temporal_workflows.py       |  266 -----
 tests/test_canonical_contracts.py                  |  192 ----
 tests/test_commands.py                             |  185 ---
 tests/test_connector_sdk_review_findings.py        |  257 -----
 tests/test_connector_sdk_standards_v1.py           |   89 --
 tests/test_connector_sdk_v1.py                     |  639 -----------
 tests/test_models.py                               |   55 -
 tests/test_nats_transport.py                       |  105 --
 tests/test_observability.py                        |   89 --
 tests/test_release_manifest.py                     |  120 --
 tests/test_replay.py                               |    9 -
 tests/test_runtime.py                              |  360 ------
 tests/test_security.py                             |  404 -------
 tests/test_staging_acceptance.py                   |  200 ----
 tests/test_storage_contracts.py                    |  165 ---
 tests/test_temporal_transport.py                   |   78 --
 tests/test_worker.py                               |  217 ----
 workers/run_outbox.py                              |   58 -
 workers/run_temporal.py                            |   48 -
 207 files changed, 112 insertions(+), 33783 deletions(-)
```

## Working-tree inventory before capture commit

```text
M .dockerignore
 D .github/pull_request_template.md
 D .github/workflows/connector-runtime-api-ci.yml
 D .github/workflows/connector-sdk-ci.yml
 D .github/workflows/connector-storage-ci.yml
 D .github/workflows/middleware-ci.yml
 D .github/workflows/release.yml
 M .gitignore
 D Dockerfile.runtime
 M README.md
 M app/__init__.py
 D app/canonical_contracts.py
 D app/commands.py
 D app/config.py
 D app/contracts.py
 M app/main.py
 D app/models.py
 D app/nats_transport.py
 D app/observability.py
 D app/replay.py
 D app/runtime.py
 D app/runtime_safety.py
 D app/security.py
 D app/service.py
 D app/storage.py
 D app/temporal_activities.py
 D app/temporal_runtime.py
 D app/temporal_transport.py
 D app/temporal_workflows.py
 D app/worker.py
 D architecture/CODESTRA_INTEGRATION_FABRIC_V2.md
 D architecture/__init__.py
 D architecture/routes.py
 D architecture/site_architecture.py
 D architecture/workstreams.py
 D config/adapter-registry.v2.json
 D config/api-webhook-contracts.json
 D config/beyvra-identity-event-contract.json
 D config/caddy/auth.codestra.co.caddy.example
 D config/capabilities.v2.json
 D config/connectivity-map.json
 D config/environments/production.runtime.env.example
 D config/environments/staging.runtime.env.example
 D config/identity-access-map.json
 D config/integration-branches.json
 D config/preproduction-safety.env.example
 D config/runtime-profiles.v1.json
 D config/runtime-source-state.json
 D config/runtime.env.example
 D config/system-ownership.v2.json
 D connectors/capabilities.v1.json
 D connectors/generated/command-registry.v1.json
 D connectors/generated/keycloak-clients.v1.json
 D connectors/generated/kong-routes.v1.json
 D connectors/generated/n8n-workflow-packs.v1.json
 D connectors/manifests/beyvra-nonfinancial.connector.json
 D connectors/manifests/klyrow-email.connector.json
 D connectors/manifests/kyqra-crawler.connector.json
 D connectors/manifests/odoo-19.connector.json
 D connectors/manifests/postly-social.connector.json
 D connectors/manifests/provisioning-service.connector.json
 D connectors/manifests/telnexa-sms.connector.json
 D connectors/manifests/vicidial-restricted.connector.json
 D contracts/automation/n8n-control-plane.v2.json
 D contracts/automation/operation-policy.v2.json
 D contracts/beyvra-identity-provisioned.schema.json
 D contracts/connectors/cloudevent.v1.schema.json
 D contracts/connectors/connector-management-api.v1.yaml
 D contracts/connectors/connector-manifest.v1.schema.json
D  contracts/connectors/connector-storage.v1.sql
 D contracts/event-envelope.schema.json
 D contracts/http-conventions.md
 D contracts/lead-intake.schema.json
 D contracts/observability-conventions.md
 D contracts/odoo-lead-command.schema.json
 D contracts/platform/command-envelope.v1.schema.json
 D contracts/platform/contract-catalog.v1.json
 D contracts/platform/event-envelope.v1.schema.json
 D contracts/platform/integration-fabric-api.v2.yaml
 D contracts/provider-transport-conventions.md
 D contracts/release-manifest.v1.schema.json
 D contracts/runtime-safety-readback.v1.schema.json
 D docs/BEYVRA-IDENTITY-EVENT.md
 D docs/CANONICAL-CONTRACTS.md
 D docs/CI-ENVIRONMENTS-AND-HANDOFF.md
 D docs/COMMAND-LEDGER.md
 D docs/CONNECTIVITY-AND-COMMUNICATION.md
 D docs/IDENTITY-API-WEBHOOK-CONTRACTS.md
 D docs/IMMUTABLE-EVENT-LEDGER.md
 D docs/INTEGRATION-BRANCHES.md
 D docs/LEAD-INGESTION-TO-ODOO.md
 D docs/RELEASE-SUPPLY-CHAIN.md
 D docs/RUNTIME-ENVIRONMENT-LOCKS.md
 D docs/RUNTIME-INTAKE-V1.md
 D docs/SERVER-A-GIT-SYNC.md
 D docs/SERVER-CONNECTION.md
 D docs/SITE-ARCHITECTURE.md
 D docs/SYNTHETIC-STAGING-ACCEPTANCE.md
 D docs/TEMPORAL-WORKFLOWS.md
 D docs/auth-codestra-co-edge-repair.md
 D docs/auth-codestra-co-keycloak-contract.md
 D docs/branches/INTEGRATION_FABRIC_BRANCH_MAP.md
 D docs/connectors/CODESTRA_CONNECTOR_SDK_V1.md
 D docs/connectors/CONNECTOR_RUNTIME_API_V1.md
 D docs/connectors/CONNECTOR_SDK_STANDARDS_PROFILE_V1.md
 D docs/connectors/CONNECTOR_STORAGE_V1.md
 D docs/integrations/beyvra-n8n-v2.md
 D docs/integrations/n8n-control-plane-v2.md
 D docs/releases/2026-08-26-server-a-sync.md
 D middleware/__init__.py
 D middleware/connector_sdk/__init__.py
 D middleware/connector_sdk/catalog.py
 D middleware/connector_sdk/errors.py
 D middleware/connector_sdk/generation.py
 D middleware/connector_sdk/interfaces.py
 D middleware/connector_sdk/manifest.py
 D middleware/connector_sdk/models.py
 D middleware/connector_sdk/registry.py
 D middleware/connector_sdk/runtime.py
 D middleware/connector_sdk/standards.py
 D middleware/connector_sdk/webhooks.py
 D pytest.ini
 D requirements-runtime.in
 D requirements-runtime.txt
 M requirements-test.in
 D requirements-test.txt
 D scripts/audit_all_workstream_sync.py
 D scripts/audit_workstream_sync.py
 D scripts/discover_auth_codestra_edge.sh
 D scripts/discover_middleware_runtime.sh
 D scripts/generate_connector_artifacts.py
 D scripts/integration_ci.sh
 D scripts/migrate_runtime.py
 D scripts/nats_integration_ci.sh
 D scripts/project_ci.sh
 D scripts/release_manifest.py
 D scripts/run_ci.sh
 D scripts/scaffold_connector.py
 D scripts/staging_synthetic_acceptance.py
 D scripts/synthetic_acceptance_ci.sh
 D scripts/temporal_integration_ci.sh
 D scripts/validate_beyvra_identity_contract.py
 D scripts/validate_connectivity_contracts.py
 D scripts/validate_connector_sdk.py
 D scripts/validate_identity_webhook_contracts.py
 D scripts/validate_integration_fabric.py
 D scripts/validate_n8n_flow.py
 D scripts/validate_release_supply_chain.py
 D scripts/validate_repository.py
 D scripts/validate_runtime_profiles.py
 D scripts/validate_site_routes_and_leads.py
 D scripts/validate_site_workstreams.py
 D scripts/validate_workstream_manifest.py
 D scripts/verify_event_ledger.py
 D services/connector-runtime/alembic.ini
 D services/connector-runtime/migrations/env.py
 D services/connector-runtime/migrations/script.py.mako
 D services/connector-runtime/migrations/versions/20260828_0001_connector_runtime.py
 D services/connector-runtime/migrations/versions/20260828_0002_tenant_parent_fks.py
 D services/connector-runtime/migrations/versions/20260828_0003_management_api.py
 D services/connector-runtime/migrations/versions/20260828_0004_webhook_ingress_lookup.py
 D services/connector-runtime/pyproject.toml
 D services/connector-runtime/scripts/test_postgres.sh
 D services/connector-runtime/src/codestra_connector_runtime/__init__.py
 D services/connector-runtime/src/codestra_connector_runtime/api/__init__.py
 D services/connector-runtime/src/codestra_connector_runtime/api/app.py
 D services/connector-runtime/src/codestra_connector_runtime/api/auth.py
 D services/connector-runtime/src/codestra_connector_runtime/api/config.py
 D services/connector-runtime/src/codestra_connector_runtime/api/crypto.py
 D services/connector-runtime/src/codestra_connector_runtime/api/cursor.py
 D services/connector-runtime/src/codestra_connector_runtime/api/database.py
 D services/connector-runtime/src/codestra_connector_runtime/api/problems.py
 D services/connector-runtime/src/codestra_connector_runtime/api/repository.py
 D services/connector-runtime/src/codestra_connector_runtime/api/schemas.py
 D services/connector-runtime/src/codestra_connector_runtime/api/webhook_ingress.py
 D services/connector-runtime/src/codestra_connector_runtime/db.py
 D services/connector-runtime/src/codestra_connector_runtime/main.py
 D services/connector-runtime/src/codestra_connector_runtime/storage.py
 D services/connector-runtime/tests/test_api_helpers.py
 D services/connector-runtime/tests/test_management_api.py
 D services/connector-runtime/tests/test_storage_contract.py
 D services/connector-runtime/tests/test_storage_tenant_foreign_keys.py
 D tests/__init__.py
 D tests/conftest.py
 D tests/integration/conftest.py
 D tests/integration/test_nats_jetstream.py
 D tests/integration/test_outbox_dispatch_lease.py
 D tests/integration/test_postgres_redis.py
 D tests/integration/test_synthetic_acceptance.py
 D tests/integration/test_temporal_workflows.py
 D tests/test_canonical_contracts.py
 D tests/test_commands.py
 D tests/test_connector_sdk_review_findings.py
 D tests/test_connector_sdk_standards_v1.py
 D tests/test_connector_sdk_v1.py
 D tests/test_models.py
 D tests/test_nats_transport.py
 D tests/test_observability.py
 D tests/test_release_manifest.py
 D tests/test_replay.py
 D tests/test_runtime.py
 D tests/test_security.py
 D tests/test_staging_acceptance.py
 D tests/test_storage_contracts.py
 D tests/test_temporal_transport.py
 D tests/test_worker.py
 D workers/run_outbox.py
 D workers/run_temporal.py
?? .env.example
?? .github/workflows/sign-rc3p-openvex.yml
?? Dockerfile
?? Dockerfile.base-test
?? Dockerfile.derivative-test
?? Dockerfile.mtls-client
?? ENVIRONMENT-VARIABLES.md
?? MIDDLEWARE-SERVER-SOURCE-MANIFEST.md
?? Makefile
?? SERVER-VS-GITHUB-DRIFT.md
?? alembic.ini
?? app.py
?? app/adapters/
?? app/api/
?? app/core/
?? app/db/
?? app/entrypoints/
?? app/integrations/
?? app/metrics.py
?? app/schemas/
?? app/workers/
?? contracts/cross-server/
?? contracts/telephony-publisher/
?? deploy/
?? deployed-config.py
?? docs/architecture.md
?? docs/credential-rotation-plan.md
?? docs/invalid-event-quarantine.md
?? docs/postgres-schema.md
?? docs/redis-key-model.md
?? docs/security.md
?? docs/security/
?? docs/telephony/
?? docs/vicidial-private-mtls.md
?? integrations/
?? middleware.private-mtls.env.example
?? migrations/env.py
?? migrations/versions/
?? monitoring/
?? pyproject.toml
?? reports/
?? requirements-test.lock
?? requirements.in
?? requirements.lock
?? schemas/
?? scripts/build_extension_inventory.py
?? scripts/build_vicidial_campaign_registry.py
?? scripts/export_schemas.py
?? security/
?? server-baseline/
?? services/realtime/
?? services/transcription/
?? tests/integration/test_durable_outbox.py
?? tests/integration/test_invalid_event_quarantine.py
?? tests/integration/test_telephony_reservation.py
?? tests/test_ai_services.py
?? tests/test_analytics.py
?? tests/test_appointments.py
?? tests/test_auth.py
?? tests/test_campaign_mappings.py
?? tests/test_daily_reporting.py
?? tests/test_delivery_policy.py
?? tests/test_entrypoints.py
?? tests/test_integrations_gateway.py
?? tests/test_ivr.py
?? tests/test_lead_reconciliation.py
?? tests/test_lead_reconciliation_api.py
?? tests/test_n8n_automation_contract.py
?? tests/test_orchestration_contract.py
?? tests/test_policy_engine.py
?? tests/test_postiz.py
?? tests/test_publisher_auth.py
?? tests/test_quarantine_security.py
?? tests/test_realtime.py
?? tests/test_reliability.py
?? tests/test_scheduler.py
?? tests/test_schema_registry.py
?? tests/test_telephony_allocation.py
?? tests/test_transcription.py
?? tests/test_vicidial_dispositions.py
?? tests/test_vicidial_mapping_registry.py
?? tests/test_vicidial_mtls_client.py
?? tests/test_webphone.py
```
