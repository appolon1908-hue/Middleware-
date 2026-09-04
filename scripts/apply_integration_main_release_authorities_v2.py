#!/usr/bin/env python3
"""Expanded fixed integration authority and exact owner issue-command gate."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
BASE_SCRIPT = ROOT / "scripts" / "apply_integration_main_release_authorities.py"

spec = importlib.util.spec_from_file_location("integration_authority_v1", BASE_SCRIPT)
if spec is None or spec.loader is None:  # pragma: no cover - import guard
    raise RuntimeError("cannot load v1 integration authority")
BASE = importlib.util.module_from_spec(spec)
spec.loader.exec_module(BASE)

EXPECTED_OWNER = "appolon1908-hue"
EXPECTED_OWNER_ID = 275410064
EXPECTED_REPOSITORY = "appolon1908-hue/Middleware-"
EXPECTED_REPOSITORY_ID = 1347559071
EXPECTED_ISSUE_NUMBER = 130
EXPECTED_ISSUE_COMMAND = "/apply-integration-main-release-authority v1"
EXPECTED_REPOSITORIES = {
    "appolon1908-hue/Codestra-AI": (
        1351354401,
        ("unit-and-contract", "postgres-certification", "container-build"),
    ),
    "appolon1908-hue/Codestra-Marketing-": (
        1351352422,
        ("unit-and-contract", "postgres-certification", "container-build"),
    ),
    "appolon1908-hue/Codestra-Prometheus": (
        1350767800,
        (
            "production-source-validation",
            "deploy-readiness / deploy-readiness / overlay-source-ci",
            "deploy-readiness / deploy-readiness / overlay-secret-scan",
        ),
    ),
    "appolon1908-hue/N8N": (
        1347560645,
        (
            "Validate exact repository SHA",
            "deploy-readiness / deploy-readiness / source-ci",
            "deploy-readiness / deploy-readiness / secret-scan",
        ),
    ),
    "appolon1908-hue/Vicidialer-Codestra": (
        1347744324,
        (
            "deploy-readiness / deploy-readiness / secret-scan",
            "deploy-readiness / deploy-readiness / source-ci",
        ),
    ),
    "appolon1908-hue/Websocket-": (
        1357322123,
        ("exact-head-ci",),
    ),
    "appolon1908-hue/klyrow.com": (
        1334863061,
        ("frontend", "test", "secrets", "image"),
    ),
    "appolon1908-hue/social.codestra.co": (
        1348783113,
        (
            "Backend policy, migration, test, and build",
            "Backend container build and hardening",
            "certify",
        ),
    ),
}


def configure_base() -> None:
    """Bind the v1 controller to the exact expanded repository set."""
    BASE.EXPECTED_REPOSITORIES = EXPECTED_REPOSITORIES


def validate_issue_comment_event(event: Mapping[str, Any]) -> None:
    """Reject every issue event except the exact owner command on issue 130."""
    BASE.require(event.get("action") == "created", "issue command action drift")
    repository = event.get("repository")
    BASE.require(isinstance(repository, Mapping), "issue command repository missing")
    BASE.require(
        repository.get("id") == EXPECTED_REPOSITORY_ID,
        "issue command repository ID drift",
    )
    BASE.require(
        repository.get("full_name") == EXPECTED_REPOSITORY,
        "issue command repository drift",
    )
    BASE.require(
        repository.get("default_branch") == "main",
        "issue command default branch drift",
    )
    owner = repository.get("owner")
    BASE.require(isinstance(owner, Mapping), "issue command owner missing")
    BASE.require(owner.get("login") == EXPECTED_OWNER, "issue command owner login drift")
    BASE.require(owner.get("id") == EXPECTED_OWNER_ID, "issue command owner ID drift")

    issue = event.get("issue")
    BASE.require(isinstance(issue, Mapping), "issue command issue missing")
    BASE.require(issue.get("number") == EXPECTED_ISSUE_NUMBER, "issue command number drift")
    BASE.require(
        "pull_request" not in issue,
        "issue command cannot originate from a pull request",
    )

    sender = event.get("sender")
    comment = event.get("comment")
    BASE.require(isinstance(sender, Mapping), "issue command sender missing")
    BASE.require(isinstance(comment, Mapping), "issue command comment missing")
    comment_user = comment.get("user")
    BASE.require(isinstance(comment_user, Mapping), "issue command comment user missing")
    for actor, label in ((sender, "sender"), (comment_user, "comment user")):
        BASE.require(
            actor.get("login") == EXPECTED_OWNER,
            f"issue command {label} login drift",
        )
        BASE.require(
            actor.get("id") == EXPECTED_OWNER_ID,
            f"issue command {label} ID drift",
        )
    BASE.require(
        comment.get("body") == EXPECTED_ISSUE_COMMAND,
        "issue command body drift",
    )


def main(argv: list[str] | None = None) -> int:
    configure_base()
    return BASE.main(list(sys.argv[1:] if argv is None else argv))


if __name__ == "__main__":
    raise SystemExit(main())
