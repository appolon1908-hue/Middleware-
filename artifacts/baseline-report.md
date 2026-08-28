# Middleware production-readiness baseline

Captured on 2026-08-28 before production-foundation changes. This report describes the exact `main` source at the baseline SHA. Results from unavailable infrastructure are marked `NOT VERIFIED`; a skipped test is never counted as a pass.

## Baseline identity

```text
BASELINE_SHA=844d13c7ba808653a7d982c63353bc67cdc9adef
CURRENT_BRANCH=main
WORKTREE_STATUS=CLEAN
PYTHON_VERSION=3.12.5 (local host); 3.13 (GitHub Actions)
PACKAGE_MANAGER_VERSION=pip 24.3.1 (host); pip 24.2 (isolated venv bootstrap)
DOCKER_VERSION=NOT AVAILABLE LOCALLY
COMPOSE_VERSION=NOT AVAILABLE LOCALLY
MIGRATION_HEAD=0003_immutable_event_ledger (Middleware SQL); 20260828_0004 (Connector Alembic)
CURRENT_TEST_COUNTS=111 passed, 23 skipped, 11 subtests passed locally
CURRENT_DEPENDENCY_AUDIT=root runtime/test locks: no known vulnerabilities; Connector installed runtime: no known runtime vulnerabilities after excluding installer-only pip advisories
CURRENT_CONTAINER_BUILD_STATUS=PASS IN GITHUB ACTIONS FOR EXACT SHA; NOT VERIFIED LOCALLY
```

The local verification environment was created from scratch from the committed lock files, not from the repository's existing `.venv`.

## Source and runtime inventory

| Area | Baseline state | Evidence/status |
| --- | --- | --- |
| API runtime | `app.main:create_app`, served by `Dockerfile.runtime` on port 8080 | Packaged image smoke test passed in exact-SHA CI |
| Outbox worker | `workers/run_outbox.py` | Source and tests exist; no dedicated image or Compose service |
| Temporal worker | `workers/run_temporal.py` | Source and workflow tests exist; no dedicated image or Compose service |
| Connector Runtime | `services/connector-runtime` with Alembic and a Python package | Package is not self-contained; details below |
| PostgreSQL | Root SQL migrations plus Connector Alembic migrations | Disposable CI exists; production role/migration control is incomplete |
| Redis | Used for replay protection | Disposable CI exists; no repository-owned deployment definition |
| NATS JetStream | Canonical durable event transport | Disposable CI exists; no repository-owned application deployment contract |
| Temporal | Durable workflow plane | Time-skipping workflow tests exist; no real multi-process acceptance topology |
| Health | API exposes `/health` and `/ready`; Connector exposes `/healthz` and readiness | No explicit health contract for every required process |

Tracked deployment artifacts at the baseline:

```text
Dockerfile.runtime
```

There is no tracked `deploy/` directory, no tracked Compose file, and no Connector Runtime Dockerfile. Production application topology is therefore not reproducible from this repository.

## Reproducible test evidence

### Local clean-environment run

Command:

```text
python -m pytest -q -ra tests
```

Result:

```text
111 passed
23 skipped
11 subtests passed
1 Starlette TestClient deprecation warning
```

Skipped tests by reason:

| Test class | Skipped | Reason | Baseline status |
| --- | ---: | --- | --- |
| PostgreSQL/Redis and outbox integration | 19 | Disposable PostgreSQL/Redis variables and services were not available locally | NOT VERIFIED LOCALLY |
| NATS JetStream | 2 | Disposable NATS and Docker were not available locally | NOT VERIFIED LOCALLY |
| Temporal | 1 | Temporal test-server gate was not enabled locally | NOT VERIFIED LOCALLY |
| Synthetic acceptance | 1 | Disposable synthetic gate was not enabled locally | NOT VERIFIED LOCALLY |

### Exact-SHA GitHub Actions evidence

