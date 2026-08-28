# Middleware Server Functionality Inventory

Frozen inputs: canonical main `844d13c7ba808653a7d982c63353bc67cdc9adef`; server capture `85b7898456abd4bdd0928b80ea925cafd8ad0f4c`; captured original source `7b9451b4db92982e5f0a4179d979ae94c043f943`. This document is analysis only.

## Scope and completeness

All 32 captured running containers are mapped below. Containers sharing an image or responsibility remain separate evidence records but are not treated as separate applications. The future source authority is one approved Git SHA with explicit API, worker, connector-runtime, adapter, PostgreSQL, and Redis build/deployment targets.

## F001 — middleware-vicidial-adapter

FUNCTION_ID=F001
FUNCTION_NAME=middleware-vicidial-adapter
BUSINESS_PURPOSE=Preserve restricted telephony capabilities behind OAuth2+mTLS, explicit command prefixes and mandatory read-back.

SERVER_SOURCE_FILES=app/entrypoints/vicidial_adapter.py
SERVER_ENTRYPOINT=`/usr/local/bin/live-delivery-admission python -m app.entrypoints.vicidial_adapter`
SERVER_CONTAINER=`codestra-middleware-vicidial-adapter-1`
SERVER_IMAGE=`codestra/middleware@sha256:1a9e13a0c930d36076b5742e17f948dc85d9bc6ace90e58052756c8b1ad42700`
SERVER_REVISION=`b3ca9aa458fef843e3065aeff3397c656349f138`

SERVER_API_PATHS=runtime health/readiness/dependencies
SERVER_DATABASE_TABLES=see DATABASE-SCHEMA-MAP.md; worker-specific ownership requires command contracts
SERVER_REDIS_USAGE=configuration/coordination only; see REDIS-USAGE-MAP.md
SERVER_QUEUE_USAGE=legacy PostgreSQL polling/outbox, direct HTTP, or runtime-specific loop; see EVENT-TRANSPORT-MAP.md
SERVER_EXTERNAL_SYSTEMS=Odoo, n8n, VICIdial, Asterisk/PJSIP, Postiz/Postly, SMS provider, email provider, provisioning service

AUTH_MODEL=legacy shared bearer, HMAC, mTLS, or service credential depending on boundary; see AUTHORIZATION-MAP.md
TENANT_MODEL=server payload/header/campaign conventions must be replaced by verified canonical tenant context
IDEMPOTENCY=server-specific; durable ledger/inbox equivalence test required
RETRY_MODEL=server worker retry/poll loop; normalize in connector/Temporal policy
ERROR_MODEL=server-specific HTTP/worker errors; normalize to canonical command and connector errors
OBSERVABILITY=health `healthy` plus logs; canonical metrics/audit/correlation required

CANONICAL_MAIN_EQUIVALENT=`vicidial-restricted` connector
CLASSIFICATION=KEEP_AND_PORT
RATIONALE=Preserve restricted telephony capabilities behind OAuth2+mTLS, explicit command prefixes and mandatory read-back.
TEST_REQUIRED=VICIdial mock, mTLS, capability denial, idempotency, timeout and unknown-outcome tests
SERVER_DEPENDENCIES=VICIdial private endpoints; command ledger; telephony events

## F002 — middleware-telephony-provisioning

FUNCTION_ID=F002
FUNCTION_NAME=middleware-telephony-provisioning
BUSINESS_PURPOSE=Provisioning lifecycle/state belongs to provisioning service; Middleware retains tenant/capability authorization and orchestration only.

SERVER_SOURCE_FILES=app/entrypoints/telephony_provisioning.py
SERVER_ENTRYPOINT=`/usr/local/bin/live-delivery-admission python -m app.entrypoints.telephony_provisioning`
SERVER_CONTAINER=`codestra-middleware-telephony-provisioning-1`
SERVER_IMAGE=`codestra/middleware@sha256:1a9e13a0c930d36076b5742e17f948dc85d9bc6ace90e58052756c8b1ad42700`
SERVER_REVISION=`b3ca9aa458fef843e3065aeff3397c656349f138`

SERVER_API_PATHS=runtime health/readiness/dependencies
SERVER_DATABASE_TABLES=see DATABASE-SCHEMA-MAP.md; worker-specific ownership requires command contracts
SERVER_REDIS_USAGE=configuration/coordination only; see REDIS-USAGE-MAP.md
SERVER_QUEUE_USAGE=legacy PostgreSQL polling/outbox, direct HTTP, or runtime-specific loop; see EVENT-TRANSPORT-MAP.md
SERVER_EXTERNAL_SYSTEMS=Odoo, n8n, VICIdial, Asterisk/PJSIP, Postiz/Postly, SMS provider, email provider, provisioning service

AUTH_MODEL=legacy shared bearer, HMAC, mTLS, or service credential depending on boundary; see AUTHORIZATION-MAP.md
TENANT_MODEL=server payload/header/campaign conventions must be replaced by verified canonical tenant context
IDEMPOTENCY=server-specific; durable ledger/inbox equivalence test required
RETRY_MODEL=server worker retry/poll loop; normalize in connector/Temporal policy
ERROR_MODEL=server-specific HTTP/worker errors; normalize to canonical command and connector errors
OBSERVABILITY=health `healthy` plus logs; canonical metrics/audit/correlation required

CANONICAL_MAIN_EQUIVALENT=provisioning-service connector orchestrated by Middleware
CLASSIFICATION=REPLACE_WITH_NEW_ARCHITECTURE
RATIONALE=Provisioning lifecycle/state belongs to provisioning service; Middleware retains tenant/capability authorization and orchestration only.
TEST_REQUIRED=Provisioning mock, duplicate desired state, partial failure, rollback and read-back tests
SERVER_DEPENDENCIES=Provisioning service; VICIdial/PJSIP connectors; command ledger

## F003 — middleware-pjsip-adapter

FUNCTION_ID=F003
FUNCTION_NAME=middleware-pjsip-adapter
BUSINESS_PURPOSE=PJSIP behavior is required but lacks a complete connector manifest in main; it must not remain an ad-hoc entrypoint.

SERVER_SOURCE_FILES=app/entrypoints/pjsip_adapter.py
SERVER_ENTRYPOINT=`/usr/local/bin/live-delivery-admission python -m app.entrypoints.pjsip_adapter`
SERVER_CONTAINER=`codestra-middleware-pjsip-adapter-1`
SERVER_IMAGE=`codestra/middleware@sha256:1a9e13a0c930d36076b5742e17f948dc85d9bc6ace90e58052756c8b1ad42700`
SERVER_REVISION=`b3ca9aa458fef843e3065aeff3397c656349f138`

SERVER_API_PATHS=runtime health/readiness/dependencies
SERVER_DATABASE_TABLES=see DATABASE-SCHEMA-MAP.md; worker-specific ownership requires command contracts
SERVER_REDIS_USAGE=configuration/coordination only; see REDIS-USAGE-MAP.md
SERVER_QUEUE_USAGE=legacy PostgreSQL polling/outbox, direct HTTP, or runtime-specific loop; see EVENT-TRANSPORT-MAP.md
SERVER_EXTERNAL_SYSTEMS=Odoo, n8n, VICIdial, Asterisk/PJSIP, Postiz/Postly, SMS provider, email provider, provisioning service

AUTH_MODEL=legacy shared bearer, HMAC, mTLS, or service credential depending on boundary; see AUTHORIZATION-MAP.md
TENANT_MODEL=server payload/header/campaign conventions must be replaced by verified canonical tenant context
IDEMPOTENCY=server-specific; durable ledger/inbox equivalence test required
RETRY_MODEL=server worker retry/poll loop; normalize in connector/Temporal policy
ERROR_MODEL=server-specific HTTP/worker errors; normalize to canonical command and connector errors
OBSERVABILITY=health `healthy` plus logs; canonical metrics/audit/correlation required

CANONICAL_MAIN_EQUIVALENT=new Asterisk/PJSIP connector to be added
CLASSIFICATION=KEEP_AND_PORT
RATIONALE=PJSIP behavior is required but lacks a complete connector manifest in main; it must not remain an ad-hoc entrypoint.
TEST_REQUIRED=Asterisk/PJSIP mock, mTLS, tenant, retry, read-back and forbidden-command tests
SERVER_DEPENDENCIES=Asterisk/PJSIP provider; provisioning service; command ledger

## F004 — middleware-webphone-session-issuer

FUNCTION_ID=F004
FUNCTION_NAME=middleware-webphone-session-issuer
BUSINESS_PURPOSE=Short-lived browser session issuance remains separate from telephony command authority and must not expose provider credentials.

SERVER_SOURCE_FILES=app/entrypoints/webphone_session_issuer.py
SERVER_ENTRYPOINT=`/usr/local/bin/live-delivery-admission python -m app.entrypoints.webphone_session_issuer`
SERVER_CONTAINER=`codestra-middleware-webphone-session-issuer-1`
SERVER_IMAGE=`ghcr.io/codestra-srl/codestra-middleware@sha256:48dbb4201b4cf8abee1600936a84da52a92969ab124fb44a0007059e75d57e85`
SERVER_REVISION=`80954a1ecb4eae49a57a9de245f78fd9a2f825a1`

SERVER_API_PATHS=runtime health/readiness/dependencies
SERVER_DATABASE_TABLES=see DATABASE-SCHEMA-MAP.md; worker-specific ownership requires command contracts
SERVER_REDIS_USAGE=configuration/coordination only; see REDIS-USAGE-MAP.md
SERVER_QUEUE_USAGE=legacy PostgreSQL polling/outbox, direct HTTP, or runtime-specific loop; see EVENT-TRANSPORT-MAP.md
SERVER_EXTERNAL_SYSTEMS=Odoo, n8n, VICIdial, Asterisk/PJSIP, Postiz/Postly, SMS provider, email provider, provisioning service

