# CI, environments, and current handoff

Status snapshot: 2026-08-28

This document is the concise operating reference for source branches, CI,
staging and production promotion, and the next unfinished production work. It
does not authorize a deployment or replace environment-specific evidence.

## Branch and environment model

The repository uses `main` as the only release source branch. Staging and
production are deployment environments, not Git branches. The same immutable
image digest must be accepted in staging and then promoted to production.

| Name | Kind | Current state | Purpose |
|---|---|---|---|
| `main` | release source branch | Present remotely at `0f29b6c`; GitHub protection settings were not available locally | Merged, release-eligible source once required protection is confirmed |
| `integration/system-architecture-alignment` | workstream branch | Current review branch, based on `main` | Integration and production-readiness changes awaiting merge |
| `testing/playwright` | testing workstream branch | Present remotely | Browser test source; not a staging environment |
| `staging` | intended deployment environment | No remote Git branch; GitHub Environment existence was not available locally | Deploy and test an immutable digest with external effects disabled |
| `production` | intended deployment environment | No remote Git branch; GitHub Environment existence was not available locally | Promote the staging-accepted digest after approval |

Do not create `staging` or `production` source branches. Environment-specific
differences belong in protected environment configuration and secret managers,
while source remains identical.

## CI coverage

| Workflow | Pull requests | Push to `main` | Responsibility |
|---|---|---|---|
| `Middleware CI` | Yes | Yes | Repository validators, locked unit tests, runtime-image build/smoke, PostgreSQL/Redis integration, NATS, Temporal, and synthetic no-effect acceptance |
| `Connector SDK v1 validation` | Relevant paths | Relevant paths | Connector manifests, generated artifacts, contracts, and SDK regression tests |
| `Connector storage v1` | Relevant paths | Relevant paths | Alembic migrations, RLS/tenant isolation, concurrency, backup/restore, and downgrade/upgrade |
| `Connector Runtime API validation` | Relevant paths | Relevant paths | Connector management API plus PostgreSQL integration and migration replay |
| `Signed Middleware Release` | No direct trigger | After successful `Middleware CI` on `main` | Build, scan, sign, verify, and preserve immutable release evidence |

The three connector workflows check out the exact pull-request head SHA during
review and the exact `github.sha` after merge to `main`. Connector Runtime CI
provides both `DATABASE_URL` for Alembic and `ADMIN_DATABASE_URL` for its tests.

Recommended protected-branch checks:

- `Validate middleware repository`
- `Build and smoke-test runtime image`
- `Disposable PostgreSQL Redis integration`
- `Disposable NATS JetStream integration`
- `Temporal critical workflow integration`
- `Synthetic no-effect acceptance E2E`
- all connector checks when their paths are changed

GitHub branch protection and GitHub Environments are repository settings and
cannot be proven by workflow YAML. Confirm them in GitHub before merging or
promoting a release.

## Promotion model

```text
workstream pull request
  -> exact-head CI
  -> protected merge to main
  -> exact-main-SHA CI
  -> signed immutable image and release evidence
  -> deploy digest to staging
  -> runtime read-back, synthetic acceptance, backup/restore and rollback proof
  -> explicit production approval
  -> deploy the identical digest to production
```

The attached architecture assigns runtime composition and deployment promotion
to `appolon1908-hue/codestra-production-platform`. This repository produces the
Middleware source and release artifact; production readiness also requires a
separate review of that central deployment repository.

## Last left off

Completed in this work session:

- reviewed actual runtime source, dependencies, tests, release configuration,
  migrations, and security-sensitive settings;
- confirmed that remote `main` has the base `Middleware CI`, but not the newer
  connector and release workflows on this integration branch;
- confirmed there are no remote `staging` or `production` branches and that
  `testing/playwright` is a test workstream only;
- added exact-SHA `main` triggers to all connector workflows;
- corrected Connector Runtime CI so Alembic receives `DATABASE_URL`;
- packaged the generated command registry required by the application and added
  an image build/smoke job to `Middleware CI`.

No merge, push, deployment, environment creation, capability activation, or
external system change has been performed.

## Remaining production blockers

Work should continue in this order:

1. Upgrade the vulnerable FastAPI/Starlette and PyJWT dependency set and
   regenerate both hashed lock files.
2. Make Connector Runtime a self-contained, hash-locked, independently built
   artifact instead of relying on a CI-only monorepo `PYTHONPATH`.
3. Add streaming request-size enforcement and bounded encrypted-body retention
   to Connector Runtime.
4. Implement reviewed provider command and read-back adapters plus a separately
   authorized capability activation path. Keep all effects disabled until then.
5. Define least-privilege database roles, grants, migration locking and migration
   checksum policy in the deployment authority.
6. Add a deployed-topology staging test that starts the API, outbox worker and
   Temporal worker as separate processes and proves the full event path.
7. Audit `codestra-production-platform` for migration jobs, worker deployment,
   secret mounts, observability, backups, rollback, staging promotion, and
   production approval.

The next code task is blocker 1: dependency security remediation. After it is
complete, rerun `pip-audit`, the full locked test suite, disposable integration
jobs, and the release supply-chain validator before moving to blocker 2.
