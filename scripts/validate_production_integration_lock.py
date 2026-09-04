#!/usr/bin/env python3
"""Fail-closed validation for the full Codestra production integration lock."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
LOCK_PATH = ROOT / "config" / "production-integration-lock.v1.json"
EVIDENCE_DIR = ROOT / "artifacts" / "production-integration-lock"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
REPO_RE = re.compile(r"^appolon1908-hue/[A-Za-z0-9_.-]+$")
SOURCE_STATES = {
    "protected_source_ready",
    "candidate_pending_review",
    "candidate_needs_refresh",
    "governance_incomplete",
    "source_only",
    "authority_only",
}
CHECK_STATES = {"active", "missing", "unverified"}
REVIEWER_STATES = {"available", "requested", "pending-access", "unverified"}
BINDING_STATES = {
    "source-ready",
    "source-only",
    "runtime-unverified",
    "not-observed",
    "unverified",
}
PRODUCTION_STATES = {"BLOCKED", "SOURCE_READY", "PENDING_PROTECTED_MERGE"}
CANDIDATE_STATES = {
    "refresh-from-main-required",
    "pending-review-before-development-reconciliation",
    "superseded-by-reconciled-development-head",
    "pending-exact-head-review",
    "blocked-by-pr-55-and-refresh",
    "pending-review-and-source-pin-refresh",
    "ci-running-and-reviewer-access-pending",
    "reviewer-access-pending",
    "independent-review-requested",
    "reviewer-and-ruleset-access-pending",
}
GLOBAL_GATES = [
    "protected_merged_source",
    "exact_head_ci",
    "independent_approval",
    "signed_immutable_artifact",
    "staging_readonly_deployment",
    "source_and_digest_readback",
    "identity_and_route_matrix",
    "provider_readback",
    "backup_restore",
    "rollback_rehearsal",
    "monitoring_continuity",
    "bounded_read_only_canary",
]


class LockError(RuntimeError):
    """The integration lock would permit an unsupported production claim."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise LockError(message)


def load_lock(path: Path = LOCK_PATH) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LockError(f"cannot load integration lock: {path}") from exc
    require(isinstance(value, dict), "integration lock must be an object")
    return value


def validate_runtime(component: Mapping[str, Any]) -> None:
    cid = str(component["component_id"])
    runtime = component.get("runtime")
    require(isinstance(runtime, Mapping), f"{cid}: runtime record missing")
    require(runtime.get("binding_state") in BINDING_STATES, f"{cid}: invalid binding state")
    certified = runtime.get("runtime_certified")
    require(isinstance(certified, bool), f"{cid}: runtime_certified must be boolean")
    evidence_fields = (
        "staging_evidence",
        "backup_restore_evidence",
        "rollback_evidence",
        "runtime_readback_evidence",
    )
    if certified:
        digest = runtime.get("immutable_image_digest")
        require(isinstance(digest, str) and DIGEST_RE.fullmatch(digest), f"{cid}: immutable digest required")
        for field in evidence_fields:
            value = runtime.get(field)
            require(isinstance(value, str) and value.strip(), f"{cid}: {field} required")
        require(
            component.get("source_state") == "protected_source_ready",
            f"{cid}: certified runtime requires protected source",
        )
        governance = component["governance"]
        require(governance.get("branch_protected") is True, f"{cid}: protected branch required")
        require(
            governance.get("required_status_checks_state") == "active",
            f"{cid}: active required checks required",
        )
    else:
        require(runtime.get("immutable_image_digest") is None, f"{cid}: uncertified digest must be null")
        for field in evidence_fields:
            require(runtime.get(field) is None, f"{cid}: uncertified evidence must be null")


def validate_candidate(component_id: str, candidate: Mapping[str, Any]) -> None:
    number = candidate.get("pull_request")
    require(isinstance(number, int) and number > 0, f"{component_id}: invalid PR number")
    head = candidate.get("head_sha")
    require(isinstance(head, str) and SHA_RE.fullmatch(head), f"{component_id}: invalid candidate SHA")
    base = candidate.get("base_branch")
    require(isinstance(base, str) and base, f"{component_id}: candidate base missing")
    require(candidate.get("status") in CANDIDATE_STATES, f"{component_id}: invalid candidate status")
    require(candidate.get("merge_method") in {"squash", "merge"}, f"{component_id}: invalid merge method")