AUTH_MODEL=legacy shared bearer, HMAC, mTLS, or service credential depending on boundary; see AUTHORIZATION-MAP.md
TENANT_MODEL=server payload/header/campaign conventions must be replaced by verified canonical tenant context
IDEMPOTENCY=server-specific; durable ledger/inbox equivalence test required
RETRY_MODEL=server worker retry/poll loop; normalize in connector/Temporal policy
ERROR_MODEL=server-specific HTTP/worker errors; normalize to canonical command and connector errors
OBSERVABILITY=health `healthy` plus logs; canonical metrics/audit/correlation required

CANONICAL_MAIN_EQUIVALENT=isolated webphone session connector/API with Keycloak validation
CLASSIFICATION=KEEP_AND_PORT
RATIONALE=Short-lived browser session issuance remains separate from telephony command authority and must not expose provider credentials.
TEST_REQUIRED=JWT audience/azp, tenant, expiry, replay, credential non-disclosure and revocation tests
SERVER_DEPENDENCIES=Keycloak; provisioning service; telephony session backend

## F005 — middleware-integration-api

FUNCTION_ID=F005
FUNCTION_NAME=middleware-integration-api
BUSINESS_PURPOSE=This is the principal server API surface. Required endpoint semantics must be inventoried and selectively ported; direct provider writes must become commands/connectors.

SERVER_SOURCE_FILES=app/entrypoints/integration_api.py, app/main.py
SERVER_ENTRYPOINT=`/usr/local/bin/live-delivery-admission /opt/venv/bin/python -m app.entrypoints.integration_api`
SERVER_CONTAINER=`codestra-middleware-integration-api-1`
SERVER_IMAGE=`ghcr.io/codestra-srl/codestra-middleware@sha256:09d4bd0f7b2376e0a06d3efae27a6642429389fa7e3277791ec0b36584e87175`
SERVER_REVISION=`35448ef85ae56db3651a72b61db8e242b7aacd2e`

SERVER_API_PATHS=runtime health/readiness/dependencies
SERVER_DATABASE_TABLES=see DATABASE-SCHEMA-MAP.md; worker-specific ownership requires command contracts
SERVER_REDIS_USAGE=configuration/coordination only; see REDIS-USAGE-MAP.md
SERVER_QUEUE_USAGE=legacy PostgreSQL polling/outbox, direct HTTP, or runtime-specific loop; see EVENT-TRANSPORT-MAP.md
SERVER_EXTERNAL_SYSTEMS=Odoo, n8n, VICIdial, Asterisk/PJSIP, Postiz/Postly, SMS provider, email provider, provisioning service

AUTH_MODEL=legacy shared bearer, HMAC, mTLS, or service credential depending on boundary; see AUTHORIZATION-MAP.md
TENANT_MODEL=server payload/header/campaign conventions must be replaced by verified canonical tenant context
IDEMPOTENCY=server-specific; durable ledger/inbox equivalence test required
RETRY_MODEL=server worker retry/poll loop; normalize in connector/Temporal policy
ERROR_MODEL=server-specific HTTP/worker errors; normalize to canonical command and connector errors
OBSERVABILITY=health `healthy` plus logs; canonical metrics/audit/correlation required

CANONICAL_MAIN_EQUIVALENT=`app.main`, `app.service`, `app.commands`, and connector-runtime API
CLASSIFICATION=KEEP_AND_PORT
RATIONALE=This is the principal server API surface. Required endpoint semantics must be inventoried and selectively ported; direct provider writes must become commands/connectors.
TEST_REQUIRED=Per-route contract matrix plus authorization, tenant, idempotency and no-direct-write tests
SERVER_DEPENDENCIES=PostgreSQL; Redis; Keycloak; n8n; Odoo; provisioning; internal integration gateway

## F006 — middleware

FUNCTION_ID=F006
FUNCTION_NAME=middleware
BUSINESS_PURPOSE=The container duplicates the integration API and uses legacy route/write boundaries. Preserve only explicitly mapped endpoint behavior behind canonical auth, tenant, inbox/outbox and command controls.

SERVER_SOURCE_FILES=app/entrypoints/integration_api.py, app/main.py
SERVER_ENTRYPOINT=`/usr/local/bin/live-delivery-admission python -m app.entrypoints.integration_api`
SERVER_CONTAINER=`codestra-middleware-1`
SERVER_IMAGE=`codestra/middleware:health-contract-b3ca9aa`
SERVER_REVISION=`b3ca9aa458fef843e3065aeff3397c656349f138`

SERVER_API_PATHS=runtime health/readiness/dependencies
SERVER_DATABASE_TABLES=see DATABASE-SCHEMA-MAP.md; worker-specific ownership requires command contracts
SERVER_REDIS_USAGE=configuration/coordination only; see REDIS-USAGE-MAP.md
SERVER_QUEUE_USAGE=legacy PostgreSQL polling/outbox, direct HTTP, or runtime-specific loop; see EVENT-TRANSPORT-MAP.md
SERVER_EXTERNAL_SYSTEMS=Odoo, n8n, VICIdial, SMS provider, email provider, provisioning service

AUTH_MODEL=legacy shared bearer, HMAC, mTLS, or service credential depending on boundary; see AUTHORIZATION-MAP.md
TENANT_MODEL=server payload/header/campaign conventions must be replaced by verified canonical tenant context
IDEMPOTENCY=server-specific; durable ledger/inbox equivalence test required
RETRY_MODEL=server worker retry/poll loop; normalize in connector/Temporal policy
ERROR_MODEL=server-specific HTTP/worker errors; normalize to canonical command and connector errors
OBSERVABILITY=health `healthy` plus logs; canonical metrics/audit/correlation required

CANONICAL_MAIN_EQUIVALENT=`app.main` intake API plus connector-runtime management API
CLASSIFICATION=REPLACE_WITH_NEW_ARCHITECTURE
RATIONALE=The container duplicates the integration API and uses legacy route/write boundaries. Preserve only explicitly mapped endpoint behavior behind canonical auth, tenant, inbox/outbox and command controls.
TEST_REQUIRED=API contract, JWT/OIDC, tenant isolation, idempotency, capability denial and legacy-route parity tests
SERVER_DEPENDENCIES=PostgreSQL; Redis; Keycloak; provisioning service; Odoo boundary

## F007 — middleware-odoo-result-worker

FUNCTION_ID=F007
FUNCTION_NAME=middleware-odoo-result-worker
BUSINESS_PURPOSE=Delivery results remain required, but Odoo writes must pass through the command/capability boundary and record read-back.

SERVER_SOURCE_FILES=app/api/v1/integrations.py, app/workers/delivery.py
SERVER_ENTRYPOINT=`/usr/local/bin/live-delivery-admission /opt/venv/bin/python -m app.entrypoints.odoo_result_worker`
SERVER_CONTAINER=`codestra-middleware-odoo-result-worker-1`
SERVER_IMAGE=`ghcr.io/codestra-srl/codestra-middleware@sha256:ab74b9eb56c9625597476ab6669b065b471314c912cb2d4677118de230e3d4e2`
SERVER_REVISION=`d30babd35b7b82aab312f16940f5b8d2f7797f1d`

SERVER_API_PATHS=see API-ENDPOINT-MAP.md
SERVER_DATABASE_TABLES=see DATABASE-SCHEMA-MAP.md; worker-specific ownership requires command contracts
SERVER_REDIS_USAGE=configuration/coordination only; see REDIS-USAGE-MAP.md
SERVER_QUEUE_USAGE=legacy PostgreSQL polling/outbox, direct HTTP, or runtime-specific loop; see EVENT-TRANSPORT-MAP.md
SERVER_EXTERNAL_SYSTEMS=Odoo, n8n, VICIdial, Asterisk/PJSIP, Postiz/Postly, SMS provider, email provider, provisioning service

AUTH_MODEL=legacy shared bearer, HMAC, mTLS, or service credential depending on boundary; see AUTHORIZATION-MAP.md
TENANT_MODEL=server payload/header/campaign conventions must be replaced by verified canonical tenant context
IDEMPOTENCY=server-specific; durable ledger/inbox equivalence test required
RETRY_MODEL=server worker retry/poll loop; normalize in connector/Temporal policy
ERROR_MODEL=server-specific HTTP/worker errors; normalize to canonical command and connector errors
OBSERVABILITY=health `healthy` plus logs; canonical metrics/audit/correlation required

CANONICAL_MAIN_EQUIVALENT=Odoo connector plus canonical command/result events
CLASSIFICATION=KEEP_AND_PORT
RATIONALE=Delivery results remain required, but Odoo writes must pass through the command/capability boundary and record read-back.
TEST_REQUIRED=Odoo mock, tenant, duplicate, conflict, retry and read-back completion tests
SERVER_DEPENDENCIES=PostgreSQL; Odoo connector; Keycloak service identity

## F008 — middleware-notification-worker

FUNCTION_ID=F008
FUNCTION_NAME=middleware-notification-worker
BUSINESS_PURPOSE=Notification scheduling/delivery is required, but every external effect must use an explicit connector and capability.

SERVER_SOURCE_FILES=app/entrypoints/notification_worker.py, app/workers/delivery.py
SERVER_ENTRYPOINT=`/usr/local/bin/live-delivery-admission /opt/venv/bin/python -m app.entrypoints.notification_worker`
SERVER_CONTAINER=`codestra-middleware-notification-worker-1`
SERVER_IMAGE=`ghcr.io/codestra-srl/codestra-middleware@sha256:73fe86858d7a9303bbb151c77097aa43c0739e71c4781636e7db81dd4eadbf98`
SERVER_REVISION=`9118e5bc01f9ce4a52add8753c096d061cd84848`

