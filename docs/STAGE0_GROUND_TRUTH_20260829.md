# Codestra CRM/Telephony/Messaging Stage 0 Ground Truth

Date: 2026-08-29

Scope: Middleware, Odoo, Keycloak, N8N, Kong, Telnexa, Klyrow, Kyqra, VICIdial/Asterisk and provisioning. This document replaces the mission plan's unknown/unaudited assumptions with repository-backed source status. It does not claim that source-ready code is deployed or production-ready.

## Permanent architecture boundary

```text
                       Keycloak
                          |
                          v
                         Kong
                          |
                    Caddy/API edge
                          |
                          v
                     Middleware
       +------------------+-------------------+
       |                  |                   |
       v                  v                   v
Vicidialer-Codestra   Telnexa/Jasmin     Klyrow/Email
       |                                      |
       v                                      v
VICIdial/Asterisk                         Postal/Mautic
       |
       +------------------> Odoo <----------------+
                              ^
                              |
                             n8n
                     orchestration only
```

- Middleware is the only cross-system write/control authority.
- Telnexa/Jasmin is SMS, not voice.
- VICIdial/Asterisk is voice/contact-center; the actual VICIdial-specific bridge is owned by `Vicidialer-Codestra`.
- Klyrow is email/customer communications.
- n8n orchestrates only through Middleware and may not call providers/Odoo directly.
- Keycloak supplies machine/user identity; Kong gates ingress; Middleware revalidates privileged authorization.

## 1. Keycloak audit

Repository: `appolon1908-hue/Keycloak`

### README claims vs source

The README accurately describes a GitOps identity repository with canonical issuer `https://auth.codestra.co/realms/codestra`, confidential machine service accounts, short-lived Client Credentials tokens, protected check/drift-review/apply separation, no secrets in Git and exact-source/merge-result CI.

The source contains protected machine clients including `kong-gateway`, `middleware-api`, `middleware-worker`, `odoo-integration`, `n8n-automation`, `vicidial-adapter`, `telnexa-gateway`, `klyrow-gateway`, `kyqra-gateway`, `postly-adapter`, `provisioning-service` and `monitoring-readonly`.

### CI/tests

CI is present and substantial: exact source/merge validation, runtime preflight, drift review and protected deploy workflows. The current Keycloak/Kong OIDC alignment work is in PR #21 and has green exact-source and merge-result validation.

### TODO/stub search

Repository-wide code search found no tracked `TODO` or `NotImplemented` hits in the audited source set. This is not proof that every runtime integration is complete.

### Latest substantive source

Main includes the protected machine-service rollout (`49d33b68a1ebf7c9de97049597583fe30a49a3ce`). PR #21 adds the reviewed N8N -> Middleware command/read scopes and Kong trust contract.

### Stage status

SOURCE_IDENTITY_FOUNDATION=STRONG
LIVE_TOKEN_ACCEPTANCE_EVIDENCE=NOT_PROVEN_BY_STAGE0
STAGE1_EXIT=NOT_YET_PROVEN

Do not call Stage 1 complete until a live Client Credentials token is issued by `auth.codestra.co`, accepted by the reviewed Kong route and rejected when invalid.

---

## 2. N8N audit

Repository: `appolon1908-hue/N8N`

### README claims vs source

The README accurately identifies this as the canonical governed n8n workflow repository. It explicitly keeps runtime paths, deployed endpoint binding, credentials/editor policy and workflow activation unverified/disabled until evidence exists. It prohibits direct access to Odoo, VICIdial, Jasmin/Telnexa, Klyrow/Postal, Kyqra, databases, Keycloak admin and Kong admin.

### CI/tests

Permanent CI and a deployment-preflight workflow are present. Policy, workflow, secret, contract and runtime validations are implemented. Current Stage-4/N8N control-plane integration work is separately reviewed in PR #17; it remains inactive and fail-closed.

### TODO/stub search

Repository-wide code search found no tracked `TODO` or `NotImplemented` hits in the audited source set.

### Latest substantive source

Main currently includes recurring-recovery and runtime-governance work, with latest reviewed merge `1bcf8a4aa9eebc8777a1af477da73ff6a9b5c6f3`.

### Stage status

CANONICAL_REPO=YES
WORKFLOW_GOVERNANCE=IMPLEMENTED
RUNTIME_BINDING=UNVERIFIED
WORKFLOWS_ACTIVE_IN_GIT=NO
STAGE4_EXIT=NOT_YET_PROVEN

The Stage 4 exit still requires a real staging workflow through Middleware and expected Odoo state change after Stage 2/3 prerequisites are accepted.

---

## 3. Telnexa audit

Repository: `appolon1908-hue/telnexa`

### README claims vs source

The README describes a production-oriented Jasmin SMS gateway with HTTP/SMPP, signed MO/DLR/failure callback relay, Redis/RabbitMQ, billing/wallet/ledger state, backup/restore and safe provider onboarding. This is substantive backend/runtime code, not a website scaffold.

Telnexa is explicitly SMS-only in the platform authority model. It is not the VICIdial/Asterisk voice system.

