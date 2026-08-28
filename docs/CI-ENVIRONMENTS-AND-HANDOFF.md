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
| `main` | release source branch | Present remotely at `cdb07b4`; Middleware CI and Signed Middleware Release passed for this commit | Merged, release-eligible source once required protection is confirmed |
| `integration/system-architecture-alignment` | retained workstream branch | Merged into `main`; retained remotely at `c07cc64` for audit history | Historical integration review; not a deployment source |
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
to `appolon1908-hue/codestra-production-platform`, whose protected integration
baseline is `release/production-activation`. That repository owns the central
contract catalog, runtime composition, multi-service release manifest,
integrated Caddy/Kong desired state, and promotion evidence. This repository
produces Middleware source, contracts, and signed service artifacts.

Caddy's canonical Git home is
`appolon1908-hue/codestra-production-platform:operations/caddy/`. The local
`platform/caddy` branch is a Middleware compatibility and review workstream,
not the production Caddy deployment source.

The canonical crawler source is `appolon1908-hue/kyqra-crawler`. The legacy
`appolon1908-hue/kyqra` repository name is retired and must not appear in new
contracts, composition, or release records.

## Last left off

Completed in this work session:

- reviewed actual runtime source, dependencies, tests, release configuration,
  migrations, and security-sensitive settings;
- merged and pushed the integration review to `main`;
- confirmed there are no remote `staging` or `production` branches and that
  `testing/playwright` is a test workstream only;
- added exact-SHA `main` triggers to all connector workflows;
- corrected Connector Runtime CI so Alembic receives `DATABASE_URL`;
- packaged the generated command registry required by the application and added
  an image build/smoke job to `Middleware CI`;
- upgraded FastAPI, Starlette, PyJWT, pytest, the Python base image, and hashed
  locks; `pip-audit` reported no known vulnerabilities;
- corrected the Cosign v3 annotation flag and completed the signed release;
- established `codestra-production-platform` as the machine-readable contract,
  runtime-composition, release-manifest, and Caddy configuration authority;
- selected `appolon1908-hue/kyqra-crawler` as the only canonical crawler source.

No deployment, GitHub Environment creation, capability activation, Caddy
reload, or provider-system mutation has been performed.

## Remaining production blockers

Work should continue in this order:

1. Make Connector Runtime a self-contained, hash-locked, independently built
   artifact instead of relying on a CI-only monorepo `PYTHONPATH`.
2. Add streaming request-size enforcement and bounded encrypted-body retention
   to Connector Runtime.
3. Implement reviewed provider command and read-back adapters plus a separately
   authorized capability activation path. Keep all effects disabled until then.
4. Define least-privilege database roles, grants, migration locking and migration
   checksum policy in the deployment authority.
5. Add a deployed-topology staging test that starts the API, outbox worker and
   Temporal worker as separate processes and proves the full event path.
6. Finish the `codestra-production-platform` runtime audit for migration jobs,
   worker deployment,
   secret mounts, observability, backups, rollback, staging promotion, and
   production approval.

The next code task is blocker 1: make Connector Runtime independently buildable
and hash-locked, then rerun its unit, migration, PostgreSQL, image-smoke,
dependency-audit, and release-supply-chain gates.
