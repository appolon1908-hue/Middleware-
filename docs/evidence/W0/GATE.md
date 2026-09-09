# Gate W0 — Contract decision and repository-governance baseline

- **Status:** POLICY_UPDATE_PENDING — LIVE REAPPLY AND TAG PENDING
- **Original baseline commit:** `382683958feefce73458ee56a1589092bad632b3`
- **Historical verified governance source:** `8e4e1e2e7ed38fffbd71f1b50d45b26ce325bc0e`
- **Historical live verification workflow:** `33781342722`
- **Active authority ruleset at historical verification:** `middleware-main-production-authority` (`22120968`)
- **Decision:** Middleware adopts automation v2 (ADR-0001)
- **Live writes changed:** no
- **Deployment changed:** no

## Historical evidence

Workflow run `33781342722` successfully applied and verified the policy at
source `8e4e1e2e7ed38fffbd71f1b50d45b26ce325bc0e`. At that point, the live
ruleset was active on the default branch with no bypass actors. It blocked
deletion and non-fast-forward updates, required linear history, one approving
review, stale-review dismissal, resolved review threads, squash-only merges,
and strict required checks.

That run remains valid evidence for its exact historical source. It is not
evidence that later policy changes are already live.

## Current policy decision

The current W0 source update resolves the previously open environment-review
decision. Both `staging` and `production` require independent review by the
approved reviewer identity, prevent self-review, disable administrator bypass,
and accept deployments only from protected branches. Twelve Middleware status
checks are now encoded.

The applier validates environment input before mutation, supports both protected
and custom branch-policy modes without conflating them, and reads back reviewer,
self-review, administrator-bypass, wait-timer, and deployment-branch settings.
The source validator pins the accepted environment and fail-closed release
policy.

These statements describe the proposed source policy. The live environments
must not be reported conformant until a new exact-source apply-and-read-back run
passes after merge.

No runtime, provider, credential, server, deployment, or external-effect
capability is activated by this source change or by repository-governance
application.

## Exit conditions

- [x] Option A recorded
- [x] Conformance harness present
- [x] Route authority and compatibility policy recorded
- [x] Skipped-test ownership documented
- [x] Historical GitHub governance apply and audit recorded
- [x] Independent environment-review decision recorded
- [ ] Updated policy merged through protected `main`
- [ ] Updated policy applied and read back from the exact protected-main SHA
- [ ] Current run/source evidence merged
- [ ] Tag `w0-complete` created and its exact target read back

After the source update reaches `main`, the owner-locked
`/apply-repository-governance w0-live-v1` workflow is the only approved apply
path. Creating the completion tag does not authorize runtime promotion or any
live write.