SERVER_API_PATHS=runtime health/readiness/dependencies
SERVER_DATABASE_TABLES=see DATABASE-SCHEMA-MAP.md; worker-specific ownership requires command contracts
SERVER_REDIS_USAGE=configuration/coordination only; see REDIS-USAGE-MAP.md
SERVER_QUEUE_USAGE=legacy PostgreSQL polling/outbox, direct HTTP, or runtime-specific loop; see EVENT-TRANSPORT-MAP.md
SERVER_EXTERNAL_SYSTEMS=Odoo, n8n, VICIdial, Asterisk/PJSIP, Postiz/Postly, SMS provider, email provider, provisioning service

AUTH_MODEL=legacy shared bearer, HMAC, mTLS, or service credential depending on boundary; see AUTHORIZATION-MAP.md
TENANT_MODEL=server payload/header/campaign conventions must be replaced by verified canonical tenant context
IDEMPOTENCY=server-specific; durable ledger/inbox equivalence test required
RETRY_MODEL=server worker retry/poll loop; normalize in connector/Temporal policy
ERROR_MODEL=server-specific HTTP/worker errors; normalize to canonical command and connector errors
OBSERVABILITY=health `healthy` plus logs; canonical metrics/audit/correlation required

CANONICAL_MAIN_EQUIVALENT=canonical outbox worker and connector commands
CLASSIFICATION=KEEP_AND_PORT
RATIONALE=Notification scheduling/delivery is required, but every external effect must use an explicit connector and capability.
TEST_REQUIRED=Email/SMS mocks, capability denial, retry, receipt and opt-out tests
SERVER_DEPENDENCIES=PostgreSQL outbox; Redis; communications connectors

## F009 — middleware-scheduler

FUNCTION_ID=F009
FUNCTION_NAME=middleware-scheduler
BUSINESS_PURPOSE=Local polling semantics should be represented as durable Temporal schedules or database-backed leases, not an undocumented standalone scheduler.

SERVER_SOURCE_FILES=app/entrypoints/scheduler.py
SERVER_ENTRYPOINT=`/usr/local/bin/live-delivery-admission /opt/venv/bin/python -m app.entrypoints.scheduler`
SERVER_CONTAINER=`codestra-middleware-scheduler-1`
SERVER_IMAGE=`ghcr.io/codestra-srl/codestra-middleware@sha256:73fe86858d7a9303bbb151c77097aa43c0739e71c4781636e7db81dd4eadbf98`
SERVER_REVISION=`9118e5bc01f9ce4a52add8753c096d061cd84848`

SERVER_API_PATHS=runtime health/readiness/dependencies
SERVER_DATABASE_TABLES=see DATABASE-SCHEMA-MAP.md; worker-specific ownership requires command contracts
SERVER_REDIS_USAGE=configuration/coordination only; see REDIS-USAGE-MAP.md
SERVER_QUEUE_USAGE=legacy PostgreSQL polling/outbox, direct HTTP, or runtime-specific loop; see EVENT-TRANSPORT-MAP.md
SERVER_EXTERNAL_SYSTEMS=Odoo, n8n, VICIdial, Asterisk/PJSIP, Postiz/Postly, SMS provider, email provider, provisioning service

AUTH_MODEL=legacy shared bearer, HMAC, mTLS, or service credential depending on boundary; see AUTHORIZATION-MAP.md
TENANT_MODEL=server payload/header/campaign conventions must be replaced by verified canonical tenant context
IDEMPOTENCY=server-specific; durable ledger/inbox equivalence test required
RETRY_MODEL=server worker retry/poll loop; normalize in connector/Temporal policy
ERROR_MODEL=server-specific HTTP/worker errors; normalize to canonical command and connector errors
OBSERVABILITY=health `healthy` plus logs; canonical metrics/audit/correlation required

CANONICAL_MAIN_EQUIVALENT=Temporal schedules/workflows and `core/workers-scheduler`
CLASSIFICATION=REPLACE_WITH_NEW_ARCHITECTURE
RATIONALE=Local polling semantics should be represented as durable Temporal schedules or database-backed leases, not an undocumented standalone scheduler.
TEST_REQUIRED=Schedule idempotency, missed tick, overlapping lease, restart and delayed callback tests
SERVER_DEPENDENCIES=Temporal; PostgreSQL; command ledger

## F010 — middleware-staging

FUNCTION_ID=F010
FUNCTION_NAME=middleware-staging
BUSINESS_PURPOSE=Staging is an environment of the canonical API, not a separate source history or implementation.

SERVER_SOURCE_FILES=app/entrypoints/integration_api.py, app/main.py
SERVER_ENTRYPOINT=`/opt/venv/bin/python -m app.entrypoints.integration_api`
SERVER_CONTAINER=`codestra-middleware-staging-middleware-staging-1`
SERVER_IMAGE=`ghcr.io/codestra-srl/codestra-middleware@sha256:73fe86858d7a9303bbb151c77097aa43c0739e71c4781636e7db81dd4eadbf98`
SERVER_REVISION=`9118e5bc01f9ce4a52add8753c096d061cd84848`

SERVER_API_PATHS=runtime health/readiness/dependencies
SERVER_DATABASE_TABLES=see DATABASE-SCHEMA-MAP.md; worker-specific ownership requires command contracts
SERVER_REDIS_USAGE=configuration/coordination only; see REDIS-USAGE-MAP.md
SERVER_QUEUE_USAGE=legacy PostgreSQL polling/outbox, direct HTTP, or runtime-specific loop; see EVENT-TRANSPORT-MAP.md
SERVER_EXTERNAL_SYSTEMS=Odoo, n8n, VICIdial, Postiz/Postly, email provider

AUTH_MODEL=legacy shared bearer, HMAC, mTLS, or service credential depending on boundary; see AUTHORIZATION-MAP.md
TENANT_MODEL=server payload/header/campaign conventions must be replaced by verified canonical tenant context
IDEMPOTENCY=server-specific; durable ledger/inbox equivalence test required
RETRY_MODEL=server worker retry/poll loop; normalize in connector/Temporal policy
ERROR_MODEL=server-specific HTTP/worker errors; normalize to canonical command and connector errors
OBSERVABILITY=health `healthy` plus logs; canonical metrics/audit/correlation required

CANONICAL_MAIN_EQUIVALENT=same canonical API build with staging runtime profile
CLASSIFICATION=DUPLICATE
RATIONALE=Staging is an environment of the canonical API, not a separate source history or implementation.
TEST_REQUIRED=Same-image provenance, staging fail-closed profile and external-effects-disabled acceptance
SERVER_DEPENDENCIES=Staging PostgreSQL/Redis/Keycloak/n8n

## F011 — notification-worker-staging

FUNCTION_ID=F011
FUNCTION_NAME=notification-worker-staging
BUSINESS_PURPOSE=Environment-specific deployment only; no separate source implementation should survive.

SERVER_SOURCE_FILES=app/entrypoints/notification_worker.py, app/workers/delivery.py
SERVER_ENTRYPOINT=`/opt/venv/bin/python -m app.entrypoints.notification_worker`
SERVER_CONTAINER=`codestra-middleware-staging-notification-worker-staging-1`
SERVER_IMAGE=`ghcr.io/codestra-srl/codestra-middleware@sha256:73fe86858d7a9303bbb151c77097aa43c0739e71c4781636e7db81dd4eadbf98`
SERVER_REVISION=`9118e5bc01f9ce4a52add8753c096d061cd84848`

SERVER_API_PATHS=runtime health/readiness/dependencies
SERVER_DATABASE_TABLES=see DATABASE-SCHEMA-MAP.md; worker-specific ownership requires command contracts
SERVER_REDIS_USAGE=configuration/coordination only; see REDIS-USAGE-MAP.md
SERVER_QUEUE_USAGE=legacy PostgreSQL polling/outbox, direct HTTP, or runtime-specific loop; see EVENT-TRANSPORT-MAP.md
SERVER_EXTERNAL_SYSTEMS=Odoo, n8n, VICIdial, email provider

AUTH_MODEL=legacy shared bearer, HMAC, mTLS, or service credential depending on boundary; see AUTHORIZATION-MAP.md
TENANT_MODEL=server payload/header/campaign conventions must be replaced by verified canonical tenant context
IDEMPOTENCY=server-specific; durable ledger/inbox equivalence test required
RETRY_MODEL=server worker retry/poll loop; normalize in connector/Temporal policy
ERROR_MODEL=server-specific HTTP/worker errors; normalize to canonical command and connector errors
OBSERVABILITY=health `running` plus logs; canonical metrics/audit/correlation required

CANONICAL_MAIN_EQUIVALENT=same canonical notification/outbox worker with staging profile
CLASSIFICATION=DUPLICATE
RATIONALE=Environment-specific deployment only; no separate source implementation should survive.
TEST_REQUIRED=Same-image provenance and communications mocks with all live effects disabled
SERVER_DEPENDENCIES=Staging PostgreSQL; Redis; mock connectors

## F012 — scheduler-staging

FUNCTION_ID=F012
FUNCTION_NAME=scheduler-staging
BUSINESS_PURPOSE=Environment-specific instance of the scheduler replacement.

SERVER_SOURCE_FILES=app/entrypoints/scheduler.py
SERVER_ENTRYPOINT=`/opt/venv/bin/python -m app.entrypoints.scheduler`
SERVER_CONTAINER=`codestra-middleware-staging-scheduler-staging-1`
SERVER_IMAGE=`ghcr.io/codestra-srl/codestra-middleware@sha256:73fe86858d7a9303bbb151c77097aa43c0739e71c4781636e7db81dd4eadbf98`
SERVER_REVISION=`9118e5bc01f9ce4a52add8753c096d061cd84848`

SERVER_API_PATHS=runtime health/readiness/dependencies
SERVER_DATABASE_TABLES=see DATABASE-SCHEMA-MAP.md; worker-specific ownership requires command contracts
SERVER_REDIS_USAGE=configuration/coordination only; see REDIS-USAGE-MAP.md
SERVER_QUEUE_USAGE=legacy PostgreSQL polling/outbox, direct HTTP, or runtime-specific loop; see EVENT-TRANSPORT-MAP.md
SERVER_EXTERNAL_SYSTEMS=Odoo, n8n, VICIdial, email provider

