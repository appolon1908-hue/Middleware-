# Server A Middleware authority convergence

## Decision

Protected `main` in `appolon1908-hue/Middleware-` is the only forward source
authority. Every future Middleware image admitted to staging or production must
be built by `.github/workflows/release.yml` from the exact CI-accepted
protected-main SHA and must be addressed by its immutable GHCR digest.

`Codestra-SRL/codestra-middleware` and every image derived from it are retained
as rollback-only source and image history. They are not deleted, force-pushed,
rebuilt as new forward releases, or allowed to expand their runtime footprint.

This document and `config/middleware-authority-convergence.v1.json` are observed
evidence and a convergence plan. They authorize no deployment, traffic change,
provider call, database write, queue consumption, or container retirement.

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

The appolon SHA above is a verified signed candidate, not a permanent source
pointer. After this authority change merges, the protected merge SHA must
produce a new signed release. The older `b03b378…` artifact must not be promoted
as though it contained the authority change.

## Review and comparison result

The previous reconciliation used appolon anchor
`f3437709c06747249586598590145234ea2c7327`. The reviewed protected main is 28
commits ahead and zero behind. It now includes the compatibility API,
quarantine and reconciliation controls, Klyrow, Postly, Telnexa and Odoo
adapters, provider-control policy, Temporal/outbox execution, immutable runtime
read-back, and signed release evidence.

The previous Codestra-SRL snapshot used
`2f1c7af41f87c27e2881c3695621ece787b97445`. The reviewed legacy protected main
is three commits ahead and zero behind. Its tip adds generic
health/readiness/version/capability controls, an external-webhook production
Compose definition, Beyvra email Compose pin adjustments, and entrypoint tests.
Those changes do not supersede the canonical appolon command, connector,
tenant, idempotency, release, and runtime-safety architecture.

The repositories are divergent architectures, not byte-identical releases.
Unlike the WebSocket namespace migration, one appolon image cannot safely
replace every legacy worker command. A blind replacement could break
entrypoints, double-consume queues, drift schemas, lose unknown-outcome
reconciliation, or enable unintended effects.

## What “synced” means

Middleware is synced when one canonical contract and release authority owns all
new development and every required legacy behavior is ported through an
explicit, tested boundary. It does not mean merging the old monolith wholesale.

Already represented in the appolon architecture:

- authenticated `/api/v1` compatibility routes;
- quarantine list, detail, discard, and review controls;
- reconciliation list, detail, and resolution controls;
- signed intake plus durable inbox, outbox, command, and audit ledgers;
- Klyrow email/alert, Postly social, Telnexa SMS, and Odoo adapters;
- Temporal workflows, provider-control policy, idempotency, and read-back;
- exact source, digest, schema, runtime-profile, capability, SBOM, provenance,
  signature, and vulnerability-gate evidence.

Still requiring per-workload certification before retirement:

- Asterisk/PJSIP connector parity;
- a Keycloak-validated short-lived webphone session issuer;
- Breero normalization, idempotency, and Odoo read-back parity;
- Kyqra/scraper cursor, replay, idempotency, and Odoo read-back parity;
- queue drain, replay-safe handoff, and unknown-outcome reconciliation;
- database restore, schema migration, route ownership, and rollback proof.

## Server A runtime finding

The September 1 inventory did not show two interchangeable Middleware images.
It showed one stale appolon API and multiple Codestra-SRL image families serving
different API and worker entrypoints.

The stale appolon runtime is:

```text
container=codestra-appolon-middleware-integration-api-1
source=f6748a58f8d2590520a4f28776770957061cdea1
image=ghcr.io/appolon1908-hue/codestra-middleware@sha256:695fa3ce3f50ba4d0ae0784976b946a0a683ca731155e4bd3bd9e90a4670b820
```

Two representative legacy APIs are:

```text
container=codestra-middleware-1
source=b3ca9aa458fef843e3065aeff3397c656349f138
image_id=sha256:5dd751a9da60e2417c9ee553ddea68f54e76981dcc896eb3676b27617d121f38

container=codestra-middleware-integration-api-1
source=35448ef85ae56db3651a72b61db8e242b7aacd2e
image=ghcr.io/codestra-srl/codestra-middleware@sha256:09d4bd0f7b2376e0a06d3efae27a6642429389fa7e3277791ec0b36584e87175
```

The complete observed record contains 31 Middleware workloads grouped into 16
image families. PostgreSQL, Redis, and rehearsal-only objects remain separate
from Middleware forward image authority.

## Exact registry backups

Four legacy images have immutable Codestra-SRL GHCR manifest digests. The
manual workflow
`.github/workflows/mirror-codestra-legacy-middleware-images.yml` copies their
manifests and layers without rebuilding them into:

```text
ghcr.io/appolon1908-hue/codestra-middleware-legacy
```

The workflow:

- can run only through `workflow_dispatch` from protected `main`;
- checks out and verifies the exact dispatch SHA;
- requires exactly four reviewed mirror records;
- uses `skopeo --all --preserve-digests`;
- requires the destination manifest digest and raw manifest hash to equal the
  source;
