# CI, environments, and current handoff

Status snapshot: 2026-08-29

This is the concise operating reference for Middleware source, CI, environment promotion, and the next gated work in the CRM/telephony/messaging mission. It does not authorize deployment and it does not replace repository-specific runtime evidence.

## Branch and environment model

Middleware uses `main` as its release source branch. Staging and production are deployment environments, not Git branches. The same immutable image digest accepted in staging is promoted to production only after the applicable approval and read-back gates.

Codestra uses a **decentralized repository release model**. Every owning repository releases independently from an immutable accepted source/artifact identity and couples to other repositories through versioned contracts. No central mutable repository may silently override the accepted release of another service.

For a cross-repository feature, Middleware owns the combined **evidence note** because it is the cross-system write boundary. That evidence role does not give Middleware authority to merge, deploy or activate another repository.

See:

- `docs/STAGE0_GROUND_TRUTH_20260829.md`
- `docs/CROSS_REPOSITORY_RELEASE_EVIDENCE.md`
- `docs/releases/RELEASE_EVIDENCE_TEMPLATE.md`

## CI coverage

| Workflow | Pull requests | Push to `main` | Responsibility |
|---|---|---|---|
| `Middleware CI` | Yes | Yes | Repository validators, locked tests, runtime image smoke, PostgreSQL/Redis, NATS, Temporal, synthetic no-effect acceptance and security gates |
| `Connector SDK v1 validation` | Relevant paths | Relevant paths | Connector manifests, generated artifacts, contracts and SDK regression tests |
| `Connector storage v1` | Relevant paths | Relevant paths | Alembic migrations, RLS/tenant isolation, concurrency, backup/restore and downgrade/upgrade |
| `Connector Runtime API validation` | Relevant paths | Relevant paths | Management API, PostgreSQL integration and migration replay |
| `Signed Middleware Release` | protected release path | accepted `main` source | Build, scan, sign, verify and preserve immutable service release evidence |

Recommended protected checks include repository validation, runtime image build/smoke, disposable PostgreSQL/Redis, NATS, Temporal critical workflows, synthetic no-effect E2E and all affected connector checks.

Branch protection and GitHub Environment controls are repository settings; workflow YAML alone cannot prove they are active. Confirm the actual settings before merge or promotion.

## Promotion model

For Middleware itself:

```text
workstream PR
  -> exact-head CI
  -> protected merge to main
  -> exact-main-SHA CI
  -> immutable signed Middleware image/artifact
  -> staging deployment with external effects disabled
  -> runtime read-back + synthetic acceptance + restore/rollback proof
  -> explicit production approval
  -> promote the identical accepted digest
```

For a feature spanning repositories:

```text
versioned contract
  -> independently reviewed implementation PRs
  -> exact accepted SHA/digest per repository
  -> cross-repository staging acceptance
  -> Middleware release-evidence note listing every immutable identity
  -> separately approved capability activation
```

## Caddy and gateway ownership

Stage 0 resolved the previous shared-Caddy ownership ambiguity:

- `appolon1908-hue/Kong` is the **future shared API-edge Caddy source authority** under `deploy/caddy/`, alongside Kong gateway/security source.
- `appolon1908-hue/codestra-production-platform` is retained as historical deployment/runtime-reconciliation/rollback evidence, not a central release authority.
- Middleware `platform/caddy` remains compatibility/review source, not the future production shared-edge source.
- Product-specific frontend/webserver configuration remains in the product repository unless it is part of the shared `api.codestra.co` edge.

No live Caddy configuration has been moved. Source convergence requires read-only runtime inventory, checksums, staging Caddy -> Kong validation, rollback rehearsal, immutable deployment and post-change read-back.

## Canonical provider ownership

```text
Telnexa/Jasmin          = SMS
Vicidialer-Codestra     = VICIdial/Asterisk voice/contact-center connector
Klyrow/Postal/Mautic    = email/customer communications
kyqra-crawler           = canonical crawler runtime
n8n                     = orchestration only
Odoo                    = CRM/business state
Middleware              = sole cross-system command/write authority
Keycloak                = identity authority
Kong                    = API/security gateway
```

The legacy `appolon1908-hue/kyqra` repository is historical only. `scrapper` has active source/hardening work but no repository-backed staging or production deployment evidence and must not become a competing crawler runtime.

## Current gated status

### Stage 0 — source ground truth

The repository/source-authority audit is implemented in draft PRs across the owning repositories. It resolves Kyqra, Telnexa/Klyrow frontend-backend splits, Scrapper deployment truth, SDK-vs-runtime connector ownership and future shared Caddy ownership.

Stage 0 is source-complete only after those PRs receive their normal review/merge treatment. It does not change live runtime.

### Stage 1 — identity foundation

Keycloak and Kong source contracts are substantially implemented and the current Keycloak/Kong OIDC alignment PRs have green source validation. The live exit gate remains mandatory:

```text
real Client Credentials token issued by auth.codestra.co
-> accepted by the reviewed Kong route
-> invalid/expired/wrong-audience token rejected
-> Middleware receives and revalidates the intended service/tenant identity
```

Do **not** declare Stage 1 complete from Git configuration alone.

### Stage 2 — Middleware Phase 4

Several tasks from the older mission wording are already present in source or in reviewed open hardening branches:

- Connector Runtime is independently packaged under `services/connector-runtime`.
- streaming request-size/encrypted-body safety work exists in dedicated Connector Runtime hardening PRs;
- runtime/quality gates and dependency audit are established;
- source-aligned Odoo and provider adapters exist in current integration PRs;
- command ledger and Temporal command execution require provider read-back before completion.

The remaining integration question is **runtime binding of each provider according to its real confirmation semantics**, not creation of another adapter/command ledger. Do not force all providers through the same synchronous pattern: Telnexa SMS final delivery truth is asynchronous DLR, while VICIdial and crawler operations have direct state read-back APIs.

Per the mission stage gate, no new provider runtime activation should proceed until Stage 1 live identity acceptance is proven. All provider/business effect flags remain false.

### Stage 3 — Odoo

Odoo `main` has a real Odoo 19 addon/test baseline; the old claim that `custom-addons/` contains only a README is stale. The broader CRM/contact-center business modules required by the mission are still not accepted on `main`, so the Stage 3 end-to-end lead/consent/restore exit condition remains open.

### Stage 4 — n8n

The canonical N8N source and governance controls exist, but runtime endpoint/credential/editor binding and workflow activation remain intentionally unverified/disabled. The Stage 4 exit still requires a real staging CP workflow through Middleware after Stage 2/3 prerequisites are met.

### Stages 5–9

Provider live command/read-back, Kong/Caddy activation, full staging acceptance and production launch retain their explicit real-runtime gates. Source-ready code is not equivalent to a launched capability.

## Immediate next gate

Do not skip the dependency order. The next mission gate is **Stage 1 live identity acceptance**. Once that is proven, Stage 2 can safely close the remaining provider-runtime binding and then move to Odoo/n8n/provider staging acceptance.

No deployment, GitHub Environment creation, live Caddy reload, provider write, SMS/email delivery, production dialing, unrestricted crawling or production activation is authorized by this document.