AUTH_MODEL=legacy shared bearer, HMAC, mTLS, or service credential depending on boundary; see AUTHORIZATION-MAP.md
TENANT_MODEL=server payload/header/campaign conventions must be replaced by verified canonical tenant context
IDEMPOTENCY=server-specific; durable ledger/inbox equivalence test required
RETRY_MODEL=server worker retry/poll loop; normalize in connector/Temporal policy
ERROR_MODEL=server-specific HTTP/worker errors; normalize to canonical command and connector errors
OBSERVABILITY=health `running` plus logs; canonical metrics/audit/correlation required

CANONICAL_MAIN_EQUIVALENT=same Temporal scheduler/workflow build with staging queue
CLASSIFICATION=DUPLICATE
RATIONALE=Environment-specific instance of the scheduler replacement.
TEST_REQUIRED=Same-image provenance, isolated task queue and restart tests
SERVER_DEPENDENCIES=Staging Temporal; PostgreSQL

## F013 — middleware-evidence-runner

FUNCTION_ID=F013
FUNCTION_NAME=middleware-evidence-runner
BUSINESS_PURPOSE=Runtime evidence must come from reproducible acceptance/release tooling, not a permanently running mixed-revision utility container.

SERVER_SOURCE_FILES=app/entrypoints/evidence_runner.py
SERVER_ENTRYPOINT=`/usr/local/bin/live-delivery-admission python -m app.entrypoints.evidence_runner`
SERVER_CONTAINER=`codestra-middleware-evidence-runner-1`
SERVER_IMAGE=`codestra/middleware@sha256:1a9e13a0c930d36076b5742e17f948dc85d9bc6ace90e58052756c8b1ad42700`
SERVER_REVISION=`b3ca9aa458fef843e3065aeff3397c656349f138`

SERVER_API_PATHS=runtime health/readiness/dependencies
SERVER_DATABASE_TABLES=see DATABASE-SCHEMA-MAP.md; worker-specific ownership requires command contracts
SERVER_REDIS_USAGE=configuration/coordination only; see REDIS-USAGE-MAP.md
SERVER_QUEUE_USAGE=legacy PostgreSQL polling/outbox, direct HTTP, or runtime-specific loop; see EVENT-TRANSPORT-MAP.md
SERVER_EXTERNAL_SYSTEMS=Odoo, n8n, VICIdial, Asterisk/PJSIP, Postiz/Postly, SMS provider, email provider, provisioning service

AUTH_MODEL=legacy shared bearer, HMAC, mTLS, or service credential depending on boundary; see AUTHORIZATION-MAP.md
TENANT_MODEL=server payload/header/campaign conventions must be replaced by verified canonical tenant context
IDEMPOTENCY=server-specific; durable ledger/inbox equivalence test required
RETRY_MODEL=server worker retry/poll loop; normalize in connector/Temporal policy
ERROR_MODEL=server-specific HTTP/worker errors; normalize to canonical command and connector errors
OBSERVABILITY=health `healthy` plus logs; canonical metrics/audit/correlation required

CANONICAL_MAIN_EQUIVALENT=synthetic staging acceptance and release-manifest validators
CLASSIFICATION=REPLACE_WITH_NEW_ARCHITECTURE
RATIONALE=Runtime evidence must come from reproducible acceptance/release tooling, not a permanently running mixed-revision utility container.
TEST_REQUIRED=No-effect acceptance, source/digest attestation and evidence immutability tests
SERVER_DEPENDENCIES=Release manifest; staging API; observability

## F014 — middleware-policy-engine

FUNCTION_ID=F014
FUNCTION_NAME=middleware-policy-engine
BUSINESS_PURPOSE=Server policy decisions may contain required behavior, but the new signed capability and activation design remains authoritative.

SERVER_SOURCE_FILES=app/entrypoints/policy_engine.py
SERVER_ENTRYPOINT=`/usr/local/bin/live-delivery-admission python -m app.entrypoints.policy_engine`
SERVER_CONTAINER=`codestra-middleware-policy-engine-1`
SERVER_IMAGE=`codestra/middleware@sha256:1a9e13a0c930d36076b5742e17f948dc85d9bc6ace90e58052756c8b1ad42700`
SERVER_REVISION=`b3ca9aa458fef843e3065aeff3397c656349f138`

SERVER_API_PATHS=runtime health/readiness/dependencies
SERVER_DATABASE_TABLES=see DATABASE-SCHEMA-MAP.md; worker-specific ownership requires command contracts
SERVER_REDIS_USAGE=configuration/coordination only; see REDIS-USAGE-MAP.md
SERVER_QUEUE_USAGE=legacy PostgreSQL polling/outbox, direct HTTP, or runtime-specific loop; see EVENT-TRANSPORT-MAP.md
SERVER_EXTERNAL_SYSTEMS=Odoo, n8n, VICIdial, Asterisk/PJSIP, Postiz/Postly, SMS provider, email provider, provisioning service

AUTH_MODEL=legacy shared bearer, HMAC, mTLS, or service credential depending on boundary; see AUTHORIZATION-MAP.md
TENANT_MODEL=server payload/header/campaign conventions must be replaced by verified canonical tenant context
IDEMPOTENCY=server-specific; durable ledger/inbox equivalence test required
RETRY_MODEL=server worker retry/poll loop; normalize in connector/Temporal policy
ERROR_MODEL=server-specific HTTP/worker errors; normalize to canonical command and connector errors
OBSERVABILITY=health `healthy` plus logs; canonical metrics/audit/correlation required

CANONICAL_MAIN_EQUIVALENT=capability registry, operation policy and runtime-safety controls
CLASSIFICATION=KEEP_AND_PORT
RATIONALE=Server policy decisions may contain required behavior, but the new signed capability and activation design remains authoritative.
TEST_REQUIRED=Default deny, expiry, tenant mismatch, forbidden prefix and signed activation tests
SERVER_DEPENDENCIES=Capability registry; Keycloak claims; command policy

## F015 — middleware-sync-worker

FUNCTION_ID=F015
FUNCTION_NAME=middleware-sync-worker
BUSINESS_PURPOSE=The generic sync scope is not explicit enough to port safely. Each synchronized resource must be assigned to a connector/event contract first.

SERVER_SOURCE_FILES=app/entrypoints/sync_worker.py
SERVER_ENTRYPOINT=`/usr/local/bin/live-delivery-admission python -m app.entrypoints.sync_worker`
SERVER_CONTAINER=`codestra-middleware-sync-worker-1`
SERVER_IMAGE=`codestra/middleware@sha256:1a9e13a0c930d36076b5742e17f948dc85d9bc6ace90e58052756c8b1ad42700`
SERVER_REVISION=`b3ca9aa458fef843e3065aeff3397c656349f138`

SERVER_API_PATHS=runtime health/readiness/dependencies
SERVER_DATABASE_TABLES=see DATABASE-SCHEMA-MAP.md; worker-specific ownership requires command contracts
SERVER_REDIS_USAGE=configuration/coordination only; see REDIS-USAGE-MAP.md
SERVER_QUEUE_USAGE=legacy PostgreSQL polling/outbox, direct HTTP, or runtime-specific loop; see EVENT-TRANSPORT-MAP.md
SERVER_EXTERNAL_SYSTEMS=Odoo, n8n, VICIdial, Asterisk/PJSIP, Postiz/Postly, SMS provider, email provider, provisioning service

AUTH_MODEL=legacy shared bearer, HMAC, mTLS, or service credential depending on boundary; see AUTHORIZATION-MAP.md
TENANT_MODEL=server payload/header/campaign conventions must be replaced by verified canonical tenant context
IDEMPOTENCY=server-specific; durable ledger/inbox equivalence test required
RETRY_MODEL=server worker retry/poll loop; normalize in connector/Temporal policy
ERROR_MODEL=server-specific HTTP/worker errors; normalize to canonical command and connector errors
OBSERVABILITY=health `healthy` plus logs; canonical metrics/audit/correlation required

CANONICAL_MAIN_EQUIVALENT=connector event ingestion plus Temporal workflows
CLASSIFICATION=KEEP_AND_PORT
RATIONALE=The generic sync scope is not explicit enough to port safely. Each synchronized resource must be assigned to a connector/event contract first.
TEST_REQUIRED=Resource-specific ownership, tenant, cursor, duplicate and convergence tests
SERVER_DEPENDENCIES=PostgreSQL; provider connectors; event ledger

## F016 — middleware-n8n-runtime-worker

FUNCTION_ID=F016
FUNCTION_NAME=middleware-n8n-runtime-worker
BUSINESS_PURPOSE=Retain orchestration handoff while making Middleware the authorization and durable-command boundary.

SERVER_SOURCE_FILES=server-baseline/runtime-images.json (runtime-only evidence)
SERVER_ENTRYPOINT=`/usr/local/bin/live-delivery-admission python -m app.entrypoints.n8n_runtime_worker`
SERVER_CONTAINER=`codestra-middleware-n8n-runtime-worker-1`
SERVER_IMAGE=`codestra/middleware@sha256:1a9e13a0c930d36076b5742e17f948dc85d9bc6ace90e58052756c8b1ad42700`
SERVER_REVISION=`b3ca9aa458fef843e3065aeff3397c656349f138`

SERVER_API_PATHS=see API-ENDPOINT-MAP.md
SERVER_DATABASE_TABLES=see DATABASE-SCHEMA-MAP.md; worker-specific ownership requires command contracts
SERVER_REDIS_USAGE=configuration/coordination only; see REDIS-USAGE-MAP.md
SERVER_QUEUE_USAGE=legacy PostgreSQL polling/outbox, direct HTTP, or runtime-specific loop; see EVENT-TRANSPORT-MAP.md
SERVER_EXTERNAL_SYSTEMS=Odoo, n8n, VICIdial, Asterisk/PJSIP, Postiz/Postly, SMS provider, email provider, provisioning service

