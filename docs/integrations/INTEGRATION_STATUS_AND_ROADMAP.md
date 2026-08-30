# Middleware Integration Status and Roadmap

## Current decision

```text
SOURCE_STATE=PARTIAL
DEPLOYMENT_STATE=DISABLED
PRODUCTION_STATE=NO_GO
LIVE_EXTERNAL_EFFECTS=NO
```

The integration architecture, principal repository boundaries, canonical envelopes, effectful adapter manifests, and several source implementations exist. The program is not complete until exact-head CI, route parity, cross-repository contract tests, provider read-back, staging evidence, immutable artifacts, backup/restore, rollback, and independent approval pass.

## Done / partial / missing matrix

| Integration | Owner | State | Done | Missing / next gate |
|---|---|---|---|---|
| `edge-caddy` | `appolon1908-hue/Caddy` | **SOURCE_PARTIAL** | authority boundary; hostname/route expectations; private-upstream rule | accepted route parity; render validation against exact Middleware API; staging TLS/auth evidence; production reload approval |
| `gateway-kong` | `appolon1908-hue/Kong` | **SOURCE_PARTIAL** | gateway authority; desired route artifacts; identity boundary | exact route-to-runtime parity; consumer/service scope tests; staging no-effect test; production apply approval |
| `identity-keycloak` | `appolon1908-hue/Keycloak` | **SOURCE_PARTIAL** | canonical issuer; managed clients/roles source; plan/review/apply design | accepted source promotion; unchanged reviewed plan; staging token matrix; live apply approval |
| `automation-n8n` | `appolon1908-hue/N8N` | **CONTRACT_DEFINED** | wake/claim; leases; approvals; dead-letter rules; provider access prohibited | runtime endpoint parity; approved workflow packs; lease recovery; staging no-effect evidence |
| `business-odoo` | `appolon1908-hue/Odoo` | **CONTRACT_DEFINED** | connector manifest; CRM commands; event boundary; campaign isolation | full field/state mapping; readback parity; campaign isolation tests; write-disabled staging |
| `email-klyrow` | `appolon1908-hue/klyrow.com` | **SOURCE_PARTIAL** | frozen API contract; adapter source; signed events/readback; safe-mode preservation | all Middleware CI green; cross-repo contract tests; duplicate-send proof; safe-mode staging |
| `sms-telnexa` | `appolon1908-hue/telnexa` | **PREPARED_ONLY** | responsibility map; status normalization; Unicode/DLR/MO and reconciliation requirements | runtime implementation; Jasmin adapter; segment accounting; opt-out tests; staging |
| `voice-vicidial` | `appolon1908-hue/Vicidialer-Codestra` | **CONTRACT_DEFINED** | connector manifest; restricted boundary; campaign isolation | canonical voice API; call/readback reconciliation; recording/disposition mapping; no-dial staging |
| `social-postiz` | `appolon1908-hue/social.codestra.co` | **CONTRACT_DEFINED** | connector manifest; social commands; provider events | account/permission mapping; publication readback; duplicate prevention; simulator |
| `crawler-kyqra` | `appolon1908-hue/kyqra-crawler` | **CONTRACT_DEFINED** | canonical repo; connector manifest; signed callback | API parity; private-network denial; batching/reconciliation; legacy cutover evidence |
| `provisioning` | `appolon1908-hue/codestra-provisioning-service` | **CONTRACT_DEFINED** | connector manifest; plan/apply/readback concept; secret prohibition | resource implementations; compensation; drift reconciliation; plan-only staging |
| `beyvra-nonfinancial` | `appolon1908-hue/beyvra-backend` | **CONTRACT_DEFINED** | connector manifest; allowed operations prefix; financial denylist | route parity; negative financial tests; staging readback; security approval |
| `product-clients` | multiple | **PARTIAL** | MoneyBee/BREERO/LARIM/Freight/Beyvra caller skeletons; tenant/scope rules; public intake | Codestra backend decision; restaurant backend authority; Booked4Seasons contract; full matrices |
| `communications-sdk` | `appolon1908-hue/SDK-repository` | **SOURCE_READY_FOR_REVIEW** | Communications API v1; canonical statuses/errors/events | protected merge; generated SDK release; compatibility/deprecation policy |
| `communications-dashboard` | `appolon1908-hue/communication-platform-` | **PREPARED_ONLY** | read-model architecture; dashboard separation; tenant/RBAC model | persistence/views; APIs; operator UI; controlled actions |
| `observability` | 14 principal repositories | **SOURCE_PARTIAL** | repo/hostname ownership; private exposure; metrics/log/trace map | exact-head CI; immutable artifacts; integration lab; staging evidence |
| `secrets-openbao` | `appolon1908-hue/Codestra-OpenBao` | **BLOCKED_DESIGN** | repository authority; OIDC concept; private exposure | storage/HA; seal/unseal; custody; audit; backup/restore/DR; policy certification |
| `planned-control-planes` | four planned repos | **PLANNED** | missions and authority boundaries | contracts; implementations; identity; read models; staging |
| `legacy-cleanup` | `scrapper`, `kyqra`, `Codestraxxxx` | **DECISION_REQUIRED** | canonical crawler decision; legacy labels | archive/deprecation; traffic cutover; credential retirement; placeholder disposition |

