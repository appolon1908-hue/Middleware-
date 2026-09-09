#!/usr/bin/env python3
"""Run only an independently approved production-contract validator pair.

This launcher is executed from the protected base branch by a
``pull_request_target`` workflow. Candidate source is treated as inert data
until both Python validators have matched a pair approved on protected main.
The candidate cannot update these approvals, this launcher, or its workflow in
the same pull request that changes a validator.
"""

from __future__ import annotations

import hashlib
import os
import re
import runpy
import subprocess
import sys
from pathlib import Path


TRUST_ROOT = Path(__file__).resolve().parents[1]
LAUNCHER_PATH = Path(__file__).resolve()
WORKFLOW_PATH = Path(".github/workflows/production-orchestrator-contract.yml")
ORCHESTRATOR_PATH = Path(".codestra/validate-production-orchestrator-contract.py")
RELEASE_VALIDATOR_PATH = Path(".codestra/validate-release-intent.py")
SHA = re.compile(r"[0-9a-f]{40}")

# The key is the exact orchestrator validator. The bootstrap generation binds
# its release validator byte-for-byte. The successor binds its normalized
# security fingerprint, permitting reviewed source-closure/hash value updates
# without permitting release-policy logic to change in the same pull request.
APPROVED_VALIDATOR_POLICIES = {
    "529dcf0501b1624fb18da2ded0c0459978a0174f43e3f9412877f749911fe06b": (
        "raw",
        "97f3891f1d638141780a1c2e5772f7cb7c51dcae44325299777605ee92097497",
    ),
    "06ab6afa78b151825c708878a8426e77e148827f9bd614e724f5bd92f7cc836b": (
        "security-fingerprint",
        "15dbaa6d571a1d1e72c09ca417cc94198d8f21260babfae5eaedbdd46472b1ec",
    ),
}


class TrustError(RuntimeError):
    """Raised when candidate source is not anchored by protected main."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise TrustError(message)


def digest(path: Path) -> str:
    require(path.is_file() and not path.is_symlink(), f"unsafe trust path: {path}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require_unchanged_trust_file(relative: Path, candidate_root: Path) -> None:
    trusted = TRUST_ROOT / relative
    candidate = candidate_root / relative
    require(
        digest(candidate) == digest(trusted),
        f"protected-base trust file changed: {relative.as_posix()}",
    )


def candidate_root() -> Path:
    raw = os.environ.get("VALIDATION_ROOT", "")
    require(bool(raw), "VALIDATION_ROOT is required")
    unresolved = Path(raw)
    require(unresolved.is_absolute(), "VALIDATION_ROOT must be absolute")
    require(not unresolved.is_symlink(), "VALIDATION_ROOT cannot be a symlink")
    resolved = unresolved.resolve(strict=True)
    require(resolved.is_dir(), "VALIDATION_ROOT must be a directory")
    return resolved


def validate_exact_checkout(root: Path) -> str:
    expected = os.environ.get("EXPECTED_SHA", "")
    require(SHA.fullmatch(expected) is not None, "EXPECTED_SHA is invalid")
    actual = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=root, text=True
    ).strip()
    require(actual == expected, "candidate checkout does not match EXPECTED_SHA")
    return expected


def validate_candidate(root: Path) -> Path:
    require_unchanged_trust_file(WORKFLOW_PATH, root)
    require_unchanged_trust_file(LAUNCHER_PATH.relative_to(TRUST_ROOT), root)
    orchestrator = root / ORCHESTRATOR_PATH
    release_validator = root / RELEASE_VALIDATOR_PATH
    orchestrator_digest = digest(orchestrator)
    release_validator_digest = digest(release_validator)
    policy = APPROVED_VALIDATOR_POLICIES.get(orchestrator_digest)
    require(
        policy is not None,
        "candidate orchestrator validator is not approved by protected main",
    )
    assert policy is not None
    mode, expected_release_digest = policy
    if mode == "raw":
        observed_release_digest: object = release_validator_digest
    else:
        require(
            mode == "security-fingerprint",
            "protected-base release-validator policy mode is invalid",
        )
        namespace = runpy.run_path(str(orchestrator), run_name="approved_orchestrator")
        fingerprint = namespace.get("release_validator_security_fingerprint")
        if not callable(fingerprint):
            raise TrustError("approved orchestrator fingerprint is missing")
        observed_release_digest = fingerprint(
            release_validator.read_text(encoding="utf-8")
        )
    require(
        observed_release_digest == expected_release_digest,
        "candidate release validator is not approved by protected main",
    )
    return orchestrator


def main() -> int:
    root = candidate_root()
    validate_exact_checkout(root)
    os.environ["PYTHONSAFEPATH"] = "1"
    orchestrator = validate_candidate(root)
    os.environ.pop("VALIDATION_ROOT", None)
    previous_cwd = Path.cwd()
    previous_argv = sys.argv[:]
    try:
        os.chdir(root)
        sys.argv = [str(orchestrator)]
        try:
            runpy.run_path(str(orchestrator), run_name="__main__")
        except SystemExit as error:
            require(
                error.code in (None, 0),
                "approved production-contract validator failed",
            )
    finally:
        sys.argv = previous_argv
        os.chdir(previous_cwd)
    print("PROTECTED_BASE_VALIDATOR_TRUST=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