AUTH_MODEL=legacy shared bearer, HMAC, mTLS, or service credential depending on boundary; see AUTHORIZATION-MAP.md
TENANT_MODEL=server payload/header/campaign conventions must be replaced by verified canonical tenant context
IDEMPOTENCY=server-specific; durable ledger/inbox equivalence test required
RETRY_MODEL=server worker retry/poll loop; normalize in connector/Temporal policy
ERROR_MODEL=server-specific HTTP/worker errors; normalize to canonical command and connector errors
OBSERVABILITY=health `healthy` plus logs; canonical metrics/audit/correlation required

CANONICAL_MAIN_EQUIVALENT=generated n8n workflow packs plus command/event contracts
CLASSIFICATION=KEEP_AND_PORT
RATIONALE=Retain orchestration handoff while making Middleware the authorization and durable-command boundary.
TEST_REQUIRED=Signed handoff, scope, idempotency, result correlation and forbidden-direct-write tests
SERVER_DEPENDENCIES=PostgreSQL; n8n; Keycloak service identity; command ledger

## F017 — middleware-social-n8n-delivery-worker

FUNCTION_ID=F017
FUNCTION_NAME=middleware-social-n8n-delivery-worker
BUSINESS_PURPOSE=Retain delivery orchestration but move provider calls behind the social connector; do not duplicate Postiz domain logic.

SERVER_SOURCE_FILES=server-baseline/runtime-images.json (runtime-only evidence)
SERVER_ENTRYPOINT=`/usr/local/bin/live-delivery-admission python -m app.entrypoints.social_n8n_delivery_worker`
SERVER_CONTAINER=`codestra-middleware-social-n8n-delivery-worker-1`
SERVER_IMAGE=`codestra/middleware@sha256:1a9e13a0c930d36076b5742e17f948dc85d9bc6ace90e58052756c8b1ad42700`
SERVER_REVISION=`b3ca9aa458fef843e3065aeff3397c656349f138`

SERVER_API_PATHS=see API-ENDPOINT-MAP.md
SERVER_DATABASE_TABLES=see DATABASE-SCHEMA-MAP.md; worker-specific ownership requires command contracts
SERVER_REDIS_USAGE=configuration/coordination only; see REDIS-USAGE-MAP.md
SERVER_QUEUE_USAGE=legacy PostgreSQL polling/outbox, direct HTTP, or runtime-specific loop; see EVENT-TRANSPORT-MAP.md
SERVER_EXTERNAL_SYSTEMS=Odoo, n8n, VICIdial, Asterisk/PJSIP, Postiz/Postly, SMS provider, email provider, provisioning service

AUTH_MODEL=legacy shared bearer, HMAC, mTLS, or service credential depending on boundary; see AUTHORIZATION-MAP.md
TENANT_MODEL=server payload/header/campaign conventions must be replaced by verified canonical tenant context
IDEMPOTENCY=server-specific; durable ledger/inbox equivalence test required
RETRY_MODEL=server worker retry/poll loop; normalize in connector/Temporal policy
ERROR_MODEL=server-specific HTTP/worker errors; normalize to canonical command and connector errors
OBSERVABILITY=health `healthy` plus logs; canonical metrics/audit/correlation required

CANONICAL_MAIN_EQUIVALENT=Postly connector manifest and n8n workflow pack
CLASSIFICATION=KEEP_AND_PORT
RATIONALE=Retain delivery orchestration but move provider calls behind the social connector; do not duplicate Postiz domain logic.
TEST_REQUIRED=Social mock, duplicate, provider 429/500, callback and reconciliation tests
SERVER_DEPENDENCIES=PostgreSQL; n8n; Postiz/Postly connector

## F018 — middleware-reconciliation-worker

FUNCTION_ID=F018
FUNCTION_NAME=middleware-reconciliation-worker
BUSINESS_PURPOSE=Reconciliation is a core requirement and must compare durable intent with provider read-back before completion.

SERVER_SOURCE_FILES=app/entrypoints/reconciliation_worker.py
SERVER_ENTRYPOINT=`/usr/local/bin/live-delivery-admission python -m app.entrypoints.reconciliation_worker`
SERVER_CONTAINER=`codestra-middleware-reconciliation-worker-1`
SERVER_IMAGE=`codestra/middleware@sha256:1a9e13a0c930d36076b5742e17f948dc85d9bc6ace90e58052756c8b1ad42700`
SERVER_REVISION=`b3ca9aa458fef843e3065aeff3397c656349f138`

SERVER_API_PATHS=runtime health/readiness/dependencies
SERVER_DATABASE_TABLES=see DATABASE-SCHEMA-MAP.md; worker-specific ownership requires command contracts
SERVER_REDIS_USAGE=configuration/coordination only; see REDIS-USAGE-MAP.md
SERVER_QUEUE_USAGE=legacy PostgreSQL polling/outbox, direct HTTP, or runtime-specific loop; see EVENT-TRANSPORT-MAP.md
SERVER_EXTERNAL_SYSTEMS=Odoo, n8n, VICIdial, Asterisk/PJSIP, Postiz/Postly, SMS provider, email provider, provisioning service

AUTH_MODEL=legacy shared bearer, HMAC, mTLS, or service credential depending on boundary; see AUTHORIZATION-MAP.md
TENANT_MODEL=server payload/header/campaign conventions must be replaced by verified canonical tenant context
IDEMPOTENCY=server-specific; durable ledger/inbox equivalence test required
RETRY_MODEL=server worker retry/poll loop; normalize in connector/Temporal policy
ERROR_MODEL=server-specific HTTP/worker errors; normalize to canonical command and connector errors
OBSERVABILITY=health `healthy` plus logs; canonical metrics/audit/correlation required

CANONICAL_MAIN_EQUIVALENT=Temporal reconciliation workflows and command read-back
CLASSIFICATION=KEEP_AND_PORT
RATIONALE=Reconciliation is a core requirement and must compare durable intent with provider read-back before completion.
TEST_REQUIRED=Unknown outcome, mismatch, retry, rollback, dead-letter approval and restart tests
SERVER_DEPENDENCIES=Temporal; PostgreSQL command ledger; connector read-back

## F019 — middleware-extension-allocator

FUNCTION_ID=F019
FUNCTION_NAME=middleware-extension-allocator
BUSINESS_PURPOSE=Resource allocation belongs to provisioning service; Middleware should authorize/orchestrate the command without owning allocation state.

SERVER_SOURCE_FILES=app/entrypoints/extension_allocator.py
SERVER_ENTRYPOINT=`/usr/local/bin/live-delivery-admission python -m app.entrypoints.extension_allocator`
SERVER_CONTAINER=`codestra-middleware-extension-allocator-1`
SERVER_IMAGE=`codestra/middleware@sha256:1a9e13a0c930d36076b5742e17f948dc85d9bc6ace90e58052756c8b1ad42700`
SERVER_REVISION=`b3ca9aa458fef843e3065aeff3397c656349f138`

SERVER_API_PATHS=runtime health/readiness/dependencies
SERVER_DATABASE_TABLES=see DATABASE-SCHEMA-MAP.md; worker-specific ownership requires command contracts
SERVER_REDIS_USAGE=configuration/coordination only; see REDIS-USAGE-MAP.md
SERVER_QUEUE_USAGE=legacy PostgreSQL polling/outbox, direct HTTP, or runtime-specific loop; see EVENT-TRANSPORT-MAP.md
SERVER_EXTERNAL_SYSTEMS=Odoo, n8n, VICIdial, Asterisk/PJSIP, Postiz/Postly, SMS provider, email provider, provisioning service

AUTH_MODEL=legacy shared bearer, HMAC, mTLS, or service credential depending on boundary; see AUTHORIZATION-MAP.md
TENANT_MODEL=server payload/header/campaign conventions must be replaced by verified canonical tenant context
IDEMPOTENCY=server-specific; durable ledger/inbox equivalence test required
RETRY_MODEL=server worker retry/poll loop; normalize in connector/Temporal policy
ERROR_MODEL=server-specific HTTP/worker errors; normalize to canonical command and connector errors
OBSERVABILITY=health `healthy` plus logs; canonical metrics/audit/correlation required

CANONICAL_MAIN_EQUIVALENT=provisioning-service connector and tenant-onboarding command boundary
CLASSIFICATION=REPLACE_WITH_NEW_ARCHITECTURE
RATIONALE=Resource allocation belongs to provisioning service; Middleware should authorize/orchestrate the command without owning allocation state.
TEST_REQUIRED=Idempotent provisioning mock, tenant, desired-state, read-back and duplicate allocation tests
SERVER_DEPENDENCIES=Provisioning service; command ledger; telephony connector

## F020 — middleware-event-gateway

FUNCTION_ID=F020
FUNCTION_NAME=middleware-event-gateway
BUSINESS_PURPOSE=Provider ingress behavior remains required, but verification and acknowledgement must terminate in the canonical durable inbox/outbox.

SERVER_SOURCE_FILES=app/entrypoints/event_gateway.py
SERVER_ENTRYPOINT=`/usr/local/bin/live-delivery-admission python -m app.entrypoints.event_gateway`
SERVER_CONTAINER=`codestra-middleware-event-gateway-1`
SERVER_IMAGE=`codestra/middleware:webhook-cert-pg-20260816`
SERVER_REVISION=`4a3ac0b57a61baf63310c55048a7897556faa9a972083b86761e91391ae2317b`