### CI/tests

`.github/workflows/ci.yml` exists and runs formatting/lint, the full pytest suite, dependency audit, Compose validation, non-root image build and Gitleaks scanning. Recent main history includes exact-head quality gates and SMS production-readiness hardening.

### TODO/stub search

Repository-wide code search found no tracked `TODO` or `NotImplemented` hits in the audited source set.

### Latest substantive source

Main head includes PR #12, `79f2a2ff84aad6a5857d2ef15fcd472f1575dae4`, "Harden Telnexa SMS API and canonical identity".

### Stage status

BACKEND_RUNTIME_IMPLEMENTED=YES
SMS_PRODUCTION_DELIVERY=DISABLED_BY_SOURCE_POLICY
REAL_CARRIER_ROUTE_CREDENTIAL_EVIDENCE=NOT_PROVEN_BY_STAGE0
STAGE5_TELNEXA_EXIT=NOT_YET_PROVEN

---

## 4. Klyrow audit

Repository: `appolon1908-hue/klyrow.com`

### README claims vs source

The README accurately describes a tenant-isolated email/customer-communications platform built around Postal, Mautic and a FastAPI gateway with delivery submission, domain onboarding, suppressions, webhook verification, safe mode, operations and SaaS features.

Production sending is intentionally gated by `KLYROW_SAFE_MODE` plus an independent production approval gate.

### CI/tests

`.github/workflows/ci.yml` is present. Recent main history contains security, SMTP, payload-encryption and CI-hardening commits rather than only scaffolding.

### TODO/stub search

Repository-wide code search found no tracked `TODO` or `NotImplemented` hits in the audited source set.

### Latest substantive source

Main includes PR #38 at `ee0612a17b910148090ff9e342c7bb92aeac867f`, hardening Keycloak SECURITY SMTP payload handling.

### Stage status

BACKEND_RUNTIME_IMPLEMENTED=YES
PRODUCTION_SENDING_LAUNCH_GATED=YES
REAL_END_TO_END_MIDDLEWARE_READBACK=NOT_PROVEN_BY_STAGE0
STAGE5_KLYROW_EXIT=NOT_YET_PROVEN

---

## 5. Codestra provisioning-service audit

Repository: `appolon1908-hue/codestra-provisioning-service`

### README claims vs source

The service is explicitly private and staging-only. It implements identity/access provisioning orchestration for Odoo, Keycloak, VICIdial, SIP, Agent Desktop, hosted email, protected credentials, n8n notifications, verification and reconciliation. Provider adapters are disabled until approved endpoints/CA/credential files are installed.

### CI/tests

`.github/workflows/ci.yml` includes ruff, compile, pytest, pip-audit, immutable image build, Gitleaks, Trivy, GHCR publication, SBOM/provenance and Cosign signing/verification under protected release conditions.

### TODO/stub search

Repository-wide code search found no tracked `TODO` or `NotImplemented` hits in the audited source set.

### Latest substantive source

Main head includes PR #9 at `db970edc54207945b7c0bb1547a84b1bdd8905b9`, adding fail-closed production preflight after prior release-signing/governance work.

### Stage status

STAGING_SERVICE_IMPLEMENTED=YES
PRODUCTION_ACTIVATION=NOT_PROVEN
PROVIDER_ADAPTERS_DEFAULT_DISABLED=YES

---

## 6. VICIdial/Asterisk audit

Repository: `appolon1908-hue/Vicidialer-Codestra`

### README claims vs source

This is a substantive dedicated VICIdial integration repository, not just a mapping document. It contains the restricted adapter, campaign provisioning, source/container packaging, tests, release manifests, systemd/operations definitions and reconciliation evidence.

The restricted API contract exposes health/readiness plus campaign, agent, lead, callback, transfer-policy and reconciliation operations with schema validation, idempotency and destination read-back. Newly provisioned campaign resources remain disabled/non-dialing by default.

### CI/tests

Active GitHub Actions validate VICIdial source and containers. Source CI installs the adapter test package, runs `vicidial/tests`, compiles source, scans secrets, rejects runtime artifacts and verifies fail-closed feature flags.

### TODO/stub search

Repository-wide code search found no tracked `TODO` or `NotImplemented` hits in the audited source set.

### Latest substantive source

Main head is `1c84e8bec7e56288adb87c96f292362d33547cff`, completing the dedicated repository migration and separate runnable/attested image validation.

### Stage status

VICIDIAL_CONNECTOR_SOURCE=IMPLEMENTED
VOICE_SYSTEM_AUTHORITY=VICIDIAL_ASTERISK
TELNEXA_USED_AS_VOICE=NO
PRODUCTION_DIALING_ENABLED=NO
STAGE5_VICIDIAL_EXIT=NOT_YET_PROVEN

---

## 7. Kyqra repository resolution

Decision:

```text
CANONICAL_CRAWLER_REPOSITORY=appolon1908-hue/kyqra-crawler
LEGACY_REPOSITORY=appolon1908-hue/kyqra
```

