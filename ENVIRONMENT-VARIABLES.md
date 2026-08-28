# Environment variable inventory

Generated from the captured application, workers, Dockerfiles, Compose files, and scripts. No live values are included. Requirement/default semantics remain defined by the referenced code.

| Variable | Requirement | Secret | Consumers |
|---|---|---|---|
| `AI_AUDIT_LOG_FILE` | inspect code/default | no/inspect deployment | application/runtime |
| `AI_COMMAND_TIMEOUT_SECONDS` | inspect code/default | no/inspect deployment | application/runtime |
| `AI_DAILY_TOKEN_QUOTA` | inspect code/default | yes | application/runtime |
| `AI_DEFAULT_MAX_QUEUED_PER_TENANT` | inspect code/default | no/inspect deployment | application/runtime |
| `AI_DEFAULT_MAX_RUNNING_PER_TENANT` | inspect code/default | no/inspect deployment | application/runtime |
| `AI_ENRICHMENT_ENABLED` | inspect code/default | no/inspect deployment | application/runtime |
| `AI_GLOBAL_EMERGENCY_LIMIT` | inspect code/default | no/inspect deployment | application/runtime |
| `AI_HMAC_SECRET_FILE` | inspect code/default | yes | application/runtime |
| `AI_JOB_LEASE_SECONDS` | inspect code/default | no/inspect deployment | application/runtime |
| `AI_JOB_MAX_ATTEMPTS` | inspect code/default | no/inspect deployment | application/runtime |
| `AI_JOB_MAX_CONTEXT_BYTES` | inspect code/default | no/inspect deployment | application/runtime |
| `AI_JOB_MAX_OUTPUT_BYTES` | inspect code/default | no/inspect deployment | application/runtime |
| `AI_JOB_PROJECT_ALLOWLIST` | inspect code/default | no/inspect deployment | application/runtime |
| `AI_ORCHESTRATION_ENABLED` | inspect code/default | no/inspect deployment | application/runtime |
| `AI_PRIVATE_API_ENABLED` | inspect code/default | no/inspect deployment | application/runtime |
| `AI_RATE_LIMIT_PER_MINUTE` | inspect code/default | no/inspect deployment | application/runtime |
| `AI_SERVICE_ID` | inspect code/default | no/inspect deployment | application/runtime |
| `AI_SIGNATURE_TTL_SECONDS` | inspect code/default | no/inspect deployment | application/runtime |
| `AI_SUBMISSIONS_ENABLED` | inspect code/default | no/inspect deployment | application/runtime |
| `AI_WORKER_CERTIFICATE_IP` | inspect code/default | no/inspect deployment | application/runtime |
| `AI_WORKER_CERTIFICATE_SERIAL` | inspect code/default | no/inspect deployment | application/runtime |
| `AI_WORKER_CLAIMS_ENABLED` | inspect code/default | no/inspect deployment | application/runtime |
| `AI_WORKER_CLIENT_CA_FILE` | inspect code/default | no/inspect deployment | application/runtime |
| `AI_WORKER_HMAC_KEY_ID` | inspect code/default | no/inspect deployment | application/runtime |
| `AI_WORKER_ID` | inspect code/default | no/inspect deployment | application/runtime |
| `AI_WORKER_SERVICE_ID` | inspect code/default | no/inspect deployment | application/runtime |
| `AI_WORKER_SOURCE_CIDRS` | inspect code/default | no/inspect deployment | application/runtime |
| `AI_WORKER_SPIFFE_ID` | inspect code/default | no/inspect deployment | application/runtime |
| `AI_WORKER_TENANT_ID` | inspect code/default | no/inspect deployment | application/runtime |
| `AI_WORKER_TRUSTED_PROXY_CIDR` | inspect code/default | no/inspect deployment | application/runtime |
| `AI_WORKER_WORKSPACE_ID` | inspect code/default | no/inspect deployment | application/runtime |
| `ALLOWED_CLIENT_INSTANCES` | inspect code/default | no/inspect deployment | application/runtime |
| `ALLOW_LIVE_EMAIL` | inspect code/default | no/inspect deployment | application/runtime |
| `ALLOW_LIVE_SMS` | inspect code/default | no/inspect deployment | application/runtime |
| `ALLOW_NON_TEST_CAMPAIGNS` | inspect code/default | no/inspect deployment | application/runtime |
| `APOLLO_PROVIDER_ENABLED` | inspect code/default | no/inspect deployment | application/runtime |
| `AUTOMATION_ACTIONS_ENABLED` | inspect code/default | no/inspect deployment | application/runtime |
| `AUTOMATION_ALLOWED_CAMPAIGNS` | inspect code/default | no/inspect deployment | application/runtime |
| `AUTOMATION_ENVIRONMENT` | inspect code/default | no/inspect deployment | application/runtime |
| `AUTOMATION_HMAC_SECRET` | inspect code/default | yes | application/runtime |
| `BROAD_EVENT_ACTIVATION_HIGH_WATER_MARK` | inspect code/default | no/inspect deployment | application/runtime |
| `BROAD_EVENT_BUSINESS_UNIT_ALLOWLIST` | inspect code/default | no/inspect deployment | application/runtime |
| `BROAD_EVENT_CAMPAIGN_ALLOWLIST` | inspect code/default | no/inspect deployment | application/runtime |
| `BROAD_EVENT_DELIVERY_ENABLED` | inspect code/default | no/inspect deployment | application/runtime |
| `BROAD_EVENT_SUBMISSION_LIMIT` | inspect code/default | no/inspect deployment | application/runtime |
| `BROAD_EVENT_TYPE_ALLOWLIST` | inspect code/default | no/inspect deployment | application/runtime |
| `BROAD_EVENT_WORKFLOW_ALLOWLIST` | inspect code/default | no/inspect deployment | application/runtime |
| `CALLBACK_DISPATCH_ENABLED` | inspect code/default | no/inspect deployment | application/runtime |
| `CONTROLLED_BROAD_EVENT_ACTIVATION` | inspect code/default | no/inspect deployment | application/runtime |
| `CONTROLLER_APPROVAL_SIGNING_KEY_FILE` | inspect code/default | no/inspect deployment | application/runtime |
| `CONTROLLER_PRIVATE_ENABLED` | inspect code/default | no/inspect deployment | application/runtime |
| `CONTROLLER_WORKSPACE_ALLOWLIST` | inspect code/default | no/inspect deployment | application/runtime |
| `COSIGN_SHA256` | inspect code/default | no/inspect deployment | application/runtime |
| `COSIGN_VERSION` | inspect code/default | no/inspect deployment | application/runtime |
| `DATABASE_MAX_OVERFLOW` | inspect code/default | no/inspect deployment | application/runtime |
| `DATABASE_POOL_SIZE` | inspect code/default | no/inspect deployment | application/runtime |
| `DATABASE_POOL_TIMEOUT_SECONDS` | inspect code/default | no/inspect deployment | application/runtime |
| `DATABASE_URL` | inspect code/default | yes | application/runtime |
| `DATABASE_URL_FILE` | inspect code/default | yes | application/runtime |
| `DEPLOYED_SOURCE_SHA` | inspect code/default | no/inspect deployment | application/runtime |
| `ELEVENLABS_API_KEY_FILE` | inspect code/default | yes | application/runtime |
| `ELEVENLABS_BASE_URL` | inspect code/default | no/inspect deployment | application/runtime |
| `ELEVENLABS_BROWSER_OUTPUT_FORMAT` | inspect code/default | no/inspect deployment | application/runtime |
| `ELEVENLABS_CANARY_VOICE_ID` | inspect code/default | no/inspect deployment | application/runtime |
| `ELEVENLABS_CONNECT_TIMEOUT_SECONDS` | inspect code/default | no/inspect deployment | application/runtime |
| `ELEVENLABS_MAX_CONCURRENCY` | inspect code/default | no/inspect deployment | application/runtime |
| `ELEVENLABS_MAX_RETRIES` | inspect code/default | no/inspect deployment | application/runtime |
| `ELEVENLABS_MAX_TEXT_CHARACTERS` | inspect code/default | no/inspect deployment | application/runtime |
| `ELEVENLABS_MODEL_ID` | inspect code/default | no/inspect deployment | application/runtime |
| `ELEVENLABS_PROVIDER_ENABLED` | inspect code/default | no/inspect deployment | application/runtime |
| `ELEVENLABS_READ_TIMEOUT_SECONDS` | inspect code/default | no/inspect deployment | application/runtime |
| `ELEVENLABS_REQUEST_LOGGING_MODE` | inspect code/default | no/inspect deployment | application/runtime |
| `ELEVENLABS_TELEPHONY_OUTPUT_FORMAT` | inspect code/default | no/inspect deployment | application/runtime |
| `ELEVENLABS_TOTAL_TIMEOUT_SECONDS` | inspect code/default | no/inspect deployment | application/runtime |
| `EMAIL_DISPATCH_ENABLED` | inspect code/default | no/inspect deployment | application/runtime |
| `ENABLED_EVENT_TYPES` | inspect code/default | no/inspect deployment | application/runtime |
| `ENABLE_EXTERNAL_DELIVERY` | inspect code/default | no/inspect deployment | application/runtime |
| `ENVIRONMENT` | inspect code/default | no/inspect deployment | application/runtime |
| `EXPECTED_IDENTITY` | inspect code/default | no/inspect deployment | application/runtime |
| `EXPECTED_ISSUER` | inspect code/default | no/inspect deployment | application/runtime |
| `EXPORT_UPLOAD_ENABLED` | inspect code/default | no/inspect deployment | application/runtime |
| `EXTENSION_ALLOCATOR_ENABLED` | inspect code/default | no/inspect deployment | application/runtime |
| `EXTERNAL_DIAL_ENABLED` | inspect code/default | no/inspect deployment | application/runtime |
| `FORWARDED_ALLOW_IPS` | inspect code/default | no/inspect deployment | application/runtime |
| `GITHUB_REF` | inspect code/default | no/inspect deployment | application/runtime |
| `GITHUB_REPOSITORY` | inspect code/default | no/inspect deployment | application/runtime |
| `GITHUB_SHA` | inspect code/default | no/inspect deployment | application/runtime |
| `HOOTSUITE_CLIENT_ID_FILE` | inspect code/default | no/inspect deployment | application/runtime |
| `HOOTSUITE_CLIENT_SECRET_FILE` | inspect code/default | yes | application/runtime |
| `HOOTSUITE_ENABLED` | inspect code/default | no/inspect deployment | application/runtime |
| `HOOTSUITE_REDIRECT_URI` | inspect code/default | no/inspect deployment | application/runtime |
| `HUNTER_PROVIDER_ENABLED` | inspect code/default | no/inspect deployment | application/runtime |
| `INGESTION_HMAC_SECRET` | inspect code/default | yes | application/runtime |
| `INGESTION_TOKEN` | inspect code/default | yes | application/runtime |
| `KEYCLOAK_AUDIENCE` | inspect code/default | no/inspect deployment | application/runtime |
| `KEYCLOAK_AUTHORIZED_PARTIES` | inspect code/default | no/inspect deployment | application/runtime |
| `KEYCLOAK_ISSUER` | inspect code/default | no/inspect deployment | application/runtime |
| `KEYCLOAK_JWKS_URL` | inspect code/default | no/inspect deployment | application/runtime |
| `KEYCLOAK_USERINFO_URL` | inspect code/default | no/inspect deployment | application/runtime |
| `LEAD_ASSIGNMENT_ENABLED` | inspect code/default | no/inspect deployment | application/runtime |
| `LEAD_AUTOMATION_ENABLED` | inspect code/default | no/inspect deployment | application/runtime |
| `LEAD_AUTOMATION_HMAC_SECRET` | inspect code/default | yes | application/runtime |
| `LEAD_CALLBACK_CREATE_ENABLED` | inspect code/default | no/inspect deployment | application/runtime |
| `LEAD_CREATE_ENABLED` | inspect code/default | no/inspect deployment | application/runtime |
| `LEAD_OUTREACH_ENABLED` | inspect code/default | no/inspect deployment | application/runtime |
| `LEAD_STATUS_CHANGE_ENABLED` | inspect code/default | no/inspect deployment | application/runtime |
| `LEAD_UPDATE_ENABLED` | inspect code/default | no/inspect deployment | application/runtime |
| `LEAD_VERIFICATION_DRY_RUN_ONLY` | inspect code/default | no/inspect deployment | application/runtime |
| `LITELLM_API_KEY_FILE` | inspect code/default | yes | application/runtime |
| `LITELLM_BASE_URL_FILE` | inspect code/default | no/inspect deployment | application/runtime |
| `LIVE_WRITES_ENABLED` | inspect code/default | no/inspect deployment | application/runtime |
| `LOG_LEVEL` | inspect code/default | no/inspect deployment | application/runtime |
| `MAINTENANCE_INTERVAL_SECONDS` | inspect code/default | no/inspect deployment | application/runtime |
| `MESSAGING_ENABLED` | inspect code/default | no/inspect deployment | application/runtime |
| `MIDDLEWARE_IMAGE` | inspect code/default | no/inspect deployment | application/runtime |
| `MIDDLEWARE_N8N_AUDIENCE` | inspect code/default | no/inspect deployment | application/runtime |
| `MIDDLEWARE_N8N_CLIENT_ID` | inspect code/default | no/inspect deployment | application/runtime |
| `MIDDLEWARE_N8N_CLIENT_SECRET_FILE` | inspect code/default | yes | application/runtime |
| `MIDDLEWARE_N8N_SCOPE` | inspect code/default | no/inspect deployment | application/runtime |
| `MIDDLEWARE_N8N_TOKEN_URL` | inspect code/default | yes | application/runtime |
| `MIDDLEWARE_SECRET` | inspect code/default | yes | application/runtime |
| `MIDDLEWARE_SECRET_FILE` | inspect code/default | yes | application/runtime |
| `N8N_CONCURRENCY` | inspect code/default | no/inspect deployment | application/runtime |
| `N8N_DELIVERY_ENABLED` | inspect code/default | no/inspect deployment | application/runtime |
| `N8N_EVENT_DELIVERY_ENABLED` | inspect code/default | no/inspect deployment | application/runtime |
| `N8N_LEAD_BINDING_ENABLED` | inspect code/default | no/inspect deployment | application/runtime |
| `N8N_LEAD_DELIVERY_ENABLED` | inspect code/default | no/inspect deployment | application/runtime |
| `N8N_ORDER_DISPATCH_ENABLED` | inspect code/default | no/inspect deployment | application/runtime |
| `N8N_PRODUCTION_IMAGE_DIGEST` | inspect code/default | no/inspect deployment | application/runtime |
| `N8N_PRODUCTION_INSTANCE_ID` | inspect code/default | no/inspect deployment | application/runtime |
| `N8N_PRODUCTION_TARGET_IDENTITY` | inspect code/default | no/inspect deployment | application/runtime |
| `N8N_PRODUCTION_TARGET_URL` | inspect code/default | no/inspect deployment | application/runtime |
| `N8N_PRODUCTION_VERSION` | inspect code/default | no/inspect deployment | application/runtime |
| `N8N_PRODUCTION_WORKFLOWS_ENABLED` | inspect code/default | no/inspect deployment | application/runtime |
| `N8N_RECORDING_BINDING_ENABLED` | inspect code/default | no/inspect deployment | application/runtime |
| `N8N_RECORDING_WORKFLOW_ACTIVE` | inspect code/default | no/inspect deployment | application/runtime |
| `N8N_RECORDING_WORKFLOW_ENABLED` | inspect code/default | no/inspect deployment | application/runtime |
| `N8N_RESULT_PROCESSING_ENABLED` | inspect code/default | no/inspect deployment | application/runtime |
| `N8N_RUNTIME_BASE_URL` | inspect code/default | no/inspect deployment | application/runtime |
| `N8N_RUNTIME_DISPATCH_TIMEOUT_SECONDS` | inspect code/default | no/inspect deployment | application/runtime |
| `N8N_RUNTIME_ENABLED` | inspect code/default | no/inspect deployment | application/runtime |
| `N8N_RUNTIME_ENVIRONMENT` | inspect code/default | no/inspect deployment | application/runtime |
| `N8N_RUNTIME_HEALTH_URL` | inspect code/default | no/inspect deployment | application/runtime |
| `N8N_RUNTIME_HMAC_SECRET_FILE` | inspect code/default | yes | application/runtime |
| `N8N_RUNTIME_MAX_ATTEMPTS` | inspect code/default | no/inspect deployment | application/runtime |
| `N8N_RUNTIME_WORKFLOW_TIMEOUT_SECONDS` | inspect code/default | no/inspect deployment | application/runtime |
| `N8N_SERVICE_AUDIENCE` | inspect code/default | no/inspect deployment | application/runtime |
| `N8N_SERVICE_CLIENT_ID` | inspect code/default | no/inspect deployment | application/runtime |
| `N8N_SERVICE_ISSUER` | inspect code/default | no/inspect deployment | application/runtime |
| `N8N_SERVICE_JWKS_URL` | inspect code/default | no/inspect deployment | application/runtime |
| `N8N_TARGET_CA_FILE` | inspect code/default | no/inspect deployment | application/runtime |
| `N8N_WORKFLOW_PACKAGE_SHA256` | inspect code/default | no/inspect deployment | application/runtime |
| `ODOO_AUDIENCE` | inspect code/default | no/inspect deployment | application/runtime |
| `ODOO_AUTOMATION_WRITES_ENABLED` | inspect code/default | no/inspect deployment | application/runtime |
| `ODOO_BASE_URL` | inspect code/default | no/inspect deployment | application/runtime |
| `ODOO_CA_FILE` | inspect code/default | no/inspect deployment | application/runtime |
| `ODOO_CLIENT_ID` | inspect code/default | no/inspect deployment | application/runtime |
| `ODOO_CLIENT_SECRET_FILE` | inspect code/default | yes | application/runtime |
| `ODOO_CONCURRENCY` | inspect code/default | no/inspect deployment | application/runtime |
| `ODOO_CONNECT_TIMEOUT` | inspect code/default | no/inspect deployment | application/runtime |
| `ODOO_DELIVERY_ENABLED` | inspect code/default | no/inspect deployment | application/runtime |
| `ODOO_IDENTITY_LOOKUP_HMAC_FILE` | inspect code/default | no/inspect deployment | application/runtime |
| `ODOO_IDENTITY_LOOKUP_URL` | inspect code/default | no/inspect deployment | application/runtime |
| `ODOO_LEAD_APPLY_ENABLED` | inspect code/default | no/inspect deployment | application/runtime |
| `ODOO_LEAD_WRITE_ENABLED` | inspect code/default | no/inspect deployment | application/runtime |
| `ODOO_MAX_RETRIES` | inspect code/default | no/inspect deployment | application/runtime |
| `ODOO_PRODUCTION_WRITES_ENABLED` | inspect code/default | no/inspect deployment | application/runtime |
| `ODOO_READ_ENABLED` | inspect code/default | no/inspect deployment | application/runtime |
| `ODOO_READ_TIMEOUT` | inspect code/default | no/inspect deployment | application/runtime |
| `ODOO_RECORDING_HMAC_SECRET` | inspect code/default | yes | application/runtime |
| `ODOO_RECORDING_HMAC_SECRET_FILE` | inspect code/default | yes | application/runtime |
| `ODOO_RECORDING_WRITE_ENABLED` | inspect code/default | no/inspect deployment | application/runtime |
| `ODOO_RESULTS_CA_FILE` | inspect code/default | no/inspect deployment | application/runtime |
| `ODOO_RESULTS_CLIENT_ID` | inspect code/default | no/inspect deployment | application/runtime |
| `ODOO_RESULTS_CLIENT_SECRET_FILE` | inspect code/default | yes | application/runtime |
| `ODOO_RESULT_DELIVERY_ENABLED` | inspect code/default | no/inspect deployment | application/runtime |
| `ODOO_SCOPE` | inspect code/default | no/inspect deployment | application/runtime |
| `ODOO_SERVICE_CREDENTIAL_REFERENCE` | inspect code/default | yes | application/runtime |
| `ODOO_SERVICE_PRIVATE_KEY_FILE` | inspect code/default | yes | application/runtime |
| `ODOO_STAGING_WRITES_ENABLED` | inspect code/default | no/inspect deployment | application/runtime |
| `ODOO_SYNC_BATCH_SIZE` | inspect code/default | no/inspect deployment | application/runtime |
| `ODOO_SYNC_BUSINESS_UNITS` | inspect code/default | no/inspect deployment | application/runtime |
| `ODOO_SYNC_LEASE_SECONDS` | inspect code/default | no/inspect deployment | application/runtime |
| `ODOO_SYNC_WORKER_ENABLED` | inspect code/default | no/inspect deployment | application/runtime |
| `ODOO_SYNC_WORKER_ID` | inspect code/default | no/inspect deployment | application/runtime |
| `ODOO_TOKEN_URL` | inspect code/default | yes | application/runtime |
| `ODOO_WRITE_ENABLED` | inspect code/default | no/inspect deployment | application/runtime |
| `OPENAI_API_KEY_FILE` | inspect code/default | yes | application/runtime |
| `OPENAI_CHAT_MODEL` | inspect code/default | no/inspect deployment | application/runtime |
| `OPENAI_CHAT_REASONING_EFFORT` | inspect code/default | no/inspect deployment | application/runtime |
| `OPENAI_CODING_MODEL` | inspect code/default | no/inspect deployment | application/runtime |
| `OPENAI_CODING_REASONING_EFFORT` | inspect code/default | no/inspect deployment | application/runtime |
| `OPENAI_DAILY_PROJECT_TOKEN_LIMIT` | inspect code/default | yes | application/runtime |
| `OPENAI_DAILY_USER_TOKEN_LIMIT` | inspect code/default | yes | application/runtime |
| `OPENAI_LEAD_CLASSIFICATION_ENABLED` | inspect code/default | no/inspect deployment | application/runtime |
| `OPENAI_MAX_ESTIMATED_COST_MICRO_USD` | inspect code/default | no/inspect deployment | application/runtime |
| `OPENAI_MAX_RETRIES` | inspect code/default | no/inspect deployment | application/runtime |
| `OPENAI_PROVIDER_ENABLED` | inspect code/default | no/inspect deployment | application/runtime |
| `OPENAI_REQUEST_TIMEOUT_SECONDS` | inspect code/default | no/inspect deployment | application/runtime |
| `OPENAI_SAFETY_SALT_FILE` | inspect code/default | no/inspect deployment | application/runtime |
| `OPENAI_WORKER_ID` | inspect code/default | no/inspect deployment | application/runtime |
| `OPENAI_WORKER_MAX_CONCURRENCY` | inspect code/default | no/inspect deployment | application/runtime |
| `OPENAI_WORKER_SERVICE_ID` | inspect code/default | no/inspect deployment | application/runtime |
| `OPENCORPORATES_PROVIDER_ENABLED` | inspect code/default | no/inspect deployment | application/runtime |
| `ORDER_ORCHESTRATION_ENABLED` | inspect code/default | no/inspect deployment | application/runtime |
| `OUTBOX_BASE_DELAY_SECONDS` | inspect code/default | no/inspect deployment | application/runtime |
| `OUTBOX_LEASE_SECONDS` | inspect code/default | no/inspect deployment | application/runtime |
| `OUTBOX_MAX_ATTEMPTS` | inspect code/default | no/inspect deployment | application/runtime |
| `OUTBOX_MAX_DELAY_SECONDS` | inspect code/default | no/inspect deployment | application/runtime |
| `OUTBOX_WORKER_ENABLED` | inspect code/default | no/inspect deployment | application/runtime |
| `OUTREACH_ENABLED` | inspect code/default | no/inspect deployment | application/runtime |
| `PJSIP_PROVISIONING_ENABLED` | inspect code/default | no/inspect deployment | application/runtime |
| `PORT` | inspect code/default | no/inspect deployment | application/runtime |
| `POSTIZ_ANALYTICS_ENABLED` | inspect code/default | no/inspect deployment | application/runtime |
| `POSTIZ_API_KEY_FILE` | inspect code/default | yes | application/runtime |
| `POSTIZ_CA_FILE` | inspect code/default | no/inspect deployment | application/runtime |
| `POSTIZ_CLIENT_CERT_FILE` | inspect code/default | no/inspect deployment | application/runtime |
| `POSTIZ_CLIENT_KEY_FILE` | inspect code/default | no/inspect deployment | application/runtime |
| `POSTIZ_DELIVERY_ENABLED` | inspect code/default | no/inspect deployment | application/runtime |
| `POSTIZ_INTERNAL_BASE_URL` | inspect code/default | no/inspect deployment | application/runtime |
| `POSTIZ_MEDIA_UPLOAD_ENABLED` | inspect code/default | no/inspect deployment | application/runtime |
| `POSTIZ_ORGANIZATION_REFERENCE` | inspect code/default | no/inspect deployment | application/runtime |
| `POSTIZ_PUBLISH_ENABLED` | inspect code/default | no/inspect deployment | application/runtime |
| `POSTIZ_TIMEOUT_SECONDS` | inspect code/default | no/inspect deployment | application/runtime |
| `POSTLY_LEAD_DELIVERY_ENABLED` | inspect code/default | no/inspect deployment | application/runtime |
| `POSTLY_POLLING_ENABLED` | inspect code/default | no/inspect deployment | application/runtime |
| `POSTLY_POLL_BATCH_SIZE` | inspect code/default | no/inspect deployment | application/runtime |
| `POSTLY_POLL_INTERVAL_SECONDS` | inspect code/default | no/inspect deployment | application/runtime |
| `POSTLY_POLL_LOOKBACK_SECONDS` | inspect code/default | no/inspect deployment | application/runtime |
| `POSTLY_WEBHOOK_SECRET` | inspect code/default | yes | application/runtime |
| `POSTLY_WEBHOOK_SECRET_FILE` | inspect code/default | yes | application/runtime |
| `PRODUCTION_N8N_ENABLED` | inspect code/default | no/inspect deployment | application/runtime |
| `PROVISIONING_SERVICE_CA_FILE` | inspect code/default | no/inspect deployment | application/runtime |
| `PROVISIONING_SERVICE_CLIENT_ID` | inspect code/default | no/inspect deployment | application/runtime |
| `PROVISIONING_SERVICE_CLIENT_SECRET_FILE` | inspect code/default | yes | application/runtime |
| `PROVISIONING_SERVICE_TOKEN_URL` | inspect code/default | yes | application/runtime |
| `PROVISIONING_SERVICE_URL` | inspect code/default | no/inspect deployment | application/runtime |
| `PUBLISHER_CANARY_ENABLED` | inspect code/default | no/inspect deployment | application/runtime |
| `PUBLISHER_HMAC_KEYS_FILE` | inspect code/default | no/inspect deployment | application/runtime |
| `PYTHON_BASE` | inspect code/default | no/inspect deployment | application/runtime |
| `QUARANTINE_ENCRYPTION_KEY_FILE` | inspect code/default | no/inspect deployment | application/runtime |
| `QUARANTINE_ENCRYPTION_KEY_VERSION` | inspect code/default | no/inspect deployment | application/runtime |
| `QUARANTINE_FINGERPRINT_SECRET_FILE` | inspect code/default | yes | application/runtime |
| `QUARANTINE_RATE_LIMIT_PER_MINUTE` | inspect code/default | no/inspect deployment | application/runtime |
| `QUARANTINE_RETENTION_DAYS` | inspect code/default | no/inspect deployment | application/runtime |
| `QUARANTINE_RETENTION_POLICY_VERSION` | inspect code/default | no/inspect deployment | application/runtime |
| `QUARANTINE_REVIEWER_SECRET_FILE` | inspect code/default | yes | application/runtime |
| `QUARANTINE_STORE_AUTHENTICATED_RAW` | inspect code/default | no/inspect deployment | application/runtime |
| `QUEUE_NAME` | inspect code/default | no/inspect deployment | application/runtime |
| `QWEN_API_KEY_FILE` | inspect code/default | yes | application/runtime |
| `QWEN_BASE_URL_FILE` | inspect code/default | no/inspect deployment | application/runtime |
| `READINESS_PUBLISHER_CERT_SHA256` | inspect code/default | no/inspect deployment | application/runtime |
| `READINESS_PUBLISHER_KEY_ID` | inspect code/default | no/inspect deployment | application/runtime |
| `RECONCILIATION_CONCURRENCY` | inspect code/default | no/inspect deployment | application/runtime |
| `RECORDING_CONCURRENCY` | inspect code/default | no/inspect deployment | application/runtime |
| `RECORDING_PLAYBACK_URL_TTL_SECONDS` | inspect code/default | no/inspect deployment | application/runtime |
| `RECORDING_UPLOAD_URL_TTL_SECONDS` | inspect code/default | no/inspect deployment | application/runtime |
| `REDIS_RUNTIME_ENABLED` | inspect code/default | no/inspect deployment | application/runtime |
| `REDIS_RUNTIME_ENVIRONMENT` | inspect code/default | no/inspect deployment | application/runtime |
| `REDIS_RUNTIME_PREFIX` | inspect code/default | no/inspect deployment | application/runtime |
| `REDIS_RUNTIME_SOCKET_TIMEOUT_SECONDS` | inspect code/default | no/inspect deployment | application/runtime |
| `REDIS_URL` | inspect code/default | yes | application/runtime |
| `REDIS_URL_FILE` | inspect code/default | yes | application/runtime |
| `REGISTRY_L1_TTL_SECONDS` | inspect code/default | no/inspect deployment | application/runtime |
| `REGISTRY_L2_TTL_SECONDS` | inspect code/default | no/inspect deployment | application/runtime |
| `REGISTRY_SERVICE_AUDIENCE` | inspect code/default | no/inspect deployment | application/runtime |
| `REGISTRY_SERVICE_CLIENT_ID` | inspect code/default | no/inspect deployment | application/runtime |
| `REGISTRY_SERVICE_ISSUER` | inspect code/default | no/inspect deployment | application/runtime |
| `REGISTRY_SERVICE_JWKS_URL` | inspect code/default | no/inspect deployment | application/runtime |
| `REGISTRY_SNAPSHOT_SIGNING_KEY_FILE` | inspect code/default | no/inspect deployment | application/runtime |
| `REGISTRY_STALE_GRACE_SECONDS` | inspect code/default | no/inspect deployment | application/runtime |
| `REPORT_DELIVERY_ENABLED` | inspect code/default | no/inspect deployment | application/runtime |
| `REQUEST_MAX_BYTES` | inspect code/default | no/inspect deployment | application/runtime |
| `RETENTION_DELETE_ENABLED` | inspect code/default | no/inspect deployment | application/runtime |
| `RETENTION_WORKER_ENABLED` | inspect code/default | no/inspect deployment | application/runtime |
| `RUNNER_TEMP` | inspect code/default | no/inspect deployment | application/runtime |
| `RUNTIME_ARTIFACT_CHECKSUM` | inspect code/default | no/inspect deployment | application/runtime |
| `SALES_IDENTITY_RESOLUTION_ENABLED` | inspect code/default | no/inspect deployment | application/runtime |
| `SALES_LEAD_INTAKE_ENABLED` | inspect code/default | no/inspect deployment | application/runtime |
| `SALES_LEAD_REQUEST_MAX_BYTES` | inspect code/default | no/inspect deployment | application/runtime |
| `SALES_ODOO_READ_ONLY_LOOKUP_ENABLED` | inspect code/default | no/inspect deployment | application/runtime |
| `SALES_SCRAPER_CAMPAIGN_ALLOWLIST` | inspect code/default | no/inspect deployment | application/runtime |
| `SALES_SCRAPER_HMAC_SECRET_FILE` | inspect code/default | yes | application/runtime |
| `SALES_SCRAPER_IDENTITY` | inspect code/default | no/inspect deployment | application/runtime |
| `SALES_SCRAPER_TENANT_ID` | inspect code/default | no/inspect deployment | application/runtime |
| `SALES_VERIFICATION_JOBS_ENABLED` | inspect code/default | no/inspect deployment | application/runtime |
| `SALES_VERIFICATION_MAX_CONCURRENCY` | inspect code/default | no/inspect deployment | application/runtime |
| `SCRAPER_MIDDLEWARE_DELIVERY_ENABLED` | inspect code/default | no/inspect deployment | application/runtime |
| `SCRAPER_RESULT_INGEST_ENABLED` | inspect code/default | no/inspect deployment | application/runtime |
| `SEND_EVENTS` | inspect code/default | no/inspect deployment | application/runtime |
| `SERVER_A_AGENT_BIND` | inspect code/default | no/inspect deployment | application/runtime |
| `SERVER_A_AGENT_ENABLED` | inspect code/default | no/inspect deployment | application/runtime |
| `SERVICE_NAME` | inspect code/default | no/inspect deployment | application/runtime |
| `SIGNATURE_TTL_SECONDS` | inspect code/default | no/inspect deployment | application/runtime |
| `SMS_DISPATCH_ENABLED` | inspect code/default | no/inspect deployment | application/runtime |
| `SOCIAL_ANALYTICS_SYNC_ENABLED` | inspect code/default | no/inspect deployment | application/runtime |
| `SOCIAL_AUTOMATIC_DUAL_PUBLISH_ENABLED` | inspect code/default | no/inspect deployment | application/runtime |
| `SOCIAL_AUTOMATIC_PROVIDER_FAILOVER_ENABLED` | inspect code/default | no/inspect deployment | application/runtime |
| `SOCIAL_INTEGRATION_ENABLED` | inspect code/default | no/inspect deployment | application/runtime |
| `SOCIAL_JOB_MAX_ATTEMPTS` | inspect code/default | no/inspect deployment | application/runtime |
| `SOCIAL_N8N_DELIVERY_BATCH_SIZE` | inspect code/default | no/inspect deployment | application/runtime |
| `SOCIAL_N8N_DELIVERY_LEASE_SECONDS` | inspect code/default | no/inspect deployment | application/runtime |
| `SOCIAL_N8N_DELIVERY_WORKER_ENABLED` | inspect code/default | no/inspect deployment | application/runtime |
| `SOCIAL_N8N_DELIVERY_WORKER_ID` | inspect code/default | no/inspect deployment | application/runtime |
| `SOCIAL_N8N_EVENTS_ENABLED` | inspect code/default | no/inspect deployment | application/runtime |
| `SOCIAL_ODOO_SYNC_ENABLED` | inspect code/default | no/inspect deployment | application/runtime |
| `SOCIAL_ODOO_WRITE_ENABLED` | inspect code/default | no/inspect deployment | application/runtime |
| `SOCIAL_PRODUCTION_BACKUP_GATE_VERIFIED` | inspect code/default | no/inspect deployment | application/runtime |
| `SOCIAL_PRODUCTION_CANARY_ACCOUNT_IDS` | inspect code/default | no/inspect deployment | application/runtime |
| `SOCIAL_PRODUCTION_CANARY_CAMPAIGN_IDS` | inspect code/default | no/inspect deployment | application/runtime |
| `SOCIAL_PRODUCTION_CANARY_ENABLED` | inspect code/default | no/inspect deployment | application/runtime |
| `SOCIAL_PRODUCTION_CANARY_TENANT_IDS` | inspect code/default | no/inspect deployment | application/runtime |
| `SOCIAL_PRODUCTION_MODE` | inspect code/default | no/inspect deployment | application/runtime |
| `SOCIAL_PRODUCTION_MONITORING_GATE_VERIFIED` | inspect code/default | no/inspect deployment | application/runtime |
| `SOCIAL_PRODUCTION_ROLLBACK_GATE_VERIFIED` | inspect code/default | no/inspect deployment | application/runtime |
| `SOCIAL_PRODUCTION_WEBHOOK_GATE_VERIFIED` | inspect code/default | no/inspect deployment | application/runtime |
| `SOCIAL_PROVIDER` | inspect code/default | no/inspect deployment | application/runtime |
| `SOCIAL_PROVIDER_MIGRATION_MODE` | inspect code/default | no/inspect deployment | application/runtime |
| `SOCIAL_PROVIDER_MODE` | inspect code/default | no/inspect deployment | application/runtime |
| `SOCIAL_PUBLISH_ENABLED` | inspect code/default | no/inspect deployment | application/runtime |
| `SOCIAL_SQL_REPOSITORY_ENABLED` | inspect code/default | no/inspect deployment | application/runtime |
| `SOCIAL_WEBHOOK_TTL_SECONDS` | inspect code/default | no/inspect deployment | application/runtime |
| `SOCIAL_WORKER_CONCURRENCY` | inspect code/default | no/inspect deployment | application/runtime |
| `SOCIAL_WORKER_ENABLED` | inspect code/default | no/inspect deployment | application/runtime |
| `SOCIAL_WORKER_ID` | inspect code/default | no/inspect deployment | application/runtime |
| `SOCIAL_WORKER_LEASE_SECONDS` | inspect code/default | no/inspect deployment | application/runtime |
| `SOCIAL_WORKER_POLL_SECONDS` | inspect code/default | no/inspect deployment | application/runtime |
| `TELEPHONY_COMMAND_WORKER_ENABLED` | inspect code/default | no/inspect deployment | application/runtime |
| `TELEPHONY_CREDENTIAL_DIRECTORY` | inspect code/default | yes | application/runtime |
| `TELEPHONY_EVIDENCE_ENABLED` | inspect code/default | no/inspect deployment | application/runtime |
| `TELEPHONY_NOTIFICATIONS_ENABLED` | inspect code/default | no/inspect deployment | application/runtime |
| `TELEPHONY_PROVISIONING_ENABLED` | inspect code/default | no/inspect deployment | application/runtime |
| `TELEPHONY_RECONCILIATION_ENABLED` | inspect code/default | no/inspect deployment | application/runtime |
| `TELEPHONY_SERVICE_CLIENT_ID` | inspect code/default | no/inspect deployment | application/runtime |
| `TEST_DATABASE_URL` | inspect code/default | yes | application/runtime |
| `TEST_SYN_ODOO_BUSINESS_UNIT_PUBLIC_ID` | inspect code/default | no/inspect deployment | application/runtime |
| `TEST_SYN_ODOO_CAMPAIGN_PUBLIC_ID` | inspect code/default | no/inspect deployment | application/runtime |
| `TEST_SYN_ODOO_CORRELATION_ID` | inspect code/default | no/inspect deployment | application/runtime |
| `TEST_SYN_ODOO_EVENT_ID` | inspect code/default | no/inspect deployment | application/runtime |
| `TEST_SYN_ODOO_EVENT_TYPE` | inspect code/default | no/inspect deployment | application/runtime |
| `TEST_SYN_ODOO_ORGANIZATION_PUBLIC_ID` | inspect code/default | no/inspect deployment | application/runtime |
| `TEST_SYN_ODOO_OUTBOX_PUBLIC_ID` | inspect code/default | no/inspect deployment | application/runtime |
| `TEST_SYN_ODOO_RESULT_DELIVERY_ENABLED` | inspect code/default | no/inspect deployment | application/runtime |
| `TEST_SYN_ODOO_TENANT_ID` | inspect code/default | no/inspect deployment | application/runtime |
| `TEST_SYN_ODOO_WORKFLOW_CODE` | inspect code/default | no/inspect deployment | application/runtime |
| `TEST_SYN_ODOO_WORKFLOW_VERSION` | inspect code/default | no/inspect deployment | application/runtime |
| `TRANSFER_CONTROL_ENABLED` | inspect code/default | no/inspect deployment | application/runtime |
| `TWILIO_LOOKUP_PROVIDER_ENABLED` | inspect code/default | no/inspect deployment | application/runtime |
| `VICIDIAL_AUTHORIZATION_URL` | inspect code/default | yes | application/runtime |
| `VICIDIAL_CALLBACK_HMAC_SECRET_FILE` | inspect code/default | yes | application/runtime |
| `VICIDIAL_CA_FILE` | inspect code/default | no/inspect deployment | application/runtime |
| `VICIDIAL_CLIENT_CERT_FILE` | inspect code/default | no/inspect deployment | application/runtime |
| `VICIDIAL_CLIENT_KEY_FILE` | inspect code/default | no/inspect deployment | application/runtime |
| `VICIDIAL_CRL_FILE` | inspect code/default | no/inspect deployment | application/runtime |
| `VICIDIAL_EDGE_URL` | inspect code/default | no/inspect deployment | application/runtime |
| `VICIDIAL_LEAD_WRITE_ENABLED` | inspect code/default | no/inspect deployment | application/runtime |
| `VICIDIAL_PROVISIONING_ENABLED` | inspect code/default | no/inspect deployment | application/runtime |
| `VICIDIAL_PUBLICATION_ENABLED` | inspect code/default | no/inspect deployment | application/runtime |
| `VICIDIAL_READ_ENABLED` | inspect code/default | no/inspect deployment | application/runtime |
| `VICIDIAL_WRITE_ENABLED` | inspect code/default | no/inspect deployment | application/runtime |
| `WEBHOOK_SHARED_SECRET` | inspect code/default | yes | application/runtime |
| `WEBHOOK_SHARED_SECRET_FILE` | inspect code/default | yes | application/runtime |
| `WEBPHONE_ENDPOINT_ADAPTER_URL` | inspect code/default | no/inspect deployment | application/runtime |
| `WEBPHONE_EXPECTED_USER` | inspect code/default | no/inspect deployment | application/runtime |
| `WEBPHONE_KEYCLOAK_ENABLED` | inspect code/default | no/inspect deployment | application/runtime |
| `WEBPHONE_ORIGIN_HOST` | inspect code/default | no/inspect deployment | application/runtime |
| `WEBPHONE_ORIGIN_SCHEME` | inspect code/default | no/inspect deployment | application/runtime |
| `WEBPHONE_SESSION_ISSUER_ENABLED` | inspect code/default | no/inspect deployment | application/runtime |
| `WEBPHONE_STAGING_CAMPAIGN` | inspect code/default | no/inspect deployment | application/runtime |
| `WEBPHONE_STAGING_ENDPOINT` | inspect code/default | no/inspect deployment | application/runtime |
| `WEBPHONE_STAGING_PROVISIONING_ENABLED` | inspect code/default | no/inspect deployment | application/runtime |
| `WORKER_INTERVAL_SECONDS` | inspect code/default | no/inspect deployment | application/runtime |