SERVER_API_PATHS=runtime health/readiness/dependencies
SERVER_DATABASE_TABLES=see DATABASE-SCHEMA-MAP.md; worker-specific ownership requires command contracts
SERVER_REDIS_USAGE=configuration/coordination only; see REDIS-USAGE-MAP.md
SERVER_QUEUE_USAGE=legacy PostgreSQL polling/outbox, direct HTTP, or runtime-specific loop; see EVENT-TRANSPORT-MAP.md
SERVER_EXTERNAL_SYSTEMS=Odoo, n8n, VICIdial, Asterisk/PJSIP, Postiz/Postly, SMS provider, email provider, provisioning service

AUTH_MODEL=legacy shared bearer, HMAC, mTLS, or service credential depending on boundary; see AUTHORIZATION-MAP.md
TENANT_MODEL=server payload/header/campaign conventions must be replaced by verified canonical tenant context
IDEMPOTENCY=server-specific; durable ledger/inbox equivalence test required
RETRY_MODEL=server worker retry/poll loop; normalize in connector/Temporal policy
ERROR_MODEL=server-specific HTTP/worker errors; normalize to canonical command and connector errors
OBSERVABILITY=health `healthy` plus logs; canonical metrics/audit/correlation required

CANONICAL_MAIN_EQUIVALENT=`app.main` signed intake and connector-runtime `webhook_ingress`
CLASSIFICATION=KEEP_AND_PORT
RATIONALE=Provider ingress behavior remains required, but verification and acknowledgement must terminate in the canonical durable inbox/outbox.
TEST_REQUIRED=Body limit, HMAC, timestamp, duplicate, conflict, tenant routing, restart and redelivery tests
SERVER_DEPENDENCIES=PostgreSQL; Redis; edge ingress; provider signature secrets

## F021 — middleware-external-webhook-worker

FUNCTION_ID=F021
FUNCTION_NAME=middleware-external-webhook-worker
BUSINESS_PURPOSE=Asynchronous webhook processing is valid only after durable acknowledgement; n8n delivery cannot be the source of write authority.

SERVER_SOURCE_FILES=app/entrypoints/event_gateway.py, app/workers/outbox.py
SERVER_ENTRYPOINT=`/usr/local/bin/live-delivery-admission python -m app.entrypoints.external_webhook_worker`
SERVER_CONTAINER=`codestra-middleware-external-webhook-worker-1`
SERVER_IMAGE=`codestra/middleware:webhook-cert-pg-20260816`
SERVER_REVISION=`4a3ac0b57a61baf63310c55048a7897556faa9a972083b86761e91391ae2317b`

SERVER_API_PATHS=runtime health/readiness/dependencies
SERVER_DATABASE_TABLES=see DATABASE-SCHEMA-MAP.md; worker-specific ownership requires command contracts
SERVER_REDIS_USAGE=configuration/coordination only; see REDIS-USAGE-MAP.md
SERVER_QUEUE_USAGE=legacy PostgreSQL polling/outbox, direct HTTP, or runtime-specific loop; see EVENT-TRANSPORT-MAP.md
SERVER_EXTERNAL_SYSTEMS=Odoo, n8n, VICIdial, SMS provider, email provider, provisioning service

AUTH_MODEL=legacy shared bearer, HMAC, mTLS, or service credential depending on boundary; see AUTHORIZATION-MAP.md
TENANT_MODEL=server payload/header/campaign conventions must be replaced by verified canonical tenant context
IDEMPOTENCY=server-specific; durable ledger/inbox equivalence test required
RETRY_MODEL=server worker retry/poll loop; normalize in connector/Temporal policy
ERROR_MODEL=server-specific HTTP/worker errors; normalize to canonical command and connector errors
OBSERVABILITY=health `running` plus logs; canonical metrics/audit/correlation required

CANONICAL_MAIN_EQUIVALENT=connector-runtime inbox processing plus Temporal/outbox workers
CLASSIFICATION=KEEP_AND_PORT
RATIONALE=Asynchronous webhook processing is valid only after durable acknowledgement; n8n delivery cannot be the source of write authority.
TEST_REQUIRED=Inbox lease, retry, dead-letter, timeout, n8n mock and restart tests
SERVER_DEPENDENCIES=PostgreSQL inbox/outbox; n8n control network; connector contracts

## F022 — middleware-breero-odoo-worker

FUNCTION_ID=F022
FUNCTION_NAME=middleware-breero-odoo-worker
BUSINESS_PURPOSE=Preserve mapping behavior as two explicit connector boundaries with canonical lead provenance and review policy.

SERVER_SOURCE_FILES=app/core/lead_reconciliation.py, app/workers/delivery.py
SERVER_ENTRYPOINT=`/usr/local/bin/live-delivery-admission python -m app.entrypoints.breero_odoo_worker`
SERVER_CONTAINER=`codestra-middleware-breero-odoo-worker-1`
SERVER_IMAGE=`codestra/middleware:breero-51416422`
SERVER_REVISION=`51416422eaaa959c8c7223ad1434287597eb8007`

SERVER_API_PATHS=see API-ENDPOINT-MAP.md
SERVER_DATABASE_TABLES=see DATABASE-SCHEMA-MAP.md; worker-specific ownership requires command contracts
SERVER_REDIS_USAGE=configuration/coordination only; see REDIS-USAGE-MAP.md
SERVER_QUEUE_USAGE=legacy PostgreSQL polling/outbox, direct HTTP, or runtime-specific loop; see EVENT-TRANSPORT-MAP.md
SERVER_EXTERNAL_SYSTEMS=Odoo, n8n, VICIdial, SMS provider, email provider, provisioning service

AUTH_MODEL=legacy shared bearer, HMAC, mTLS, or service credential depending on boundary; see AUTHORIZATION-MAP.md
TENANT_MODEL=server payload/header/campaign conventions must be replaced by verified canonical tenant context
IDEMPOTENCY=server-specific; durable ledger/inbox equivalence test required
RETRY_MODEL=server worker retry/poll loop; normalize in connector/Temporal policy
ERROR_MODEL=server-specific HTTP/worker errors; normalize to canonical command and connector errors
OBSERVABILITY=health `running` plus logs; canonical metrics/audit/correlation required

CANONICAL_MAIN_EQUIVALENT=Breero connector feeding lead normalization and Odoo connector
CLASSIFICATION=KEEP_AND_PORT
RATIONALE=Preserve mapping behavior as two explicit connector boundaries with canonical lead provenance and review policy.
TEST_REQUIRED=Breero/Odoo mocks, mapping golden files, consent, suppression, duplicate and tenant tests
SERVER_DEPENDENCIES=Breero connector; lead normalization; Odoo connector; PostgreSQL

## F023 — middleware-postly-polling-worker

FUNCTION_ID=F023
FUNCTION_NAME=middleware-postly-polling-worker
BUSINESS_PURPOSE=Polling may be retained only as connector-owned event acquisition with durable cursors, rate limits and normalized events.

SERVER_SOURCE_FILES=app/integrations/postiz/client.py, app/integrations/postiz/routes.py
SERVER_ENTRYPOINT=`/usr/local/bin/live-delivery-admission python -m app.entrypoints.postly_polling_worker`
SERVER_CONTAINER=`codestra-middleware-postly-polling-worker-1`
SERVER_IMAGE=`codestra/middleware@sha256:d3ac2b34d216064bc579feedca9cc2d4079ebe44943a6417ab31437c79df8dd8`
SERVER_REVISION=`b3ca9aa458fef843e3065aeff3397c656349f138`

SERVER_API_PATHS=see API-ENDPOINT-MAP.md
SERVER_DATABASE_TABLES=see DATABASE-SCHEMA-MAP.md; worker-specific ownership requires command contracts
SERVER_REDIS_USAGE=configuration/coordination only; see REDIS-USAGE-MAP.md
SERVER_QUEUE_USAGE=legacy PostgreSQL polling/outbox, direct HTTP, or runtime-specific loop; see EVENT-TRANSPORT-MAP.md
SERVER_EXTERNAL_SYSTEMS=Odoo, n8n, VICIdial, Asterisk/PJSIP, Postiz/Postly, SMS provider, email provider, provisioning service

AUTH_MODEL=legacy shared bearer, HMAC, mTLS, or service credential depending on boundary; see AUTHORIZATION-MAP.md
TENANT_MODEL=server payload/header/campaign conventions must be replaced by verified canonical tenant context
IDEMPOTENCY=server-specific; durable ledger/inbox equivalence test required
RETRY_MODEL=server worker retry/poll loop; normalize in connector/Temporal policy
ERROR_MODEL=server-specific HTTP/worker errors; normalize to canonical command and connector errors
OBSERVABILITY=health `healthy` plus logs; canonical metrics/audit/correlation required

CANONICAL_MAIN_EQUIVALENT=Postly social connector event ingestion
CLASSIFICATION=KEEP_AND_PORT
RATIONALE=Polling may be retained only as connector-owned event acquisition with durable cursors, rate limits and normalized events.
TEST_REQUIRED=Cursor restart, rate limit, duplicate event, provider 429/500 and normalization tests
SERVER_DEPENDENCIES=Postly connector; PostgreSQL cursor/inbox; edge/provider API

## F024 — middleware-scraper-odoo-delivery-worker

FUNCTION_ID=F024
FUNCTION_NAME=middleware-scraper-odoo-delivery-worker
BUSINESS_PURPOSE=Scraper discoveries must enter review_pending and cannot write directly to Odoo.

SERVER_SOURCE_FILES=app/core/lead_reconciliation.py, app/workers/delivery.py
SERVER_ENTRYPOINT=`/usr/local/bin/live-delivery-admission python -m app.entrypoints.scraper_odoo_delivery_worker`
SERVER_CONTAINER=`codestra-middleware-scraper-odoo-delivery-worker-1`
SERVER_IMAGE=`codestra/middleware@sha256:55dfe9ddfa8bfa94a9202284cb5276311e009066784bbde5dc05d5e1c3776492`
SERVER_REVISION=`bab6f4332fec77611f6a364fd3c9c7f9cc022051`