def validate_lock(value: Mapping[str, Any]) -> dict[str, Any]:
    require(value.get("schema_version") == "1.0", "unsupported lock schema")
    require(
        value.get("lock_id") == "codestra.middleware-full-production-integration.v1",
        "lock ID drift",
    )
    require(value.get("decision") == "NO_GO", "source lock decision must remain NO_GO")
    require(value.get("production_activated") is False, "production must remain inactive")

    authority = value.get("authority")
    require(isinstance(authority, Mapping), "authority missing")
    require(authority.get("repository") == "appolon1908-hue/Middleware-", "authority repository drift")
    base_sha = authority.get("base_sha")
    require(isinstance(base_sha, str) and SHA_RE.fullmatch(base_sha), "authority base SHA invalid")

    policy = value.get("release_policy")
    require(isinstance(policy, Mapping), "release policy missing")
    require(policy.get("immutable_artifacts_only") is True, "immutable artifacts are required")
    require(policy.get("rebuild_between_environments") is False, "environment rebuilds are forbidden")
    percent = policy.get("max_read_only_canary_percent")
    require(isinstance(percent, int) and 0 < percent <= 1, "read-only canary must be <=1 percent")
    require(policy.get("read_only_canary_methods") == ["GET", "HEAD"], "read-only canary methods drift")
    require(policy.get("required_global_gates") == GLOBAL_GATES, "global gate order or coverage drift")
    require(policy.get("calls_placed") == 0, "CALLS_PLACED must remain zero")
    effects = policy.get("external_effects")
    require(isinstance(effects, Mapping) and effects, "external effects registry missing")
    for name, enabled in effects.items():
        require(isinstance(name, str) and name, "invalid external effect name")
        require(enabled is False, f"external effect must remain disabled: {name}")

    components = value.get("components")
    require(isinstance(components, list) and len(components) >= 20, "component coverage incomplete")
    ids: set[str] = set()
    repositories: set[str] = set()
    repository_ids: set[int] = set()
    normalized: list[dict[str, Any]] = []
    for raw in components:
        require(isinstance(raw, Mapping), "component must be an object")
        cid = raw.get("component_id")
        require(isinstance(cid, str) and cid, "component ID missing")
        require(cid not in ids, f"duplicate component ID: {cid}")
        ids.add(cid)

        repository = raw.get("repository")
        require(
            isinstance(repository, str) and REPO_RE.fullmatch(repository),
            f"{cid}: invalid repository authority",
        )
        require(repository not in repositories, f"duplicate repository: {repository}")
        repositories.add(repository)

        repository_id = raw.get("repository_id")
        require(isinstance(repository_id, int) and repository_id > 0, f"{cid}: repository ID invalid")
        require(repository_id not in repository_ids, f"duplicate repository ID: {repository_id}")
        repository_ids.add(repository_id)

        branch = raw.get("authority_branch")
        require(isinstance(branch, str) and branch, f"{cid}: authority branch missing")
        source_sha = raw.get("source_sha")
        require(isinstance(source_sha, str) and SHA_RE.fullmatch(source_sha), f"{cid}: source SHA invalid")
        require(raw.get("source_state") in SOURCE_STATES, f"{cid}: invalid source state")
        require(raw.get("production_state") in PRODUCTION_STATES, f"{cid}: invalid production state")

        role = raw.get("integration_role")
        require(isinstance(role, str) and role.strip(), f"{cid}: integration role missing")
        blockers = raw.get("blockers")
        require(isinstance(blockers, list) and blockers, f"{cid}: blockers must be explicit")
        require(
            all(isinstance(item, str) and item.strip() for item in blockers),
            f"{cid}: invalid blocker",
        )

        governance = raw.get("governance")
        require(isinstance(governance, Mapping), f"{cid}: governance missing")
        require(isinstance(governance.get("branch_protected"), bool), f"{cid}: branch protection invalid")
        require(
            governance.get("required_status_checks_state") in CHECK_STATES,
            f"{cid}: required-check state invalid",
        )
        require(
            governance.get("independent_reviewer_state") in REVIEWER_STATES,
            f"{cid}: reviewer state invalid",
        )
        if raw.get("source_state") == "protected_source_ready":
            require(governance.get("branch_protected") is True, f"{cid}: protected source claim invalid")
            require(
                governance.get("required_status_checks_state") == "active",
                f"{cid}: protected source requires active checks",
            )
        if (
            governance.get("branch_protected") is False
            or governance.get("required_status_checks_state") != "active"
        ):
            require(
                raw.get("production_state") == "BLOCKED",
                f"{cid}: incomplete governance must remain blocked",
            )

        candidates = raw.get("candidates")
        require(isinstance(candidates, list), f"{cid}: candidates must be a list")
        for candidate in candidates:
            require(isinstance(candidate, Mapping), f"{cid}: candidate must be an object")
            validate_candidate(cid, candidate)
        if raw.get("source_state") in {"candidate_pending_review", "candidate_needs_refresh"}:
            require(bool(candidates), f"{cid}: candidate source state requires PR evidence")

        dependencies = raw.get("depends_on")
        require(isinstance(dependencies, list), f"{cid}: dependencies must be a list")
        require(
            all(isinstance(item, str) and item for item in dependencies),
            f"{cid}: invalid dependency",
        )

        validate_runtime(raw)
        if raw.get("production_state") == "SOURCE_READY":
            require(raw["runtime"]["runtime_certified"] is False, f"{cid}: source-ready is not runtime-certified")
        normalized.append(dict(raw))

    for component in normalized:
        cid = component["component_id"]
        for dependency in component["depends_on"]:
            require(dependency in ids, f"{cid}: unknown dependency: {dependency}")
            require(dependency != cid, f"{cid}: self-dependency forbidden")

    order = value.get("promotion_order")
    require(isinstance(order, list) and len(order) >= 10, "promotion order incomplete")
    require(all(isinstance(step, str) and step.strip() for step in order), "invalid promotion step")

    return {
        "schema_version": "1.0",
        "result": "PASS",
        "decision": "NO_GO",
        "component_count": len(normalized),
        "runtime_certified_count": sum(
            1 for row in normalized if row["runtime"]["runtime_certified"]
        ),
        "production_activated": False,
        "external_effects_enabled": [],
        "calls_placed": 0,
    }


def write_evidence(document: Mapping[str, Any]) -> None:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    (EVIDENCE_DIR / "validation.json").write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lock", type=Path, default=LOCK_PATH)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(list(sys.argv[1:] if argv is None else argv))
    try:
        document = validate_lock(load_lock(args.lock))
        write_evidence(document)
        print(
            "PRODUCTION_INTEGRATION_LOCK=PASS "
            f"components={document['component_count']} "
            f"runtime_certified={document['runtime_certified_count']} "
            "decision=NO_GO calls_placed=0"
        )
        return 0
    except LockError as exc:
        document = {
            "schema_version": "1.0",
            "result": "FAIL",
            "decision": "NO_GO",
            "production_activated": False,
            "calls_placed": 0,
            "error": str(exc),
        }
        write_evidence(document)
        print(f"PRODUCTION_INTEGRATION_LOCK=FAIL reason={exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
