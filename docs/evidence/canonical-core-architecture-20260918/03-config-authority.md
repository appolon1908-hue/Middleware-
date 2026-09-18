# 03 — Configuration authority: `app/core/config.py`

One `Settings` (pydantic-settings) carries every field of both former lineages. `app/config.py` is a
seven-name re-export shim that emits `DeprecationWarning` and defines nothing.

## Construction and validation

| Entry | Sources | Validation |
| --- | --- | --- |
| `Settings()` (process-wide `settings`) | `os.environ`, secret files | `load_secret_files()`, asyncpg URL normalization, `validate_safety()` at import; `validate_domain()` + identity invariants at startup via `validate_configuration()` |
| `Settings.from_env(mapping)` | the mapping only (`os.environ` not consulted; `DATABASE_URL`/`REDIS_URL` empty unless present) | `load_secret_files()`, `validate_domain()`, `validate_safety()`; every defect → `ConfigurationError` |
| `settings.replace(**fields)` | copy with declared fields changed, no re-validation (test helper; unknown field → `TypeError`) | — |

## Environment names

| Canonical | Accepted aliases | Note |
| --- | --- | --- |
| `KEYCLOAK_JWKS_URL` | `KEYCLOAK_JWKS_URI` | temporary; remove after certification |
| `KEYCLOAK_AUDIENCE` | `MIDDLEWARE_AUDIENCE` | temporary |
| `APP_SOURCE_SHA` | `SOURCE_SHA` | `Dockerfile.runtime` bakes `APP_SOURCE_SHA`; the former entrypoint read `SOURCE_SHA` |
| `ODOO_19_BASE_URL`, `ODOO_19_HMAC_SECRET`, `ODOO_19_TENANT_HMAC_SECRETS`, `ODOO_19_TIMEOUT_SECONDS` | — | fields `odoo_19_base_url`, … (renamed to avoid the core `odoo_base_url`) |
| `SMS_DELIVERY_ENABLED`, `EMAIL_DELIVERY_ENABLED`, `SOCIAL_DELIVERY_ENABLED` | — | fields `effect_*_delivery_enabled` |
| `LIVE_ADVERTISING_ENABLED`, `EXTERNAL_DELIVERY_ENABLED`, `SOCIAL_PUBLISHING_ENABLED`, `EXTERNAL_MODEL_CALLS_ENABLED`, `N8N_EXTERNAL_PROVIDER_WRITES` | — | fields `umbrella_*`; view `umbrella_controls` |
| `RUNTIME_REBUILD_INTERVAL_SECONDS` | — | new, 5–600 s, default 30 |

## Rules merged from both lineages (all kept; the union applies)

- Environment policy (`validate_domain`): `APP_ENV` ∈ {development, test, staging, production}; `ENVIRONMENT` must match in staging/production; issuer must equal the environment authority unless the synthetic CI identity is used in development/test; JWKS derived from the issuer; audience `middleware-api`; effect gates ⊆ `SUPPORTED_EXTERNAL_EFFECTS`; umbrella controls off in staging; delivery effects need `EXTERNAL_DELIVERY_ENABLED`; Odoo transport (HTTPS, ≥32-byte secrets, tenant map parsed even while writes are off); NATS and Temporal rules; in-memory storage only in test/development; schema head pinned; staging/production require 40-char SHA, sha256 digest, build time, all seven webhook secrets; runtime profile lock.
- Safety policy (`validate_safety`): every production switch off; broad-event conjunction + bounded scope; social canary gates; Telnexa/Klyrow ingress secrets.
- **`SEND_EVENTS`** (both lineages): transport triplet consistency **and** broad-event conjunction. Because `N8N_PRODUCTION_WORKFLOWS_ENABLED` is not a supported effect, no configuration can enable JetStream dispatch today — proven by `tests/test_security.py::test_production_jetstream_dispatch_requires_every_broad_event_gate`.

## Test matrix (all passing locally)

| Test | Proves |
| --- | --- |
| `tests/test_core_config_authority.py` (11) | mapping isolation, aliases, `ConfigurationError` on bad values, `replace()`, implicit vs explicit identity, integration validators refuse implicit identity, wildcard tenant rejection, schema head/audience pins, secret files, per-service startup requirements, flag readback without secrets |
| `tests/test_security.py` (47) | issuer/JWKS/audience policy, synthetic identity, umbrella kill switches, JetStream rules, Temporal isolation, staging release identity, webhook secrets |
| `tests/test_architecture_governance.py::test_settings_class_is_defined_once`, `::test_legacy_modules_are_pure_shims`, `::test_environment_is_read_only_by_configuration_authority`, `::test_synthetic_ci_identity_is_never_valid_in_staging_or_production` | one schema; shims define nothing; `os.getenv` ratchet; synthetic identity rule |
| `tests/test_odoo_transport.py` (Odoo settings part) | Odoo 19 transport rules under the canonical names |
