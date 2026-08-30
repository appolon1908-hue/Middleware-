# Middleware repository settings baseline

This document is the exact target state for
`https://github.com/appolon1908-hue/Middleware-/settings`.

## Current verified state on 2026-08-30

- Default branch: `main`
- `main` is not protected.
- No repository rulesets exist.
- Merge commits, squash merges, and rebases are all allowed.
- Auto-merge, automatic branch deletion, update-branch support, and web commit
  signoff are disabled.

That state permits an administrator or collaborator to bypass the exact-head CI
model already implemented in the repository.

## General

Set the repository description to:

> Codestra durable integration and automation control plane

Recommended topics:

`middleware`, `fastapi`, `postgresql`, `keycloak`, `kong`, `n8n`,
`integration-platform`, `outbox`, `idempotency`, `gitops`

Keep Issues enabled. Disable Wiki unless it becomes an explicitly maintained
authority. The repository remains public only while secret scanning and push
protection are enabled and no runtime secrets are committed.

## Pull request merge settings

Enable only:

- Allow squash merging
- Always suggest updating pull request branches
- Allow auto-merge
- Automatically delete head branches
- Require contributors to sign off on web-based commits

Disable:

- Allow merge commits
- Allow rebase merging

## Actions

- Default workflow permissions: **Read repository contents and packages**
- Do not allow Actions to create or approve pull requests
- Keep every external action pinned to a full commit SHA
- Do not persist checkout credentials

## Active ruleset for `main`

Create an active branch ruleset named `middleware-main-production-authority`.

Require:

- Changes through pull requests
- All review conversations resolved
- Linear history
- Branch up to date before merge
- Status checks:
  - `Validate middleware source head`
  - `Validate middleware merge result`
  - `docker-runtime-build`
  - `docker-test-build`
  - `connector-runtime-build`
  - `container-security`
  - `Disposable PostgreSQL Redis integration`
  - `Disposable NATS JetStream integration`
  - `Temporal critical workflow integration`
  - `Synthetic no-effect acceptance E2E`
- Block force pushes
- Block branch deletion
- Apply to administrators

Set required approvals to zero for now because the repository has one owner and
GitHub does not allow an author to approve their own pull request. Production
release approval remains independently enforced. Raise this to one as soon as a
second trusted reviewer is added.

## Security and analysis

Enable dependency graph, Dependabot alerts and security updates, secret scanning,
push protection, private vulnerability reporting, and code scanning as a
production-release gate.

## Environments

Create `staging` and `production` environments.

`staging` uses `main`, immutable digests, and no live-write secret set true.

`production` requires an independent reviewer, prevents self-review, accepts only
`main`, forbids mutable tags, and keeps every live-write switch false until a
separately approved activation identifies the exact digest and rollback artifact.

## Verification

After applying the settings, run the `Repository governance audit` workflow with
an admin read token stored as `CODESTRA_REPOSITORY_ADMIN_TOKEN`. The workflow
does not mutate settings; it compares live state to
`config/repository-governance.v1.json` and fails closed on drift.