Evidence:

- `kyqra` is a small legacy Docker crawler shell describing planned Crawlee/Playwright/Redis/API/dashboard services.
- `kyqra-crawler` contains a substantive production-oriented Fastify/BullMQ/Redis/PostgreSQL crawler, job API, allowlisted signed callbacks, retention, backup/restore and operations.
- `scrapper` PR #14 had already designated `kyqra-crawler` as the canonical future crawler-fabric repository and prohibited a competing runtime.

Stage 0 documentation PRs now mark `kyqra` legacy and `kyqra-crawler` canonical. This does not move live traffic.

---

## 8. Telnexa backend/frontend repository resolution

Decision:

```text
appolon1908-hue/telnexa      = SMS/backend/runtime authority
appolon1908-hue/Telnexa-web  = public website/service-onboarding frontend authority
```

They are complementary repositories, not competing products. The website calls the governed Middleware boundary; the backend owns Jasmin/SMPP, billing and SMS provider operations. VICIdial voice remains separate.

Stage 0 documentation branches now record this split in both READMEs.

---

## 9. Klyrow backend/frontend repository resolution

Decision:

```text
appolon1908-hue/klyrow.com       = email/SaaS backend/runtime authority
appolon1908-hue/klyrow-Website-  = public marketing website frontend authority
```

`klyrow-Website-` explicitly says its application implementation/main release baseline is not complete and public production is inactive. It must not duplicate Postal/Mautic, tenant state, email queues or credentials from `klyrow.com`.

Stage 0 documentation branches now record this split in both READMEs.

---

## 10. Scrapper deployment truth

Repository: `appolon1908-hue/scrapper`

The main README was previously only a placeholder. The repository's open production/hardening PRs explicitly report `STAGING_DEPLOYED=NO`, `PRODUCTION_DEPLOYED=NO`, `LIVE_SERVER_CHANGED=NO` and `GO_LIVE=NO_GO`. Therefore Stage 0 records:

```text
SCRAPPER_SOURCE_DEVELOPMENT=ACTIVE
SCRAPPER_STAGING_DEPLOYMENT=NO_EVIDENCE
SCRAPPER_PRODUCTION_DEPLOYMENT=NO_EVIDENCE
CANONICAL_FUTURE_CRAWLER=appolon1908-hue/kyqra-crawler
```

A documentation branch updates the README with this release truth and canonical handoff. Source CI or production-oriented Docker/Kong/Caddy files are not deployment evidence.

---

## 11. SDK-repository vs Middleware connector framework

Decision: do not delete either repository.

```text
SDK-repository
  = developer-facing contracts, generated SDKs, webhook helpers,
    @codestra/connector-kit, n8n nodes, distributable integration tooling

Middleware-/middleware/connector_sdk + services/connector-runtime
  = privileged runtime enforcement, trusted registry, durable state,
    secret resolution, provider execution, read-back/reconciliation and activation
```

The overlap to eliminate is duplicated hand-maintained **contract definitions**, not the privileged Middleware runtime. Public SDK artifacts should be generated/versioned against canonical contracts and checked for drift.

A permanent ownership note is added in both repositories.

---

## 12. Caddy edge ownership

Stage 0 found no single canonical repository for the shared Caddy API edge. Existing material is fragmented:

- historical Server A/private VICIdial ingress Caddy evidence exists in `appolon1908-hue/codestra-production-platform`;
- product repositories include product-specific web/Caddy templates;
- Kong owns the shared API gateway, route/security policy and Caddy/Kong validation concerns.

Decision:

```text
SHARED_API_EDGE_CADDY_SOURCE_AUTHORITY=appolon1908-hue/Kong
CANONICAL_FUTURE_PATH=deploy/caddy/
HISTORICAL_RUNTIME_EVIDENCE=appolon1908-hue/codestra-production-platform
```

This is source ownership only. No live Caddy file is changed. Runtime convergence requires read-only inventory, checksum parity, staging Caddy->Kong validation, rollback rehearsal and immutable deployment.

---

## Stage 0 exit verdict

The repository-authority unknowns in the mission plan are resolved in source:

```text
KEYCLOAK_AUDITED=YES
N8N_AUDITED=YES
TELNEXA_AUDITED=YES
KLYROW_AUDITED=YES
PROVISIONING_AUDITED=YES
VICIDIAL_AUDITED=YES
KYQRA_DUPLICATE_RESOLVED=YES
TELNEXA_WEB_SPLIT_RESOLVED=YES
KLYROW_WEB_SPLIT_RESOLVED=YES
SCRAPPER_DEPLOYMENT_TRUTH_RECORDED=YES
SDK_CONNECTOR_OWNERSHIP_RESOLVED=YES
CADDY_SOURCE_OWNER_ASSIGNED=YES
LIVE_RUNTIME_CHANGED=NO
PRODUCTION_ACTIVATED=NO
```

Stage 0 is complete at the **repository/source-authority level** after these documentation PRs merge. Stages 1–9 retain their live/read-back/rehearsal exit conditions; this document does not waive them.