SERVER_API_PATHS=see API-ENDPOINT-MAP.md
SERVER_DATABASE_TABLES=see DATABASE-SCHEMA-MAP.md; worker-specific ownership requires command contracts
SERVER_REDIS_USAGE=configuration/coordination only; see REDIS-USAGE-MAP.md
SERVER_QUEUE_USAGE=legacy PostgreSQL polling/outbox, direct HTTP, or runtime-specific loop; see EVENT-TRANSPORT-MAP.md
SERVER_EXTERNAL_SYSTEMS=Odoo, n8n, VICIdial, Postiz/Postly, SMS provider, email provider

AUTH_MODEL=legacy shared bearer, HMAC, mTLS, or service credential depending on boundary; see AUTHORIZATION-MAP.md
TENANT_MODEL=server payload/header/campaign conventions must be replaced by verified canonical tenant context
IDEMPOTENCY=server-specific; durable ledger/inbox equivalence test required
RETRY_MODEL=server worker retry/poll loop; normalize in connector/Temporal policy
ERROR_MODEL=server-specific HTTP/worker errors; normalize to canonical command and connector errors
OBSERVABILITY=health `healthy` plus logs; canonical metrics/audit/correlation required

CANONICAL_MAIN_EQUIVALENT=Kyqra/scraper connector, lead normalization, and Odoo connector
CLASSIFICATION=KEEP_AND_PORT
RATIONALE=Scraper discoveries must enter review_pending and cannot write directly to Odoo.
TEST_REQUIRED=Review-required, provenance, suppression, no-contact, duplicate and Odoo mock tests
SERVER_DEPENDENCIES=Scraper/Kyqra connector; lead normalization; Odoo connector

## F025 — redis

FUNCTION_ID=F025
FUNCTION_NAME=redis
BUSINESS_PURPOSE=Redis remains an optional coordination/cache primitive; durable correctness cannot depend on it.

SERVER_SOURCE_FILES=server-baseline/runtime-images.json (runtime-only evidence)
SERVER_ENTRYPOINT=`docker-entrypoint.sh redis-server --appendonly yes --save 60 1 --maxmemory 384mb --maxmemory-policy noeviction --aclfile /run/secrets/redis-users.acl`
SERVER_CONTAINER=`codestra-middleware-staging-redis-1`
SERVER_IMAGE=`redis@sha256:bb186d083732f669da90be8b0f975a37812b15e913465bb14d845db72a4e3e08`
SERVER_REVISION=`UNKNOWN_PROVENANCE`

SERVER_API_PATHS=see API-ENDPOINT-MAP.md
SERVER_DATABASE_TABLES=see DATABASE-SCHEMA-MAP.md; worker-specific ownership requires command contracts
SERVER_REDIS_USAGE=configuration/coordination only; see REDIS-USAGE-MAP.md
SERVER_QUEUE_USAGE=legacy PostgreSQL polling/outbox, direct HTTP, or runtime-specific loop; see EVENT-TRANSPORT-MAP.md
SERVER_EXTERNAL_SYSTEMS=none evidenced by environment names

AUTH_MODEL=legacy shared bearer, HMAC, mTLS, or service credential depending on boundary; see AUTHORIZATION-MAP.md
TENANT_MODEL=server payload/header/campaign conventions must be replaced by verified canonical tenant context
IDEMPOTENCY=server-specific; durable ledger/inbox equivalence test required
RETRY_MODEL=server worker retry/poll loop; normalize in connector/Temporal policy
ERROR_MODEL=server-specific HTTP/worker errors; normalize to canonical command and connector errors
OBSERVABILITY=health `healthy` plus logs; canonical metrics/audit/correlation required

CANONICAL_MAIN_EQUIVALENT=`platform/redis` runtime dependency
CLASSIFICATION=ALREADY_IMPLEMENTED
RATIONALE=Redis remains an optional coordination/cache primitive; durable correctness cannot depend on it.
TEST_REQUIRED=ACL, outage, restart, cache-loss and no-durability-dependency tests
SERVER_DEPENDENCIES=Staging workers; Redis ACL secret; staging network

## F026 — odoo-result-worker-staging

FUNCTION_ID=F026
FUNCTION_NAME=odoo-result-worker-staging
BUSINESS_PURPOSE=The unique staging revision is release drift, not a distinct supported component.

SERVER_SOURCE_FILES=app/api/v1/integrations.py, app/workers/delivery.py
SERVER_ENTRYPOINT=`python -m app.entrypoints.odoo_result_worker`
SERVER_CONTAINER=`codestra-middleware-staging-odoo-result-worker-staging-1`
SERVER_IMAGE=`codestra/middleware:r1-45c4678`
SERVER_REVISION=`45c467899e0c7580538de72d543fb3de0b09cd75`

SERVER_API_PATHS=see API-ENDPOINT-MAP.md
SERVER_DATABASE_TABLES=see DATABASE-SCHEMA-MAP.md; worker-specific ownership requires command contracts
SERVER_REDIS_USAGE=configuration/coordination only; see REDIS-USAGE-MAP.md
SERVER_QUEUE_USAGE=legacy PostgreSQL polling/outbox, direct HTTP, or runtime-specific loop; see EVENT-TRANSPORT-MAP.md
SERVER_EXTERNAL_SYSTEMS=Odoo, n8n, VICIdial

AUTH_MODEL=legacy shared bearer, HMAC, mTLS, or service credential depending on boundary; see AUTHORIZATION-MAP.md
TENANT_MODEL=server payload/header/campaign conventions must be replaced by verified canonical tenant context
IDEMPOTENCY=server-specific; durable ledger/inbox equivalence test required
RETRY_MODEL=server worker retry/poll loop; normalize in connector/Temporal policy
ERROR_MODEL=server-specific HTTP/worker errors; normalize to canonical command and connector errors
OBSERVABILITY=health `running` plus logs; canonical metrics/audit/correlation required

CANONICAL_MAIN_EQUIVALENT=same canonical Odoo connector worker with staging profile
CLASSIFICATION=DUPLICATE
RATIONALE=The unique staging revision is release drift, not a distinct supported component.
TEST_REQUIRED=Same-image provenance and Odoo mock/read-back tests
SERVER_DEPENDENCIES=Staging PostgreSQL; Odoo staging/mock; Keycloak

## F027 — scraper-odoo-delivery-worker

FUNCTION_ID=F027
FUNCTION_NAME=scraper-odoo-delivery-worker
BUSINESS_PURPOSE=The staging-only image history must collapse into the canonical connector worker build.

SERVER_SOURCE_FILES=app/core/lead_reconciliation.py, app/workers/delivery.py
SERVER_ENTRYPOINT=`python -m app.entrypoints.scraper_odoo_delivery_worker`
SERVER_CONTAINER=`codestra-middleware-staging-scraper-odoo-delivery-worker-1`
SERVER_IMAGE=`codestra/middleware:scraper-protected-main-4780bd72`
SERVER_REVISION=`4780bd72d1c574af4aed62d374ec50b208e8ea4c`

SERVER_API_PATHS=see API-ENDPOINT-MAP.md
SERVER_DATABASE_TABLES=see DATABASE-SCHEMA-MAP.md; worker-specific ownership requires command contracts
SERVER_REDIS_USAGE=configuration/coordination only; see REDIS-USAGE-MAP.md
SERVER_QUEUE_USAGE=legacy PostgreSQL polling/outbox, direct HTTP, or runtime-specific loop; see EVENT-TRANSPORT-MAP.md
SERVER_EXTERNAL_SYSTEMS=Odoo, n8n, VICIdial, Postiz/Postly

AUTH_MODEL=legacy shared bearer, HMAC, mTLS, or service credential depending on boundary; see AUTHORIZATION-MAP.md
TENANT_MODEL=server payload/header/campaign conventions must be replaced by verified canonical tenant context
IDEMPOTENCY=server-specific; durable ledger/inbox equivalence test required
RETRY_MODEL=server worker retry/poll loop; normalize in connector/Temporal policy
ERROR_MODEL=server-specific HTTP/worker errors; normalize to canonical command and connector errors
OBSERVABILITY=health `running` plus logs; canonical metrics/audit/correlation required

CANONICAL_MAIN_EQUIVALENT=same scraper→normalization→Odoo connector pipeline with staging profile
CLASSIFICATION=DUPLICATE
RATIONALE=The staging-only image history must collapse into the canonical connector worker build.
TEST_REQUIRED=Same-image provenance, review_pending and Odoo mock tests
SERVER_DEPENDENCIES=Staging PostgreSQL; scraper mock; Odoo mock

## F028 — social-delivery-worker-staging

FUNCTION_ID=F028
FUNCTION_NAME=social-delivery-worker-staging
BUSINESS_PURPOSE=Unknown image provenance is unacceptable; behavior must be covered by the canonical social connector.

SERVER_SOURCE_FILES=server-baseline/runtime-images.json (runtime-only evidence)
SERVER_ENTRYPOINT=`python -m app.entrypoints.social_delivery_worker`
SERVER_CONTAINER=`codestra-middleware-staging-social-delivery-worker-staging-1`
SERVER_IMAGE=`codestra/middleware:social-staging-12cd5fc`
SERVER_REVISION=`unknown`

SERVER_API_PATHS=see API-ENDPOINT-MAP.md
SERVER_DATABASE_TABLES=see DATABASE-SCHEMA-MAP.md; worker-specific ownership requires command contracts
SERVER_REDIS_USAGE=configuration/coordination only; see REDIS-USAGE-MAP.md
SERVER_QUEUE_USAGE=legacy PostgreSQL polling/outbox, direct HTTP, or runtime-specific loop; see EVENT-TRANSPORT-MAP.md
SERVER_EXTERNAL_SYSTEMS=Odoo, n8n, VICIdial, Postiz/Postly