## Ordered implementation roadmap

### Phase 0 — Repository and contract authority

- Keep Middleware as the only privileged cross-system write authority.
- Keep `SDK-repository` as the public OpenAPI/AsyncAPI and generated-client authority.
- Keep every external runtime/application in its principal repository.
- Re-scope stale duplicate PRs without discarding audit history.

**Exit:** complete registry validates; authority conflicts are resolved; no bypass exists.

### Phase 1 — Edge, identity, and caller parity

- Reconcile Caddy host/upstream expectations with Kong routes and exact Middleware routes.
- Reconcile Keycloak issuer, audience, client IDs, scopes, roles, and service identities.
- Validate every control-plane caller against an actual identity and adapter target.
- Prove missing bearer, bad signature, wrong audience/tenant, expired token, and forbidden scope denial.

**Exit:** Caddy/Kong/Keycloak/Middleware compatibility tests pass; no live apply.

### Phase 2 — Durable Middleware core

- Finish command/operation APIs, signed inbox, transactional outbox, delivery ledger, dead letters, and controlled replay.
- Prove semantic idempotency, optimistic concurrency, crash/lease recovery, and timeout read-back.
- Require source-head and merge-result CI.

**Exit:** persistence and no-effect E2E tests pass with every capability false.

### Phase 3 — Email first

- Complete Middleware ↔ Klyrow against frozen Communications API v1.
- Fix all Middleware email CI failures.
- Prove consent/suppression, signed callbacks, replay denial, domain/sender reads, provider health, and reputation.
- Prove unknown outcomes cannot cause duplicate email submission.

**Exit:** Step 3 evidence complete; safe mode and production gates remain disabled.

### Phase 4 — SMS

- Implement Middleware ↔ Telnexa/Jasmin commands, DLR/MO events, Unicode, segmentation, opt-out, usage, and billing reads.
- Prove duplicate prevention and authoritative read-back.

**Exit:** contract and simulator tests pass; no external SMS sent.

### Phase 5 — Voice/contact center

- Implement the restricted Middleware ↔ VICIdial/Asterisk command/read-back/event boundary.
- Enforce permanent campaign isolation and campaign-scoped scripts, dispositions, callbacks, recordings, transfers, email, and dashboards.
- Prove no public admin API and no production dialing.

**Exit:** private simulator tests pass with `PRODUCTION_DIALING=false`.

### Phase 6 — CRM, crawler, social, and provisioning

- Complete Odoo field/state mappings and campaign isolation tests.
- Complete Kyqra reconciliation and legacy cutover.
- Complete Postiz read-back and duplicate-publish prevention.
- Complete provisioning plan/apply/read-back/compensation/drift logic.

**Exit:** every adapter has implementation, read-back, recovery, and no-effect evidence.

### Phase 7 — Product integrations

- Define caller contracts for Codestra, MoneyBee, BREERO, Freight, LARIMÍA, Booked4Seasons, restaurant, and other products.
- Resolve `codestra-backend` versus `backend2` and identify the restaurant backend.
- Keep frontends behind their backend or same-origin public intake.

**Exit:** each product has a least-privilege client, negative tests, and status/read-model integration.

### Phase 8 — Dashboard, observability, analytics, and secrets

- Build normalized read models and operator APIs.
- Wire Grafana to approved telemetry and Superset to curated read-only models.
- Complete OpenBao storage, HA, seal/unseal, custody, audit, backup/restore, and DR before runtime use.

**Exit:** read-only dashboards work; all mutations remain governed; OpenBao design is certified.

### Phase 9 — Cross-repository release candidate

- Run the disposable lab with synthetic identities, credentials, providers, and data.
- Build immutable artifacts with SBOM, provenance, signatures, checksums, vulnerability and license evidence.
- Run backup/restore and rollback rehearsals.
- Freeze exact accepted SHAs into one release-evidence note.

**Exit:** `FROZEN_SOURCE_CANDIDATE`; deployment remains disabled.

### Phase 10 — Separate deployment program

Only after repository completion: read-only inventory, backups, isolated staging, Keycloak plan-only review, Caddy/firewall render-only review, staging canary, external port scan, rollback rehearsal, and a separate production go/no-go.

## Immediate blockers

1. Accept and validate the complete registry and authority files in this branch.
2. Re-scope stale Connector SDK PR #17 so it no longer claims complete-system authority.
3. Fix Middleware email implementation PR #52 until all source and merge-result jobs pass.
4. Accept the SDK Communications API contract before SMS and voice implementation.
5. Resolve canonical Codestra backend and restaurant backend ownership.

No roadmap item authorizes deployment or a live external effect.
