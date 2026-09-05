# Middleware runtime source authority

## Canonical rule

The only forward-looking source authority is protected `main` in
`appolon1908-hue/Middleware-`. A static SHA stored in repository metadata is not
an authority because it becomes stale as soon as another protected merge lands.
Every release or certification workflow must instead resolve the exact GitHub
event SHA for protected `main` and bind that immutable source to the generated
release manifest, source tree, image digest, provenance, SBOM, vulnerability
evidence, migration head, and runtime profile.

The only forward image repository is:

```text
ghcr.io/appolon1908-hue/codestra-middleware
```

`config/runtime-source-state.json` is the machine-readable authority declaration.
It deliberately does not claim that any runtime is deployed or certified.

## Runtime truth

Repository source and runtime state are separate facts. Runtime truth exists only
when `.github/workflows/production-runtime-certification.yml`, under issue #118,
produces and verifies evidence for the exact signed candidate. That evidence must
include effective source/digest/schema/profile read-back, fail-closed capability
read-back, backup plus isolated restore, rollback rehearsal, data integrity, and
zero external-effect movement.

The signed release path is:

1. `.github/workflows/release.yml` — build, scan, sign, and bind the release
   manifest to exact protected source;
2. `.github/workflows/automated-production-promotion.yml` — automated admission
   of that exact signed candidate without enabling business effects;
3. `.github/workflows/production-runtime-certification.yml` — restricted,
   internal-only production read-only canary and immutable runtime evidence.

The manifest schema is `contracts/release-manifest.v1.schema.json`; locked runtime
profiles are registered in `config/runtime-profiles.v1.json`.

## Codestra-SRL rollback authority

`Codestra-SRL/codestra-middleware` is no longer a forward development or release
authority. Its Git history and every currently observed Server A image derived
from it are rollback-only evidence. They must not be deleted, rebuilt as new
forward releases, force-pushed, or used to expand the runtime fleet.

The reconciled, per-image-family record is:

```text
config/middleware-authority-convergence.v1.json
```

That record distinguishes registry manifest digests from Server A-only Docker
image IDs. Registry-addressable Codestra-SRL images are copied without rebuilding
to `ghcr.io/appolon1908-hue/codestra-middleware-legacy`; local-only images require
host-side archive and OCI-config-digest evidence. Neither backup path changes a
container, Compose project, route, queue, database, or provider capability.

The current appolon image and the legacy worker images are not byte-identical.
Consequently, a WebSocket-style namespace-only substitution is not valid for the
Middleware fleet. The stale appolon API may be replaced by a current signed
appolon read-only canary after exact evidence. Legacy APIs and workers must be
retired one family at a time after command, route, data, queue, idempotency,
unknown-outcome, health, readiness, and rollback parity are certified.

See `docs/production/MIDDLEWARE-AUTHORITY-CONVERGENCE.md` for the protected order
of operations and the exact September 4, 2026 comparison.

## Historical evidence

`MIDDLEWARE-AUTHORITY-RECONCILIATION.yaml` and
`docs/SERVER-RUNTIME-RECONCILIATION-MAP.md` remain observed snapshots of the
source and server reconciliation that led to the current model. Their pinned
SHAs, image digests, container counts, or comparison classifications must never
be used as permanent source authority or as proof of current runtime state.

Before any host change, all observed values must be re-read from Server A and
matched to the exact signed candidate and retained rollback evidence.

## Fail-closed boundary

This authority declaration does not approve a deployment, public route, provider
binding, credential, production write, Odoo/n8n effect, email, SMS, social
publication, crawler effect, external-model call, PSTN call, payment, or trading
action. All such capabilities remain disabled unless a separate, exact-candidate
activation release satisfies its own protected approvals and evidence gates.