The [Middleware CI run](https://github.com/appolon1908-hue/Middleware-/actions/runs/33195243004) for the baseline SHA completed successfully:

| Gate | Result |
| --- | --- |
| Repository/bootstrap validation | 111 passed, 23 skipped, 11 subtests; validation scripts passed |
| PostgreSQL/Redis integration | 19 passed, 4 unrelated suites skipped in that job |
| NATS JetStream | 2 passed, including reconnect coverage |
| Temporal critical workflows | 1 passed using the Temporal test environment |
| Synthetic no-effect acceptance | 1 passed |
| API runtime image build/smoke | PASS |

The synthetic test is not the required distributed acceptance journey. It executes the API, outbox, NATS, and Temporal adapters from one pytest process and does not start the API, outbox worker, Temporal worker, Connector Runtime, and mock provider as independent networked processes.

### Connector Runtime packaging and tests

A clean environment successfully built and installed `services/connector-runtime`, and `import codestra_connector_runtime` passed. Importing the real API from outside the repository failed:

```text
ModuleNotFoundError: No module named 'middleware'
```

Non-PostgreSQL Connector test collection without a repository-root `PYTHONPATH` also failed with two collection errors for the same missing `middleware.connector_sdk` package. PostgreSQL Connector tests were not run locally because PostgreSQL and Docker were unavailable.

This confirms that Connector Runtime is not independently installable even though its top-level package can be imported.

## Dependency hygiene

- Root API/runtime requirements and test requirements are hash-locked. `pip check` passed in an isolated environment.
- `pip-audit` reported no known vulnerabilities in either committed root lock.
- Connector Runtime pins direct dependencies in `pyproject.toml` but has no deterministic transitive lock.
- Installing Connector Runtime into the root runtime environment replaced the root-locked Pydantic/Pydantic Settings/Uvicorn versions. The runtime boundaries are therefore incompatible when co-installed and must remain separate or be reconciled explicitly.
- Connector audit found no known runtime dependency vulnerability. The environment's bootstrap `pip 24.2` produced seven installer advisories; `pip` is not a declared production runtime dependency. The private Connector package itself cannot be looked up on PyPI and was skipped by the advisory service.

## Database and migration controls

- Middleware migrations record only a version and name in `middleware_schema_migrations`; they do not record a checksum, applied source SHA, or an advisory migration lock.
- Connector Alembic head is `20260828_0004`.
- Connector CI uses `DATABASE_URL`, `ADMIN_DATABASE_URL`, and `APP_DATABASE_URL`, and both Connector workflows inject repository-root `PYTHONPATH` values.
- Connector Alembic falls back to the URL in `alembic.ini` when `DATABASE_URL` is absent instead of failing closed.
- Production database roles and grants are not defined as one version-controlled production provisioning contract.
- Concurrent migration and changed-checksum rejection are not tested.

## Security and release controls

| Control | Baseline result |
| --- | --- |
| Fail-closed capability defaults | PASS: registry defaults to deny and committed live-effect flags remain disabled |
| Release-bound capability activation | NOT IMPLEMENTED |
| Root dependency audit | PASS |
| Connector dependency audit | PASS with the private package itself unauditable by PyPI |
| Dedicated secret scanner | NOT IMPLEMENTED; a limited local pattern scan found no obvious assignment-style secret |
| SAST | NOT IMPLEMENTED |
| Container vulnerability scan | PASS for exact baseline image in remote release workflow |
| SBOM/provenance/signing | PASS for exact baseline image in remote release workflow |
| Scan-before-push policy | FAIL: the workflow pushes the image before SBOM generation and vulnerability scanning |
| Production secrets in tracked Compose | No tracked Compose exists; production configuration is not reproducible |

The [signed release run](https://github.com/appolon1908-hue/Middleware-/actions/runs/33195301067) built, pushed, generated an SPDX SBOM, scanned, signed, verified, and preserved evidence for the exact SHA. Its ordering remains unsafe because publication occurs before the vulnerability gate.

## Webhook ingress findings at the baseline

The baseline source confirms the production blockers under active repair:

1. Webhook bodies are read before the configured maximum is enforced, allowing memory pressure before a 413 response.
2. First delivery of the same event ID is not claimed atomically, so concurrent inserts can surface as 500.
3. Semantic conflicts can leave encrypted payload files behind.
4. `maximum_management_body_bytes` is declared but not enforced before FastAPI parses management JSON.

These are baseline failures even though repair PR #26 exists; unmerged code is not credited to `main`.

## Capability activation baseline

The current static capability registry is fail-closed, which is safe. It is not an operational production activation system: it does not jointly bind environment, tenant, connector, command, immutable source SHA, image digest, signed activation manifest, expiration, approver, and emergency kill switch. No real provider capability was enabled during this baseline.

## CI/CD and source control baseline

- Five workflow files exist: Middleware CI, Connector Runtime API, Connector SDK, Connector Storage, and release.
- Workflow push triggers target `main`; they do not establish `develop` and `staging` promotion gates.
- At capture time, neither `develop` nor `staging` existed remotely.
- The `main` branch protection endpoint returned 404, so required review/check enforcement is not configured there.
- The repository has at least 100 remote branches and 11 open pull requests.
- Several PRs are stacked on feature branches rather than an integration baseline:
  - PR #23 targets `feat/connector-storage-v1`.
  - PR #22 targets `feat/connector-sdk-v1`.
  - PR #19 targets `architecture/codestra-integration-fabric-v2`.
  - PR #17 targets `integration/n8n-control-plane-v2-20260827`.
  - PR #18 targets `integration/codestra-business-scrapper`.
  - PR #21 targets `feat/identity-account-events-v1`.
- PRs #5, #12, #13, #14, and #26 target `main` directly.

## P0 blockers discovered

1. No reproducible application deployment contract or complete runtime topology.
2. Root and Connector dependency boundaries are not deterministically compatible.
3. Connector Runtime is not self-contained and depends on repository-root imports.
4. Connector database CI uses multiple competing database variables and import-path injection.
5. Capability activation is static and not release-bound.
6. Webhook and management ingress have bounded-read, concurrency, and cleanup defects.
7. Migration execution lacks advisory locking, checksum/source identity, and explicit production role ownership.
8. The acceptance test does not prove the real distributed process topology or recovery matrix.
9. Release publication occurs before the vulnerability gate.

## Baseline conclusion

```text
MILESTONE=0
STATUS=PASS
BASE_SHA=844d13c7ba808653a7d982c63353bc67cdc9adef
FINAL_SHA=NOT COMMITTED YET
BRANCH=fix/01-production-foundation
REMOTE_PUSHED=NO
PR=NOT OPENED YET
FILES_CHANGED=artifacts/baseline-report.md
IMPLEMENTED=Reproducible source, test, dependency, CI, migration, packaging, deployment, security, branch, and PR baseline
UNIT=111 PASSED
POSTGRES=19 PASSED IN EXACT-SHA REMOTE CI; NOT VERIFIED LOCALLY
REDIS=PASS IN EXACT-SHA REMOTE CI; NOT VERIFIED LOCALLY
NATS=2 PASSED IN EXACT-SHA REMOTE CI; NOT VERIFIED LOCALLY
TEMPORAL=1 PASSED IN EXACT-SHA REMOTE CI; NOT VERIFIED LOCALLY
CONNECTOR=BLOCKED: NOT SELF-CONTAINED; POSTGRES TESTS NOT VERIFIED LOCALLY
MIGRATIONS=HEADS IDENTIFIED; LOCK/CHECKSUM/CONCURRENCY NOT VERIFIED
DISTRIBUTED_E2E=NOT VERIFIED
DEPENDENCY_AUDIT=PASS WITH DOCUMENTED CONNECTOR/PIP LIMITATIONS
SECRET_SCAN=NOT VERIFIED (NO DEDICATED SCANNER)
SAST=NOT VERIFIED
CONTAINER_SCAN=PASS IN EXACT-SHA REMOTE RELEASE; UNSAFE POST-PUSH ORDER
DOCKER_BUILD=PASS IN EXACT-SHA REMOTE CI; NOT VERIFIED LOCALLY
CONTAINER_START=API SMOKE PASS IN EXACT-SHA REMOTE CI; OTHER RUNTIMES NOT VERIFIED
HEALTH_CHECK=API CONSTRUCTION PASS; COMPLETE TOPOLOGY NOT VERIFIED
KNOWN_LIMITATIONS=No local Docker/PostgreSQL/Redis/NATS/Temporal; Connector package failure; no real distributed E2E
LIVE_EXTERNAL_EFFECTS=DISABLED
NEXT_MILESTONE=1 — production/deployment ownership and reproducible application composition
```
