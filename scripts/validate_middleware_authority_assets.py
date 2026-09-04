#!/usr/bin/env python3
"""Validate implementation controls for Middleware authority convergence."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = Path("config/middleware-authority-convergence.v1.json")
WORKFLOW_PATH = Path(
    ".github/workflows/mirror-codestra-legacy-middleware-images.yml"
)
BACKUP_SCRIPT_PATH = Path(
    "scripts/server-a-backup-legacy-middleware-images.sh"
)
DOCKERFILE_PATH = Path("Dockerfile.runtime")
DOCKERIGNORE_PATH = Path(".dockerignore")
DOC_PATH = Path("docs/production/MIDDLEWARE-AUTHORITY-CONVERGENCE.md")
EXPECTED_FAMILY_COUNT = 16
EXPECTED_WORKLOAD_COUNT = 31
EXPECTED_REGISTRY_MIRRORS = 4
EXPECTED_LOCAL_BACKUPS = 11
DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")


def _read(root: Path, relative: Path, errors: list[str]) -> str:
    path = root / relative
    if not path.is_file() or path.is_symlink():
        errors.append(f"required regular file missing: {relative.as_posix()}")
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        errors.append(f"cannot read {relative.as_posix()}: {exc}")
        return ""


def _load_catalog(root: Path, errors: list[str]) -> dict[str, Any]:
    raw = _read(root, CATALOG_PATH, errors)
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        errors.append(f"catalog is invalid JSON: {exc}")
        return {}
    if not isinstance(value, dict):
        errors.append("catalog root must be an object")
        return {}
    return value


def validate_assets(root: Path = ROOT) -> list[str]:
    """Return implementation errors; an empty list means PASS."""

    errors: list[str] = []
    catalog = _load_catalog(root, errors)
    workflow = _read(root, WORKFLOW_PATH, errors)
    backup_script = _read(root, BACKUP_SCRIPT_PATH, errors)
    dockerfile = _read(root, DOCKERFILE_PATH, errors)
    dockerignore = _read(root, DOCKERIGNORE_PATH, errors)
    documentation = _read(root, DOC_PATH, errors)

    families = catalog.get("runtimeImageFamilies", [])
    if not isinstance(families, list):
        errors.append("runtimeImageFamilies must be an array")
        families = []

    workload_count = 0
    registry_mirrors = 0
    local_backups = 0
    for family in families:
        if not isinstance(family, dict):
            errors.append("runtimeImageFamilies entries must be objects")
            continue
        workloads = family.get("workloads", [])
        if not isinstance(workloads, list):
            errors.append(f"family {family.get('id')!r} workloads must be an array")
            workloads = []
        workload_count += len(workloads)
        backup = family.get("backup", {})
        if not isinstance(backup, dict):
            errors.append(f"family {family.get('id')!r} backup must be an object")
            continue
        method = backup.get("method")
        if method == "registry-preserve-digest":
            registry_mirrors += 1
        elif method == "server-a-archive-and-config-digest-mirror":
            local_backups += 1

    if len(families) != EXPECTED_FAMILY_COUNT:
        errors.append(
            f"runtime image family count drifted: expected "
            f"{EXPECTED_FAMILY_COUNT}, got {len(families)}"
        )
    if workload_count != EXPECTED_WORKLOAD_COUNT:
        errors.append(
            f"runtime workload count drifted: expected "
            f"{EXPECTED_WORKLOAD_COUNT}, got {workload_count}"
        )
    if registry_mirrors != EXPECTED_REGISTRY_MIRRORS:
        errors.append(
            f"registry mirror count drifted: expected "
            f"{EXPECTED_REGISTRY_MIRRORS}, got {registry_mirrors}"
        )
    if local_backups != EXPECTED_LOCAL_BACKUPS:
        errors.append(
            f"local backup count drifted: expected "
            f"{EXPECTED_LOCAL_BACKUPS}, got {local_backups}"
        )

    candidate = (
        catalog.get("forwardAuthority", {})
        .get("image", {})
        .get("currentSignedCandidate", {})
    )
    if not isinstance(candidate, dict):
        errors.append("currentSignedCandidate must be an object")
    else:
        digest = candidate.get("imageDigest")
        if not isinstance(digest, str) or DIGEST.fullmatch(digest) is None:
            errors.append("current signed candidate digest is malformed")

    workflow_requirements = {
        "manual dispatch": "workflow_dispatch:",
        "protected-main guard": 'test "$GITHUB_REF" = "refs/heads/main"',
        "exact checkout guard": 'test "$(git rev-parse HEAD)" = "$GITHUB_SHA"',
        "source package credential": "CODESTRA_GHCR_TOKEN",
        "digest preservation": "--preserve-digests",
        "raw manifest comparison": "Raw source and destination manifests differ",
        "no runtime promotion evidence": '"runtime_promoted": False',
        "source retention evidence": '"codestra_source_retained": True',
    }
    for label, needle in workflow_requirements.items():
        if needle not in workflow:
            errors.append(f"mirror workflow missing {label}")

    if re.search(r"(?m)^\s*push\s*:", workflow):
        errors.append("mirror workflow must not run automatically on push")
    forbidden_workflow_builders = (
        "docker build ",
        "docker/build-push-action",
        "buildah bud ",
        "podman build ",
    )
    for needle in forbidden_workflow_builders:
        if needle in workflow:
            errors.append(
                f"mirror workflow must copy, not rebuild images: found {needle!r}"
            )

    script_requirements = {
        "root gate": 'fail "root_required"',
        "Server A address gate": 'fail "server_a_host_identity_mismatch"',
        "catalog validation": "validate_middleware_authority_convergence.py",
        "missing workload failure": "MISSING_EXPECTED_WORKLOADS",
        "environment non-capture": '"environment_values_captured": False',
        "mount-source non-capture": '"mount_sources_captured": False',
        "mount-destination evidence": '"mount_destinations_captured": True',
        "docker-save archive": 'docker image save "$expected_id"',
        "archive config verification": "docker save config digest mismatch",
        "isolated restore denial": '"isolated_restore_performed": False',
        "isolated restore requirement": (
            '"isolated_restore_required_before_cutover": True'
        ),
        "private registry auth gate": "validate_private_file",
        "temporary tag cleanup": "trap cleanup_temp_tag EXIT",
        "run checksum verification": "sha256sum --check --strict SHA256SUMS",
    }
    for label, needle in script_requirements.items():
        if needle not in backup_script:
            errors.append(f"Server A backup script missing {label}")

    forbidden_script_actions = (
        "docker compose up",
        "docker compose down",
        "docker container restart",
        "docker restart",
        "docker container stop",
        "docker stop",
        "docker container rm",
    )
    for needle in forbidden_script_actions:
        if needle in backup_script:
            errors.append(
                f"backup script must not mutate running containers: found {needle!r}"
            )

    marker = "FROM ${TEST_BASE} AS test"
    if marker not in dockerfile:
        errors.append("Dockerfile test target marker is missing")
    else:
        runtime_section, test_section = dockerfile.split(marker, 1)
        test_only_paths = (
            "MIDDLEWARE-AUTHORITY-RECONCILIATION.yaml",
            ".github/workflows/mirror-codestra-legacy-middleware-images.yml",
        )
        for path in test_only_paths:
            if path in runtime_section:
                errors.append(
                    f"authority-only asset leaked into production runtime stage: {path}"
                )
            if path not in test_section:
                errors.append(f"Docker test target does not package {path}")

    allowlist_line = (
        "!.github/workflows/mirror-codestra-legacy-middleware-images.yml"
    )
    if allowlist_line not in dockerignore.splitlines():
        errors.append("Docker context does not allowlist the mirror workflow")
    if ".github/workflows/*" not in dockerignore.splitlines():
        errors.append("Docker context no longer denies workflows by default")

    documentation_requirements = (
        "only forward source",
        "rollback-only",
        "CODESTRA_GHCR_TOKEN",
        "isolated restore",
        "SERVER_A_RUNTIME_REVALIDATION=NOT_EXECUTED",
        "PRODUCTION_CHANGED=NO",
        "CALLS_PLACED=0",
    )
    lower_documentation = documentation.lower()
    for phrase in documentation_requirements:
        if phrase.lower() not in lower_documentation:
            errors.append(
                f"authority documentation missing required statement: {phrase}"
            )

    return errors


def main() -> int:
    errors = validate_assets()
    if errors:
        print("MIDDLEWARE_AUTHORITY_ASSETS=FAIL", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("MIDDLEWARE_AUTHORITY_ASSETS=PASS")
    print(f"RUNTIME_IMAGE_FAMILIES={EXPECTED_FAMILY_COUNT}")
    print(f"RUNTIME_WORKLOADS={EXPECTED_WORKLOAD_COUNT}")
    print(f"EXACT_REGISTRY_MIRRORS={EXPECTED_REGISTRY_MIRRORS}")
    print(f"SERVER_A_LOCAL_BACKUPS={EXPECTED_LOCAL_BACKUPS}")
    print("SERVER_A_RUNTIME_MUTATED=NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
