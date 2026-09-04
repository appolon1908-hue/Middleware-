from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.vicidial_odoo_projection_authority import (
    load_projection_source_locks,
    validate_projection_source_locks,
)
from app.vicidial_odoo_projection_errors import ProjectionConfigurationError

ROOT = Path(__file__).resolve().parents[1]
AUTHORITY = (
    ROOT
    / "config"
    / "vicidial-odoo-projection-source-authority.v1.json"
)

EXPECTED_LOCKS = {
    "KEYCLOAK_LIFECYCLE_SOURCE_SHA": (
        "922d039b5143f3ac738e88998036355562a8dd5d"
    ),
    "ODOO_CALL_EVENT_SOURCE_SHA": (
        "9f38f87138f2914622b8ac1243c7969691ac5317"
    ),
    "VICIDIAL_EVENT_SOURCE_SHA": (
        "8007f9550a933c1cb17f21da6028dcfc41b47b0a"
    ),
}


def test_projection_authority_pins_all_reviewed_dependency_heads() -> None:
    document = json.loads(AUTHORITY.read_text(encoding="utf-8"))
    dependencies = document["dependencies"]

    assert dependencies["keycloak"] == {
        "repository": "appolon1908-hue/Keycloak",
        "pull_request": 86,
        "state_at_lock": "merged",
        "base_ref": "refs/heads/main",
        "source_sha": EXPECTED_LOCKS["KEYCLOAK_LIFECYCLE_SOURCE_SHA"],
        "runtime_env": "KEYCLOAK_LIFECYCLE_SOURCE_SHA",
        "merge_required_before_activation": True,
    }
    assert dependencies["odoo"] == {
        "repository": "appolon1908-hue/Odoo",
        "pull_request": 78,
        "state_at_lock": "open_candidate",
        "base_sha": "4daa1be3be8c2475b79db6e51a8b12d66823fdff",
        "source_sha": EXPECTED_LOCKS["ODOO_CALL_EVENT_SOURCE_SHA"],
        "runtime_env": "ODOO_CALL_EVENT_SOURCE_SHA",
        "merge_required_before_activation": True,
    }
    assert dependencies["vicidial"] == {
        "repository": "appolon1908-hue/Vicidialer-Codestra",
        "pull_request": 17,
        "state_at_lock": "open_candidate",
        "base_sha": "72ab7a1edf8c76169b0e03aadbea742e4cb2196e",
        "source_sha": EXPECTED_LOCKS["VICIDIAL_EVENT_SOURCE_SHA"],
        "runtime_env": "VICIDIAL_EVENT_SOURCE_SHA",
        "merge_required_before_activation": True,
    }
    assert load_projection_source_locks() == EXPECTED_LOCKS


def test_exact_projection_source_tuple_is_accepted() -> None:
    assert validate_projection_source_locks(EXPECTED_LOCKS) == EXPECTED_LOCKS


@pytest.mark.parametrize("runtime_env", sorted(EXPECTED_LOCKS))
def test_missing_or_changed_projection_source_fails_closed(
    runtime_env: str,
) -> None:
    missing = dict(EXPECTED_LOCKS)
    missing.pop(runtime_env)
    with pytest.raises(
        ProjectionConfigurationError,
        match=runtime_env,
    ):
        validate_projection_source_locks(missing)

    changed = dict(EXPECTED_LOCKS)
    changed[runtime_env] = "0" * 40
    with pytest.raises(
        ProjectionConfigurationError,
        match=runtime_env,
    ):
        validate_projection_source_locks(changed)


def test_authority_cannot_grant_runtime_or_external_effects(
    tmp_path: Path,
) -> None:
    document = json.loads(AUTHORITY.read_text(encoding="utf-8"))
    boundary = document["activation_boundary"]
    assert boundary == {
        "source_merge_authorized_by_this_file": False,
        "runtime_activation_authorized_by_this_file": False,
        "production_dialing_authorized_by_this_file": False,
        "external_effects_authorized_by_this_file": False,
        "requires_exact_runtime_source_readback": True,
        "requires_protected_dependency_merges": True,
        "calls_placed_expected": 0,
    }

    boundary["runtime_activation_authorized_by_this_file"] = True
    unsafe = tmp_path / "unsafe-authority.json"
    unsafe.write_text(
        json.dumps(document),
        encoding="utf-8",
    )
    with pytest.raises(
        ProjectionConfigurationError,
        match="grants an effect",
    ):
        load_projection_source_locks(unsafe)
