# Server A Middleware authority convergence

## Decision

Protected `main` in `appolon1908-hue/Middleware-` is the only forward source
authority. Images that may be admitted to staging or production must be created
by `.github/workflows/release.yml` from the exact CI-accepted protected-main SHA
and addressed by the resulting immutable GHCR digest.

`Codestra-SRL/codestra-middleware` and every image derived from it are retained
as rollback-only source and image history. They are not deleted, force-pushed,
rebuilt as new forward releases, or allowed to expand their runtime footprint.

This document and `config/middleware-authority-convergence.v1.json` are observed
evidence and a convergence plan. They do not themselves authorize a deployment,
traffic change, provider call, database write, queue consumption, or container
retirement.

## Exact reviewed authorities

The repository comparison was refreshed on September 4, 2026.

| Purpose | Exact reviewed value |
|---|---|
| Forward repository | `appolon1908-hue/Middleware-` |
| Observed protected `main` | `b03b378f3a358de333e37cf6cc7a37668f004b4f` |
| Git tree | `8e9a4be456a2f82ef3352a277f6f76f1a2e18d90` |
| Signed candidate | `ghcr.io/appolon1908-hue/codestra-middleware@sha256:dfdcfb92538242df9c9e81c27f15f9bd14b2cb840ea4c16d91dccc8f0eed7a3c` |
| Release ID | `b03b378f3a35-dfdcfb925382` |
| Release workflow run | `33908027409`, attempt `1` |
| Migration head | `0009_observability_incidents` |
| Legacy source backup | `Codestra-SRL/codestra-middleware@167bd6221911ec3fa988d719eb259646fa90f296` |
| Legacy source tree | `8304f8685f97164775666ecdcfaba5e9e93f3577` |
| Server A | `65.109.65.169` |

The SHA above is an observed signed candidate, not a permanent source pointer.
A later protected merge must produce its own exact signed release. Static SHAs
must never replace the dynamic protected-main event-SHA rule in
`config/runtime-source-state.json`.

## Review and comparison result

The old reconciliation used appolon anchor
`f3437709c06747249586598590145234ea2c7327`. Current protected main is 28
commits ahead and zero behind. The current architecture now includes the
compatibility API, quarantine and reconciliation controls, Klyrow, Postly,
Telnexa and Odoo adapters, provider-control policy, Temporal/outbox execution,
immutable runtime read-back, and signed release evidence.

The old Codestra-SRL comparison used
`2f1c7af41f87c27e2881c3695621ece787b97445`. Current legacy protected main is
three commits ahead and zero behind. The reviewed tip changes add generic
health/readiness/version/capability controls, an external-webhook production
compose definition, Beyvra email compose pin adjustments, and entrypoint tests.
Those changes do not supersede the canonical appolon command, connector,
tenant, idempotency, release, and runtime-safety architecture.

The repositories are not byte-identical releases. Unlike the WebSocket registry
namespace migration, the current appolon Middleware candidate cannot simply be
substituted under every legacy worker command. The legacy images expose several
historical entrypoints, schemas, queues, configuration paths, and source
revisions. A blind whole-fleet image replacement would risk broken commands,
double queue consumption, schema drift, lost unknown-outcome reconciliation,
and unintended external effects.

## What “synced” means

Syncing Middleware means that one canonical contract and release authority owns
all new development while required legacy behavior is moved through explicit,
tested boundaries. It does **not** mean merging the old monolith wholesale.

Already represented in the appolon architecture:

- authenticated `/api/v1` compatibility routes;
- quarantine list, detail, discard, and review controls;
- reconciliation list, detail, and resolution controls;
- signed intake plus durable inbox/outbox and command ledgers;
- Klyrow email/alert, Postly social, Telnexa SMS, and Odoo adapters;
- Temporal workflows, provider-control policy, idempotency, and audit evidence;
- exact source, digest, schema, runtime-profile, capability, SBOM, provenance,
  signature, and vulnerability-gate evidence.

Still requiring per-workload certification before retirement:

- Asterisk/PJSIP connector parity;
- a dedicated Keycloak-validated short-lived webphone session issuer;
- Breero normalization, idempotency, and Odoo read-back parity;
- Kyqra/scraper cursor, replay, idempotency, and Odoo read-back parity;
- queue drain, replay-safe handoff, and unknown-outcome reconciliation;
- database restore, schema migration, route ownership, and rollback proof.

## Server A runtime finding

The September 1 inventory did not show merely two interchangeable images. It
showed one stale appolon API and multiple Codestra-SRL image families serving
different API and worker entrypoints.

The stale appolon runtime is:

```text
container=codestra-appolon-middleware-integration-api-1
source=f6748a58f8d2590520a4f28776770957061cdea1
image=ghcr.io/appolon1908-hue/codestra-middleware@sha256:695fa3ce3f50ba4d0ae0784976b946a0a683ca731155e4bd3bd9e90a4670b820
```

The primary legacy APIs include:

```text
container=codestra-middleware-1
source=b3ca9aa458fef843e3065aeff3397c656349f138
image_id=sha256:5dd751a9da60e2417c9ee553ddea68f54e76981dcc896eb3676b27617d121f38

container=codestra-middleware-integration-api-1
source=35448ef85ae56db3651a72b61db8e242b7aacd2e
image=ghcr.io/codestra-srl/codestra-middleware@sha256:09d4bd0f7b2376e0a06d3efae27a6642429389fa7e3277791ec0b36584e87175
```

The full 31-workload, 16-image-family record is in
`config/middleware-authority-convergence.v1.json`. PostgreSQL, Redis, and the
rehearsal-only certification object are intentionally classified separately and
are not counted as Middleware forward image authorities.

## Backup strategy

Four legacy images already have immutable Codestra-SRL GHCR manifest digests.
`.github/workflows/mirror-codestra-legacy-middleware-images.yml` copies those
manifests and layers without rebuilding them into:

```text
ghcr.io/appolon1908-hue/codestra-middleware-legacy
```

The workflow refuses success unless the destination manifest digest and raw
manifest hash are identical to the source. It produces only secret-free Actions
evidence and does not contact Server A.

Several older Server A images exist only as local image IDs or local tags. On
the host, the read-only identity/backup operator is:

```bash
sudo ./scripts/server-a-backup-legacy-middleware-images.sh status
sudo ./scripts/server-a-backup-legacy-middleware-images.sh archive
sudo ./scripts/server-a-backup-legacy-middleware-images.sh mirror
```

`status` verifies each observed container image ID without reading or printing
container environment values. `archive` creates root-only Docker image archives
and checksum evidence. `mirror` copies a temporary local tag into the appolon
legacy package and proves that the destination OCI config digest equals the
recorded Docker image ID. None of those modes restarts a container, edits a
Compose file, changes traffic, or consumes a queue.

## Protected convergence order

1. Merge this authority record through protected `main` with exact-head CI and
   the required independent approval.
2. Build a new signed candidate from that exact protected merge; do not promote
   the pre-merge `b03b378…` candidate as though it contained this change.
3. Mirror the four exact Codestra-SRL GHCR digests and capture every local-only
   Server A image family before any runtime replacement.
4. Re-read all Server A container source, image, command, Compose, network,
   secret-file path, health, readiness, queue, and schema identities. Stop on
   any mismatch with the September 1 inventory.
5. Create paired PostgreSQL, queue/state, configuration, and image backups and
   prove an isolated restore.
6. Use the existing restricted `codestra-middleware-deploy` operator to admit
   the new appolon digest as a read-only canary. Keep all write, delivery,
   provider, crawler, social, email, SMS, Odoo, n8n, and PSTN controls disabled.
7. Compare exact route contracts, auth/tenant decisions, data reads, latency,
   health, readiness, source/digest/schema/profile read-back, and zero-effect
   counters against both current APIs.
8. Move only reviewed read-only route authority to the appolon canary. Do not
   start a second consumer for any legacy queue.
9. Retire the duplicate legacy API containers only after rollback rehearsal.
10. Migrate each worker image family in a separate protected release after its
    command, state, queue, idempotency, unknown-outcome, and provider-denial
    tests pass.
11. Retain Codestra-SRL source, images, local archives, configuration evidence,
    and exact rollback commands through the approved retention window.

## Current execution status

```text
APPOLON_FORWARD_SOURCE_AUTHORITY=DECLARED
CURRENT_SIGNED_CANDIDATE=VERIFIED
LEGACY_RUNTIME_IMAGE_CATALOG=COMPLETE_FROM_2026-09-01_EVIDENCE
LEGACY_GHCR_MIRROR=AUTOMATION_PREPARED
LOCAL_IMAGE_BACKUP=SERVER_A_ACCESS_REQUIRED
SERVER_A_RUNTIME_REVALIDATION=NOT_EXECUTED
APPOLON_CANARY=NOT_EXECUTED
ROUTE_CUTOVER=NOT_EXECUTED
LEGACY_CONTAINER_RETIREMENT=NOT_EXECUTED
PRODUCTION_CHANGED=NO
CALLS_PLACED=0
```

Server A is not enrolled in the connected server manager, so no host mutation
was attempted while preparing this repository change.

## Independent WebSocket gate

The WebSocket authority work is separate. Its remaining promotion gate is the
unaccepted reviewer invitation followed by protected merge. This Middleware
change neither bypasses nor resolves that gate.