- records `rebuilt=false`, `runtime_promoted=false`, and source retention;
- never contacts Server A.

Codestra-SRL GHCR is private. Before dispatch, repository secret
`CODESTRA_GHCR_TOKEN` must contain a token authorized with `read:packages` for
the legacy package. Optional secret `CODESTRA_GHCR_USER` identifies the token
owner. The appolon repository `GITHUB_TOKEN` is used only for the destination
package.

A preflight on the migration branch proved the catalog and destination
authentication, then failed closed at private source authentication because
`CODESTRA_GHCR_TOKEN` was absent. No image was rebuilt, retagged remotely, or
partially mirrored.

## Server A local-image backups

Eleven image families are identified only by local Docker image IDs or local
tags. After Server A is enrolled, run:

```bash
sudo ./scripts/server-a-backup-legacy-middleware-images.sh status
sudo ./scripts/server-a-backup-legacy-middleware-images.sh archive
sudo ./scripts/server-a-backup-legacy-middleware-images.sh mirror
```

The operator is fail-closed:

- it requires root and verifies that `65.109.65.169` is a local global address;
- it validates the convergence catalog before reading Docker state;
- it fails if any catalogued image, container, or image-ID binding is missing or
  changed;
- it never reads or records container environment values;
- it records only mount destinations, never mount source paths or file
  contents;
- it records hashes of command and entrypoint arrays rather than their values;
- it creates root-only `docker image save` archives with whole-archive SHA-256;
- it verifies archive member safety, single-image structure, layer presence,
  and that the saved config object hashes to the exact Docker image ID;
- it verifies root ownership and restrictive permissions for registry
  credentials;
- it removes temporary local tags on every mirror exit;
- it writes and verifies a checksum manifest for the complete evidence run.

Archive structural verification is not an isolated restore. A separate isolated
`docker load`, application startup, health/readiness check, source/config
read-back, and rollback rehearsal remain mandatory before any cutover.

None of the backup modes restarts or stops a container, edits Compose, changes
traffic, consumes a queue, or enables a provider.

## Protected convergence order

1. Merge this authority record through protected `main` with exact-head CI and
   fresh independent approval.
2. Build and verify a new signed artifact from that exact protected merge SHA.
3. Add `CODESTRA_GHCR_TOKEN` and run the protected-main manual mirror workflow.
4. Enroll Server A and rerun read-only inventory. Stop on any source, image,
   command-hash, Compose, network, mount-destination, health, readiness, queue,
   or schema mismatch.
5. Archive all eleven local-only image families and verify the evidence
   checksum manifest.
6. Create paired PostgreSQL, queue/state, configuration, and image backups and
   prove an isolated restore.
7. Admit the new appolon digest as an isolated read-only canary through the
   restricted `codestra-middleware-deploy` operator. Keep every write,
   delivery, provider, crawler, social, email, SMS, Odoo, n8n, and PSTN control
   disabled.
8. Compare route contracts, auth/tenant decisions, data reads, latency,
   health/readiness, source/digest/schema/profile read-back, and zero-effect
   counters against both existing APIs.
9. Move only reviewed read-only route authority to the appolon canary. Never
   start a second consumer for a legacy queue.
10. Rehearse rollback to the exact captured image/configuration tuple.
11. Retire duplicate legacy APIs to stopped rollback-only state. Migrate each
    worker in a separate protected release after its parity tests pass.
12. Retain Codestra-SRL source, images, archives, configuration evidence, and
    rollback commands through the approved retention window.

## Current execution status

```text
APPOLON_FORWARD_SOURCE_AUTHORITY=DECLARED_IN_PR
CURRENT_SIGNED_CANDIDATE=VERIFIED_PRE_MERGE_ARTIFACT
LEGACY_RUNTIME_IMAGE_CATALOG=COMPLETE_FROM_2026-09-01_EVIDENCE
LEGACY_GHCR_MIRROR_WORKFLOW=PREPARED_MANUAL_PROTECTED_MAIN_ONLY
LEGACY_GHCR_MIRROR_EXECUTION=BLOCKED_CODESTRA_GHCR_TOKEN
LOCAL_IMAGE_BACKUP=BLOCKED_SERVER_A_ENROLLMENT
SERVER_A_RUNTIME_REVALIDATION=NOT_EXECUTED
ISOLATED_RESTORE=NOT_EXECUTED
APPOLON_CANARY=NOT_EXECUTED
ROUTE_CUTOVER=NOT_EXECUTED
LEGACY_CONTAINER_RETIREMENT=NOT_EXECUTED
PRODUCTION_CHANGED=NO
CALLS_PLACED=0
```

Server A is not enrolled in the connected server manager. No host mutation was
attempted while preparing this repository change.

## Independent WebSocket gate

The WebSocket authority work is separate. Its remaining promotion gate is the
reviewer invitation followed by protected merge. This Middleware change neither
bypasses nor resolves that gate.
