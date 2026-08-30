# Step 3 Email Test Evidence

Date: 2026-08-30

## Focused email contract evidence

Executed with the repository's locked Python 3.13 test environment:

```text
python -m pytest tests/test_communications_email.py -q
6 passed, 14 warnings
```

The focused suite covers:

- canonical email command acceptance and sender authorization;
- strict tenant isolation and the `EMAIL_DELIVERY` kill switch;
- idempotent command replay with exactly one communications message and one command operation;
- signed Klyrow delivery callbacks, exact replay acceptance, and conflicting replay rejection;
- unknown provider outcomes surfaced as `indeterminate` without creating a second command;
- suppression and provider-event state transitions.

## Source-head validation

Executed with Python 3.13 through the same entry point used by Middleware CI:

```text
bash scripts/run_ci.sh
164 passed, 23 skipped, 25 warnings, 11 subtests passed
RUNTIME_CONTRACT_ROUTES=PASS
PROJECT_SPECIFIC_CI=PASS
```

All repository, workstream, connectivity, identity, n8n, site, intake, and project-specific source validators passed.

## Temporal uncertain-outcome evidence

Executed against the pinned Temporal test-server environment:

```text
bash scripts/temporal_integration_ci.sh
1 passed
TEMPORAL_EMAIL_UNKNOWN_OUTCOME_NO_RETRY=PASS
```

The workflow test injects a possible-after-acceptance provider timeout, records `reconciliation_required`, and proves there is exactly one provider execution attempt. It does not retry or mark the command completed while the outcome is uncertain.

## Remaining CI evidence boundary

The PostgreSQL/Redis, NATS JetStream, synthetic no-effect, runtime Docker, and test-target Docker validations require disposable services or pinned images. Their authoritative results are the exact-head and merge-result checks on PR #52. A local Docker registry authentication failure prevented pulling the pinned NATS image; no weaker image or simulated pass was substituted.

Step 3 is complete only when every required GitHub check is green at the pushed head and merge result.
