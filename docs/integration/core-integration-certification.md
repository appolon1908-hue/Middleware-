# Codestra local core integration — certification (2026-09-19)

Mission: **CODESTRA LOCAL CORE INTEGRATION (Middleware ↔ Kong ↔ Caddy ↔ Keycloak ↔ Odoo ↔ N8N)**, contract-first, local repositories only, no production activation, no provider effects, `PRODUCTION_GO=NO`.

Every claim below is backed by a file in one of the six local checkouts or by a test in `tests/cross_repo/`; the generated inputs are `docs/integration/core-contract-matrix.{md,json}` (`scripts/cross_repo_contract_matrix.py`) and `docs/integration/core-port-contract.{md,json}` (`scripts/cross_repo_port_contract.py`). Gaps are recorded as strict `xfail` tests carrying the exact finding — never as a pass.

## Integration branches (local worktrees, nothing merged, no force push)

| Repository | Branch | Head | Change |
|---|---|---|---|
| Middleware- | `integration/core-crossrepo-20260919` | see `git log` | contract matrix generator + matrix, port contract, `tests/cross_repo/` (50 passed, 6 strict xfail), this document |
| Kong | `integration/middleware-8095-20260919` | `360aaad` | vendored Middleware contract re-pinned to `c13554eb…` (post-#280), route `middleware-ingress-odoo-event` renamed in registry + policy, docs regenerated; six V3 kernel routes prepared `PREPARED_DISABLED` with `V3_PENDING_FINAL_MIDDLEWARE_CONTRACT=true` and a fail-closed loader + tests |
| Caddy | `integration/kong-edge-20260919` | `1364fd6` | `@kong` matcher covers every Kong-owned operation family (21 prefixes, 76 operations no longer fall through), 23 client-identity headers deleted on the Kong handoff, contract pins the Middleware digest, guard refined + tests (33 passed) |
| Keycloak | `integration/middleware-identity-20260919` | `9f20d7b` | `platform.command`, `platform.command.read`, `platform.command.replay` prepared as optional client scopes attached to no client, never realm defaults; test enforces it; five required clients verified present, none created or duplicated |
| Odoo | `integration/middleware-command-contract-20260919` | `1bad581` (= base) | analysis only: outbound calls classified (kind, auth, headers, target), inbound controllers inventoried, direct provider path recorded; no source change |
| N8N | `integration/middleware-automation-contract-20260919` | `dd100d8` (= base) | analysis only: executor boundary verified (targets, headers, carriers, SOURCE_ONLY); no source change |
| Middleware V3 (separate branch) | `mission/middleware-v3-platform-20260918` | `f2b9cf8` | N8N executor adapter wrapping `app.adapters.n8n.transport` (9 tests), registered for staging/preproduction only when configured |

## Per-repository certification

### Middleware
- Contract matrix generated from source (92 rows: 80 shared_edge, 2 private_only, 10 denied); `MIDDLEWARE_CONTRACT_HASH=c13554ebededa3ba6c39d0408adcd93f33baa941cac905907f6d63d390d93fab`.
- `tests/cross_repo`: **50 passed, 6 xfailed (strict, documented gaps)**; skipped cleanly (42 skipped) when the sibling repositories are absent, e.g. in CI.
- Locked-image certification of the integration branch: see the run record appended below.
- gitleaks 8.30.1 (`dir . --exit-code 1`): no leaks found.

### Kong
- `validate_kong_foundation` PASS (SOURCES=25 SERVICES=38 ROUTES=285, PREPARED_DISABLED=12, OVERLAPS unchanged 60, `TRANSITIONAL_8080_ALIASES=0`), `validate_kong_production_inventory` PASS (ROUTES=27 DUPLICATES=0 DIRECT_PROVIDER=0), `validate_middleware_edge_contract` PASS at `c13554eb…`, `validate_kong_calling_policy` PASS (+ self-test), `validate_community_n8n_egress` OK, `validate_release_supply_chain` OK, JSON/YAML parse OK.
- pytest: 770 passed; 4 failures + 4 errors are Windows-host artifacts (umask/symlink/deep-JSON parametrisation) identical to the pre-change baseline.
- gitleaks: no leaks found.

### Caddy
- `validate_repository` PASS (`CADDY_TO_KONG_CONTRACT=PASS`, `KONG_ROUTE_CONTRACT_BIDIRECTIONAL=PASS`, `DIRECT_MIDDLEWARE_FOR_KONG_PATHS=DENIED`), `caddy validate` / `caddy adapt --validate` in the pinned image with the CI environment: valid; `caddy fmt`: unchanged; 33 tests passed.
- Adapted JSON confirms the Kong handler sets only `Host`/`X-Real-IP` and deletes 23 headers.
- gitleaks: no leaks found.

### Keycloak
- `render-machine-client-overlays --check` PASS, `validate-service-integrations` PASS, `validate-kong-oidc-contract` PASS, `validate-n8n-flow` PASS, `validate_stage6_intake_observability_source` PASS; unittest 160 tests with the same 5 Windows-host failures (symlink/mode/`python3`) as the untouched tree.
- gitleaks: no leaks found.

### Odoo / N8N
- No source changed; both certified by the cross-repo suite against their current source. gitleaks: no leaks found (both).

## Required mission outputs

```
MIDDLEWARE_CONTRACT_MATRIX=DONE            docs/integration/core-contract-matrix.md (92 rows, 80 shared_edge)
CADDY_TO_KONG=PASS                          76 formerly fall-through operations now matched; identity headers deleted; edge headers preserved
KONG_TO_MIDDLEWARE=PASS                     vendored contract == Middleware contract; 80/80 routes on middleware-integration-api:8095; 0 audience/scope/azp/auth mismatches
KEYCLOAK_TO_MIDDLEWARE=PASS_WITH_GAPS       clients + token contract + negatives PASS; scope gap (n8n-automation, odoo-integration) and 4 undefined calling clients recorded as strict xfail
ODOO_TO_MIDDLEWARE=PASS_WITH_GAPS           every outbound call targets a served path; edge-contract calls carry idempotency+correlation via Caddy→Kong; static bearer (+HMAC) on /api/v1/odoo/events, Klyrow SMTP relay, and 7 calls outside the 8095 edge contract recorded as strict xfail
MIDDLEWARE_TO_ODOO=PASS_WITH_GAPS           sync adapter paths exist as Odoo controllers; campaign-control endpoint seeds (0066) do not match Odoo controllers — strict xfail
MIDDLEWARE_TO_N8N=PASS                      N8N targets only /v2/automation contract operations with required headers/carriers, SOURCE_ONLY; Middleware delivers via the attested one-attempt reservation transport
DUPLICATE_KONG_ROUTES=0
DIRECT_PROVIDER_ROUTES=0
CANONICAL_8080=0                            only the retired/denied alias remains, PREPARED_DISABLED / RETIRE_CANDIDATE
PUBLIC_API_DIRECT_TO_MIDDLEWARE=0
PUBLIC_API_DIRECT_TO_ODOO=0
PUBLIC_API_DIRECT_TO_N8N=0
DIRECT_PROVIDER_BYPASSES=0                  over HTTP; the one SMTP relay (Odoo codestra_klyrow_smtp → mail.klyrow.com) is recorded, not hidden
LOCAL_CORE_CONTRACT_TEST=PASS               static six-source chain for the 5 concrete-client operations + in-process fail-closed/envelope/correlation + 100 identical claims → 1 lease
V3_PENDING_FINAL_MIDDLEWARE_CONTRACT=true   Kong routes PREPARED_DISABLED, Keycloak scopes optional-only, Middleware V3 branch pending rebase on MAIN_AFTER_279
PRODUCTION_GO=NO
```

## Findings that need an owner decision (not silently "fixed")

1. **Keycloak scope gap** — `n8n-automation` does not issue `n8n.policy.check`, `n8n.results.submit`, `n8n.results.read`; `odoo-integration` does not issue `odoo.campaigns.read`. Kong would answer 403 `missingRequiredScope`. The grants are pinned in `service_integration_validator.EXPECTED_GRANTS` and `validate-n8n-flow.py`.
2. **Keycloak client gap** — the contract names `callback-ui`, `github-app`, `n8n-operations-automation`, `observability-collector`; none exists in `config/clients`.
3. **Odoo static bearer** — `codestra_agent_onboarding` posts `/api/v1/odoo/events` with a pre-provisioned bearer file + HMAC (`CODESTRA_MIDDLEWARE_ODOO_EVENTS_TOKEN_FILE/_HMAC_FILE`); the contract requires `odoo-service-jwt` (Keycloak `client_credentials`, azp `odoo-integration`, scope `odoo.events.publish`).
4. **Odoo calls outside the edge contract** — email/SMS transports (`/v1/communications/messages`), telephony (`/v1/telephony/commands`, `/v1/telephony/calls/originate`, `/v1/calls/originate`), `/api/v1/campaign-designs/preview`, control-callback operations and recordings playback target Middleware control-plane/monolith routes that are not in the 8095 contract and (except control callbacks) not routed by Caddy to Kong.
5. **Odoo direct provider path** — `codestra_klyrow_smtp` pins an `ir.mail_server` to `mail.klyrow.com:25`.
6. **Middleware → Odoo campaign-control paths** — endpoint-registry seeds (`0066`) name `POST /api/v1/integration/automation-results`, `…/campaigns/actual-state`, `…/campaigns/read`, `…/desired-state/read`; Odoo exposes `POST …/results`, `GET …/campaigns/<id>`, `GET …/desired-state/<type>/<id>` and no actual-state controller.
7. **Trace context** — no inbound `traceparent` handling in Middleware and none sent by N8N templates; correlation (`X-Correlation-ID`) is end-to-end, tracing is not.
8. **Provider-control contract (Kong)** — `config/kong-provider-control-routes.v1.json` stays `PREPARED_DISABLED` on the retired `:8080` alias; its command routes have no Middleware operation today and are superseded by the V3 kernel (`BLOCKED_ON_MIDDLEWARE_V3_FINAL_SHA`).
9. **Caddy legacy catch-all** — still present for non-Kong paths with `legacyFallbackTemporarilyAllowed=true`; removal is a runtime-inventory + rollback-rehearsal cutover decision.

## Deployment gate (mission phase 27)

Not met, by design of the mission:
- #279 successor (#283 @ `eb1764a`) not yet merged (awaiting independent approval).
- PRs #257 / #259 / #269 unresolved.
- Middleware V3 final SHA not frozen; Kong/Keycloak V3 contracts pending.
- `PRODUCTION_GO=NO`.
