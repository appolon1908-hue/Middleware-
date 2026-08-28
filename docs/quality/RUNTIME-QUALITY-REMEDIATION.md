# Runtime quality remediation

## Scope and frozen baseline

- Base: `fbba7e29eab1566147efdc62036ea979de1a8690`
- Ruff: 16 findings from `ruff check .`
- mypy core: 62 errors from the Python 3.13 core/test dependency environment
- mypy Connector Runtime: 7 errors from its independent Python 3.13 dependency environment
- Intended behavior change: none

Core and Connector Runtime are checked separately because their independently
locked FastAPI and Pydantic dependency sets intentionally differ. The root
`mypy .` command checks core application code, workers, SDK code, architecture,
scripts, and tests. CI separately checks `services/connector-runtime/src` and
`services/connector-runtime/tests` with the Connector Runtime lock.

## Ruff findings

| File | Line | Tool/rule | Classification | Fix | Behavior change |
| --- | ---: | --- | --- | --- | --- |
| `app/temporal_activities.py` | 9 | Ruff F401 | DEAD_CODE | Removed unused `CommandState` import. | NO |
| `scripts/audit_all_workstream_sync.py` | 15 | Ruff E402 | IMPORT_STRUCTURE | Replaced the post-path-mutation import with explicit dynamic module loading. | NO |
| `scripts/validate_site_routes_and_leads.py` | 15 | Ruff E402 | IMPORT_STRUCTURE | Replaced the post-path-mutation import with explicit dynamic module loading. | NO |
| `scripts/validate_site_workstreams.py` | 15 | Ruff E402 | IMPORT_STRUCTURE | Replaced the post-path-mutation import with explicit dynamic module loading. | NO |
| `scripts/verify_event_ledger.py` | 15 | Ruff E402 | IMPORT_STRUCTURE | Moved the application import into the command function after path setup. | NO |
| `services/connector-runtime/src/codestra_connector_runtime/api/app.py` | 5 | Ruff F401 | DEAD_CODE | Removed unused `json`. | NO |
| `services/connector-runtime/src/codestra_connector_runtime/api/app.py` | 12 | Ruff F401 | DEAD_CODE | Removed unused `Response`. | NO |
| `services/connector-runtime/src/codestra_connector_runtime/api/app.py` | 20 | Ruff F401 | DEAD_CODE | Removed unused `manifest_digest`. | NO |
| `services/connector-runtime/src/codestra_connector_runtime/api/app.py` | 21 | Ruff F401 | DEAD_CODE | Removed unused `parse_manifest`. | NO |
| `services/connector-runtime/src/codestra_connector_runtime/api/repository.py` | 8 | Ruff F401 | DEAD_CODE | Removed unused `datetime`. | NO |
| `services/connector-runtime/src/codestra_connector_runtime/api/repository.py` | 8 | Ruff F401 | DEAD_CODE | Removed unused `timezone`. | NO |
| `services/connector-runtime/src/codestra_connector_runtime/api/repository.py` | 9 | Ruff F401 | DEAD_CODE | Removed unused `Callable`. | NO |
| `services/connector-runtime/src/codestra_connector_runtime/api/repository.py` | 12 | Ruff F401 | DEAD_CODE | Removed unused `Connection`. | NO |
| `services/connector-runtime/tests/test_api_helpers.py` | 4 | Ruff F401 | DEAD_CODE | Removed unused `json`. | NO |
| `services/connector-runtime/tests/test_management_api.py` | 3 | Ruff F401 | DEAD_CODE | Removed unused `copy`. | NO |
| `tests/test_connector_sdk_review_findings.py` | 12 | Ruff F401 | DEAD_CODE | Removed unused `Mapping`. | NO |

## mypy findings

Repeated findings with the same cause and correction are grouped below; the
count column accounts for every reported error.