AUTH_MODEL=legacy shared bearer, HMAC, mTLS, or service credential depending on boundary; see AUTHORIZATION-MAP.md
TENANT_MODEL=server payload/header/campaign conventions must be replaced by verified canonical tenant context
IDEMPOTENCY=server-specific; durable ledger/inbox equivalence test required
RETRY_MODEL=server worker retry/poll loop; normalize in connector/Temporal policy
ERROR_MODEL=server-specific HTTP/worker errors; normalize to canonical command and connector errors
OBSERVABILITY=health `running` plus logs; canonical metrics/audit/correlation required

CANONICAL_MAIN_EQUIVALENT=canonical Postly connector delivery worker
CLASSIFICATION=DUPLICATE
RATIONALE=Unknown image provenance is unacceptable; behavior must be covered by the canonical social connector.
TEST_REQUIRED=Same-image provenance, social mock and no-effect staging tests
SERVER_DEPENDENCIES=Staging PostgreSQL; Postly mock

## F029 — social-dead-letter-worker-staging

FUNCTION_ID=F029
FUNCTION_NAME=social-dead-letter-worker-staging
BUSINESS_PURPOSE=Use the operator-approved dead-letter replay workflow rather than a social-specific undocumented implementation.

SERVER_SOURCE_FILES=server-baseline/runtime-images.json (runtime-only evidence)
SERVER_ENTRYPOINT=`python -m app.entrypoints.social_dead_letter_worker`
SERVER_CONTAINER=`codestra-middleware-staging-social-dead-letter-worker-staging-1`
SERVER_IMAGE=`codestra/middleware:social-staging-12cd5fc`
SERVER_REVISION=`unknown`

SERVER_API_PATHS=see API-ENDPOINT-MAP.md
SERVER_DATABASE_TABLES=see DATABASE-SCHEMA-MAP.md; worker-specific ownership requires command contracts
SERVER_REDIS_USAGE=configuration/coordination only; see REDIS-USAGE-MAP.md
SERVER_QUEUE_USAGE=legacy PostgreSQL polling/outbox, direct HTTP, or runtime-specific loop; see EVENT-TRANSPORT-MAP.md
SERVER_EXTERNAL_SYSTEMS=Odoo, n8n, VICIdial, Postiz/Postly

AUTH_MODEL=legacy shared bearer, HMAC, mTLS, or service credential depending on boundary; see AUTHORIZATION-MAP.md
TENANT_MODEL=server payload/header/campaign conventions must be replaced by verified canonical tenant context
IDEMPOTENCY=server-specific; durable ledger/inbox equivalence test required
RETRY_MODEL=server worker retry/poll loop; normalize in connector/Temporal policy
ERROR_MODEL=server-specific HTTP/worker errors; normalize to canonical command and connector errors
OBSERVABILITY=health `running` plus logs; canonical metrics/audit/correlation required

CANONICAL_MAIN_EQUIVALENT=canonical dead-letter/replay workflow
CLASSIFICATION=REPLACE_WITH_NEW_ARCHITECTURE
RATIONALE=Use the operator-approved dead-letter replay workflow rather than a social-specific undocumented implementation.
TEST_REQUIRED=Approval, audit, correction, replay idempotency and tenant tests
SERVER_DEPENDENCIES=Temporal; PostgreSQL; Postly connector

## F030 — social-reconciliation-worker-staging

FUNCTION_ID=F030
FUNCTION_NAME=social-reconciliation-worker-staging
BUSINESS_PURPOSE=Social reconciliation is a connector specialization of the shared workflow, not a separate source lineage.

SERVER_SOURCE_FILES=server-baseline/runtime-images.json (runtime-only evidence)
SERVER_ENTRYPOINT=`python -m app.entrypoints.social_reconciliation_worker`
SERVER_CONTAINER=`codestra-middleware-staging-social-reconciliation-worker-staging-1`
SERVER_IMAGE=`codestra/middleware:social-staging-12cd5fc`
SERVER_REVISION=`unknown`

SERVER_API_PATHS=see API-ENDPOINT-MAP.md
SERVER_DATABASE_TABLES=see DATABASE-SCHEMA-MAP.md; worker-specific ownership requires command contracts
SERVER_REDIS_USAGE=configuration/coordination only; see REDIS-USAGE-MAP.md
SERVER_QUEUE_USAGE=legacy PostgreSQL polling/outbox, direct HTTP, or runtime-specific loop; see EVENT-TRANSPORT-MAP.md
SERVER_EXTERNAL_SYSTEMS=Odoo, n8n, VICIdial, Postiz/Postly

AUTH_MODEL=legacy shared bearer, HMAC, mTLS, or service credential depending on boundary; see AUTHORIZATION-MAP.md
TENANT_MODEL=server payload/header/campaign conventions must be replaced by verified canonical tenant context
IDEMPOTENCY=server-specific; durable ledger/inbox equivalence test required
RETRY_MODEL=server worker retry/poll loop; normalize in connector/Temporal policy
ERROR_MODEL=server-specific HTTP/worker errors; normalize to canonical command and connector errors
OBSERVABILITY=health `running` plus logs; canonical metrics/audit/correlation required

CANONICAL_MAIN_EQUIVALENT=canonical reconciliation workflow plus Postly read-back
CLASSIFICATION=DUPLICATE
RATIONALE=Social reconciliation is a connector specialization of the shared workflow, not a separate source lineage.
TEST_REQUIRED=Postly read-back mismatch, timeout, retry and restart tests
SERVER_DEPENDENCIES=Temporal; PostgreSQL; Postly connector

## F031 — callback-staging

FUNCTION_ID=F031
FUNCTION_NAME=callback-staging
BUSINESS_PURPOSE=The standalone script and unknown/noncanonical revision should be replaced by the shared signed durable ingress.

SERVER_SOURCE_FILES=app/api/v1/n8n_staging.py
SERVER_ENTRYPOINT=`python3 /app/staging_callback_receiver.py`
SERVER_CONTAINER=`codestra-middleware-staging-callback-staging-1`
SERVER_IMAGE=`codestra/middleware:current-hardened-20260723`
SERVER_REVISION=`f1c07e0-reprofix2`

SERVER_API_PATHS=see API-ENDPOINT-MAP.md
SERVER_DATABASE_TABLES=see DATABASE-SCHEMA-MAP.md; worker-specific ownership requires command contracts
SERVER_REDIS_USAGE=configuration/coordination only; see REDIS-USAGE-MAP.md
SERVER_QUEUE_USAGE=legacy PostgreSQL polling/outbox, direct HTTP, or runtime-specific loop; see EVENT-TRANSPORT-MAP.md
SERVER_EXTERNAL_SYSTEMS=none evidenced by environment names

AUTH_MODEL=legacy shared bearer, HMAC, mTLS, or service credential depending on boundary; see AUTHORIZATION-MAP.md
TENANT_MODEL=server payload/header/campaign conventions must be replaced by verified canonical tenant context
IDEMPOTENCY=server-specific; durable ledger/inbox equivalence test required
RETRY_MODEL=server worker retry/poll loop; normalize in connector/Temporal policy
ERROR_MODEL=server-specific HTTP/worker errors; normalize to canonical command and connector errors
OBSERVABILITY=health `healthy` plus logs; canonical metrics/audit/correlation required

CANONICAL_MAIN_EQUIVALENT=signed connector webhook ingress
CLASSIFICATION=REPLACE_WITH_NEW_ARCHITECTURE
RATIONALE=The standalone script and unknown/noncanonical revision should be replaced by the shared signed durable ingress.
TEST_REQUIRED=Callback HMAC, timestamp, body limit, duplicate, tenant and durable-ack tests
SERVER_DEPENDENCIES=Staging ingress; connector inbox; n8n staging network

## F032 — postgres

FUNCTION_ID=F032
FUNCTION_NAME=postgres
BUSINESS_PURPOSE=PostgreSQL remains the durable store; reconcile schemas/migrations rather than porting the container as application code.

SERVER_SOURCE_FILES=server-baseline/runtime-images.json (runtime-only evidence)
SERVER_ENTRYPOINT=`docker-entrypoint.sh postgres`
SERVER_CONTAINER=`codestra-middleware-staging-postgres-1`
SERVER_IMAGE=`postgres@sha256:ef257d85f76e48da1c64832459b59fcaba1a4dac97bf5d7450c77753542eee94`
SERVER_REVISION=`UNKNOWN_PROVENANCE`

SERVER_API_PATHS=see API-ENDPOINT-MAP.md
SERVER_DATABASE_TABLES=see DATABASE-SCHEMA-MAP.md; worker-specific ownership requires command contracts
SERVER_REDIS_USAGE=configuration/coordination only; see REDIS-USAGE-MAP.md
SERVER_QUEUE_USAGE=legacy PostgreSQL polling/outbox, direct HTTP, or runtime-specific loop; see EVENT-TRANSPORT-MAP.md
SERVER_EXTERNAL_SYSTEMS=Postiz/Postly

AUTH_MODEL=legacy shared bearer, HMAC, mTLS, or service credential depending on boundary; see AUTHORIZATION-MAP.md
TENANT_MODEL=server payload/header/campaign conventions must be replaced by verified canonical tenant context
IDEMPOTENCY=server-specific; durable ledger/inbox equivalence test required
RETRY_MODEL=server worker retry/poll loop; normalize in connector/Temporal policy
ERROR_MODEL=server-specific HTTP/worker errors; normalize to canonical command and connector errors
OBSERVABILITY=health `healthy` plus logs; canonical metrics/audit/correlation required

CANONICAL_MAIN_EQUIVALENT=`platform/postgresql` and canonical migration sets
CLASSIFICATION=ALREADY_IMPLEMENTED
RATIONALE=PostgreSQL remains the durable store; reconcile schemas/migrations rather than porting the container as application code.
TEST_REQUIRED=Empty→head, previous→head, downgrade/upgrade, locking, checksum and restart tests
SERVER_DEPENDENCIES=Middleware schemas; connector-runtime schema; staging network
