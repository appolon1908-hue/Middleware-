# Gate W0 — Contract decision and baseline

- **Status:** READY_FOR_REVIEW
- **Baseline commit:** `382683958feefce73458ee56a1589092bad632b3`
- **Decision:** Middleware adopts automation v2 (ADR-0001)
- **Live writes changed:** no
- **Deployment changed:** no

## Evidence

- Repository settings were audited: `main` is unprotected and no rulesets exist.
- The target settings are encoded in `config/repository-governance.v1.json`.
- The exact manual settings procedure is documented.
- The 13-route v2 gap is encoded as strict, expiring conformance waivers.
- A route implemented without removing its waiver fails as stale.
- A missing route without a waiver fails as undocumented.
- `/v1/integrations/n8n/*` is explicitly a deprecated compatibility surface.
- `/v1/commands` remains a separate product/service control-plane API.
- The 23 baseline skips are assigned to disposable integration jobs.

## Exit conditions

- [x] Option A recorded
- [x] Conformance harness present
- [x] Route authority and compatibility policy recorded
- [x] Skipped-test ownership documented
- [ ] PR exact-head and merge-result checks green
- [ ] GitHub settings applied and live audit green
- [ ] Tag `w0-complete`

The final two items require GitHub administrative settings access and a green
merge. No runtime or production change is part of W0.
