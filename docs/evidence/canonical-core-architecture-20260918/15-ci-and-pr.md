# 15 — Commit, PR and exact-SHA CI

| Item | Value |
| --- | --- |
| Branch | `mission/middleware-canonical-core-20260918` |
| Base (PR #278 head) | `899585932c51fdb02827c8e28777d388fbb43c44` |
| Mission-2 commit | `cbfeb369034f0d5314371faf25b69824e49a145e` (single commit, parent = base) |
| PR | #280 (draft), base branch `codex/cross-repo-authority-20260916` — stacked on #278 |
| Push | `origin` (`appolon1908-hue/Middleware-`, GitHub now redirects to `ingtrader21-spec/Middleware-`) |

Merge rules in force: not before #278; not while any required check is pending or red; no force-merge, no
bypass. The PR is a draft until the exact-SHA CI of `cbfeb36` is green and #278 is merged.

## Required checks (branch protection on `main`)

`validate` · `docker-test-build` · `docker-runtime-build` · `container-security` ·
`Disposable PostgreSQL Redis integration` · `Disposable NATS JetStream integration` ·
`Temporal critical workflow integration` · `Synthetic no-effect acceptance E2E`, plus the
`Required exact-SHA CI` / `codestra/required-ci` status.

## State inherited from #278 (base) at the time of writing

`Required exact-SHA CI`: success. `Middleware CI` `validate`: **failure** — `Validate middleware source head`
and `Validate middleware merge result` (source validators; `validate_platform_control_plane.py` is fixed by
this PR), `connector-runtime-build` and `container-security` (connector runtime image and its security scan —
outside this change set). Also red on #278: `Production orchestrator contract`, `Trusted production
orchestrator evidence`, `beyvra-email-authority`. These are not caused by Mission 2 and cannot be fixed inside
its scope; they block #278 first.

## Exact-SHA CI loop for `cbfeb36`

Per the mission: run CI on the exact SHA, read every failing job's log, fix root causes in follow-up commits
on this branch (each recorded here with its SHA), never re-run to get lucky, never skip a required test.

| Round | SHA | Result | Root cause | Fix |
| --- | --- | --- | --- | --- |
| 1 | `cbfeb36` | red: `Required exact-SHA CI` (mypy: `pydantic_settings.sources` has no `parse_env_vars`), every `Middleware CI` job, `Integrated monitoring API`, `lead-automation-v1`, `Release component matrix (middleware)` — all with `ImportError: cannot import name 'parse_env_vars' from 'pydantic_settings.sources'` | the locked CI environment pins `pydantic-settings==2.10.1`, which no longer exports the private `parse_env_vars` helper the mapping source imported (the development host has 2.7.1) | `_MappingEnvSource._load_env_vars` normalizes the mapping itself (case folding, empty-value skipping, none-string parsing) and delegates to the parent for `os.environ`; verified in a venv with `pydantic==2.10.4`/`pydantic-settings==2.10.1`. Passing in round 1 despite the import error: `Historical Stage 6 … validate`, `Production route contract`, `Observability alert contract`, `Production integration lock`, `Connector SDK`, `Python quality baseline`; `PLATFORM_CONTROL_PLANE=PASS` was reached in `run_ci.sh` before the import failure. |
| 2 | (next commit) | pending | — | — |

This file is updated in the same branch after each CI round.