| File | Original line(s) | Count | Rule | Classification | Fix | Behavior change |
| --- | --- | ---: | --- | --- | --- | --- |
| `architecture/site_architecture.py` | 249 | 1 | dict-item | TYPE_MODEL_DEFECT | Added the concrete `STACKS` tuple/mapping type. | NO |
| `scripts/validate_site_workstreams.py` | 179–180 | 2 | arg-type | TYPE_MODEL_DEFECT | Constructed validated string mappings explicitly. | NO |
| `scripts/validate_identity_webhook_contracts.py` | 225–452 | 18 | union-attr, arg-type, operator | OPTIONAL_NONE_HANDLING | Declared the always-raising validation helper as `NoReturn`, preserving existing fail-closed flow narrowing. | NO |
| `scripts/validate_connectivity_contracts.py` | 444–457 | 3 | assignment, index | TYPE_MODEL_DEFECT | Gave the later expected-link tuple a distinct variable name. | NO |
| `scripts/validate_connector_sdk.py` | 304–305 | 2 | misc | TYPE_MODEL_DEFECT | Avoided reusing an exception target after Python deletes it. | NO |
| `app/commands.py`, `app/storage.py`, `workers/run_outbox.py`, `scripts/migrate_runtime.py`, `scripts/verify_event_ledger.py`, `tests/integration/test_postgres_redis.py`, `tests/integration/test_outbox_dispatch_lease.py`, `tests/integration/test_synthetic_acceptance.py` | imports | 8 | import-untyped | FALSE_POSITIVE | Added a module-limited asyncpg missing-stub exception; all consuming application code remains checked. | NO |
| `app/commands.py` | 679 | 1 | var-annotated | TYPE_MODEL_DEFECT | Typed the table-to-column-set mapping. | NO |
| `app/worker.py` | 131 | 2 | var-annotated, arg-type | ASYNC_CORRECTNESS | Modeled handlers as coroutine functions and the created task as `Task[None]`. | NO |
| `app/replay.py` | 93 | 1 | misc | ASYNC_CORRECTNESS | Narrowed the async Redis `eval` result to its awaitable interface. | NO |
| `app/main.py` | 380 | 1 | assignment | OPTIONAL_NONE_HANDLING | Declared the module application as `FastAPI | None` for fail-closed configuration. | NO |
| `workers/run_outbox.py` | 48 | 1 | arg-type | TYPE_MODEL_DEFECT | Typed the handler registry with the canonical handler alias. | NO |
| `scripts/staging_synthetic_acceptance.py` | 194 | 1 | return-value | TYPE_MODEL_DEFECT | Typed event and header mappings at construction. | NO |
| `tests/test_connector_sdk_v1.py` | 93, 264, 491, 599, 617 | 5 | dict-item, union-attr, arg-type | TEST_ONLY | Added result mapping types, explicit non-null assertions, and a real argparse namespace fixture. | NO |
| `tests/test_connector_sdk_review_findings.py` | 197 | 1 | union-attr | TEST_ONLY | Added an explicit non-null assertion. | NO |
| `tests/test_worker.py` | 15–19, 122–123 | 7 | var-annotated, index | TEST_ONLY | Typed recorded calls and narrowed optional claim arguments. | NO |
| `tests/integration/test_postgres_redis.py` | 87 | 1 | misc | TEST_ONLY | Declared async fixtures as `AsyncIterator`. | NO |
| `tests/test_runtime.py` | 22–26 | 3 | attr-defined | TEST_ONLY | Narrowed routes to `APIRoute` before reading route-specific fields. | NO |
| `tests/integration/test_synthetic_acceptance.py` | 157–162, 279 | 4 | dict-item, index | TEST_ONLY | Typed event/header mappings and asserted NATS headers are present. | NO |
| `services/connector-runtime/tests/test_api_helpers.py` | 62–96 | 7 | arg-type, call-arg | TEST_ONLY | Used `SecretStr` inputs and a typed environment-backed settings factory. | NO |

## Suppression register

One narrow external-library suppression exists in `mypy.ini`:

- WHY_REQUIRED: `asyncpg` publishes neither a `py.typed` marker nor a maintained
  stub distribution, so mypy reports the installed library itself as untyped.
- SCOPE: only `asyncpg` and `asyncpg.*` imports.
- REMOVAL_CONDITION: remove when asyncpg ships usable inline types or an approved
  compatible stub distribution is adopted.

No file-level `type: ignore`, `noqa`, global error ignore, or disabled type-checking
mode was added.

## Production blockers kept outside this PR

The approved production blockers are tracked in Middleware issues #31 through
#38 and provisioning-service issue #14. They require security or runtime behavior
changes and are intentionally not implemented by this quality-only branch.
