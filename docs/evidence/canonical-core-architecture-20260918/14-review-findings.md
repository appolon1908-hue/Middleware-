# 14 — Self-review findings and residual risks

Findings raised during the implementation review (all resolved unless marked residual):

| # | Finding | Severity | Resolution |
| --- | --- | --- | --- |
| 1 | `SEND_EVENTS` semantics differed between lineages; a naive merge would have either weakened the broad-event conjunction or silently made JetStream dispatch impossible without saying so | high | union of both rules kept; documented in `docs/RUNTIME-INTAKE-V1.md` and the migration doc; test asserts the exact refusal messages |
| 2 | First factory draft returned 503 for every `/api/*` route when the container was absent, breaking ORM routes that never needed it | high | removed; only control-plane routes depend on the container (via `app.core.providers`, 503 envelope) |
| 3 | First factory draft resolved settings with a fresh `Settings.from_env()` instead of the process-wide instance, so tests (and any operator tooling) mutating `app.core.config.settings` were ignored | high | factory binds to the process-wide instance after `validate_configuration()` |
| 4 | Two live implementations of `POST /v1/telephony/calls/originate` (Appolon calling contract vs ORM agent-UI) would have been resolved by registration order | high | documented contract wins; ORM handler unrouted; decision recorded (needs product confirmation, see residual) |
| 5 | Global `RequestValidationError` → 400 envelope would have changed canonical/integration routes from 422 to 400 for Odoo/n8n clients | medium | per-route-group policy (control plane 400, sales 422 sanitized, others FastAPI 422); OpenAPI shaping follows |
| 6 | Generic 256 KiB Content-Length cap in the guard pre-empted the control plane's per-route 1 MiB limit and its canonical 413 envelope; a 5000-digit Content-Length hit Python's int-digit limit inside the guard | medium | control-plane routes exempt from the guard's Content-Length handling |
| 7 | Deployed `/version` read `SOURCE_SHA`, which the runtime image never sets (`APP_SOURCE_SHA`) | medium | settings-based version with `SOURCE_SHA` alias |
| 8 | `FEATURE_FLAG_STATE` gauge would have been registered twice (entrypoint + bootstrap) | medium | single definition in `bootstrap`, re-exported |
| 9 | Readiness probing the derived production Keycloak from local/CI processes with an implicit identity | medium | `identity_probe_required()`; explicit or staging/production only |
| 10 | Legacy edge-denied n8n aliases were mounted on the control-plane canary (`domain_api` + `n8n_control_plane`) and would have failed the release endpoint audit once the profiles unified | medium | moved to `LEGACY_MONOLITH_ONLY_ROUTERS` (monolith only) |
| 11 | `validate_platform_control_plane.py` had been red since `ad8b2f9` (base) | medium | re-targeted to the registry (no weakening of the contract's intent) |
| 12 | Import-time timestamp in `tests/test_provider_webhooks.py` made five tests fail after 300 s of suite runtime (latent flake exposed by a longer suite) | low | timestamp refreshed per minute |
| 13 | `from_identity` classmethod broke test fakes that replace `KeycloakValidator` with plain classes | low | sites use `KeycloakValidator(**identity_validator_kwargs(...))`; fakes untouched |
| 14 | Windows CRLF written by the contract generator would have produced a 16 k-line whitespace diff | low | artifacts normalized to LF before commit |
| 15 | mypy on Linux flagged three pre-existing issues in files the commit touches (CI runs mypy on changed files) | low | fixed (`certify_edge_integration.py`, two tests) |

## Residual risks / items needing a human decision

1. **`POST /v1/telephony/calls/originate` ownership** (finding 4): agent-UI callers of the deployed
   integration API that used the shared-secret ORM route will now receive 401 (service JWT required). No live
   dialing is possible in any environment (`EXTERNAL_DIAL_ENABLED=false`, `PRODUCTION_DIALING=DISABLED`), so
   the impact is limited to admission records. Confirm or re-route the agent-UI handler to a distinct path.
2. **Canary surface**: the production read-only canary (`app.main:create_app`) loses the five deprecated n8n
   aliases and gains the canonical health aliases; validation errors on its canonical routes are now 422.
3. **Integration API surface**: `/metrics` is now authenticated; correlation ids are echoed when well-formed.
   If an external Prometheus scrape of the integration API exists outside this repository it needs the
   `monitoring-readonly` bearer (the compose healthchecks use `/healthz` and `/readyz`).
4. **JetStream dispatch** cannot be enabled by configuration until `N8N_PRODUCTION_WORKFLOWS_ENABLED` is
   promoted (or the broad-event conjunction is re-scoped) by an explicit approval.
5. **Per-process validation** now includes `validate_domain()` for the narrow entrypoints; any deployment
   whose environment file violates the domain policy (e.g. a non-canonical audience) will refuse to start
   instead of running degraded — intended, but it must be checked in staging before production promotion.
6. Per-request Redis clients in four routers/adapters remain (tracked for M3).
