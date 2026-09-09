from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/validate_system_integration_registry.py"


def load_validator() -> ModuleType:
    spec = importlib.util.spec_from_file_location("system_integration_registry_validator", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def validator() -> ModuleType:
    return load_validator()


@pytest.fixture
def documents(validator: ModuleType) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    return (
        validator.load_object(validator.REGISTRY_PATH),
        validator.load_object(validator.AUTHORITY_PATH),
        validator.load_object(validator.ALIAS_PATH),
    )


def system(registry: dict[str, Any], component: str) -> dict[str, Any]:
    return next(item for item in registry["systems"] if item["component"] == component)


def authority(authorities: dict[str, Any], component: str) -> dict[str, Any]:
    return next(item for item in authorities["authorities"] if item["component"] == component)


def assert_rejected(
    validator: ModuleType,
    registry: dict[str, Any],
    authorities: dict[str, Any],
    aliases: dict[str, Any],
    match: str,
) -> None:
    with pytest.raises(validator.RegistryError, match=match):
        validator.validate(registry, authorities, aliases)


def test_current_registry_passes_and_derives_counts(validator: ModuleType, documents) -> None:
    registry, authorities, aliases = documents
    summary = validator.validate(registry, authorities, aliases)
    assert summary["systems"] == len(registry["systems"])
    assert summary["aliases"] == len(aliases["mappings"])
    assert summary["adapters"] == len(
        {item["adapter_id"] for item in registry["systems"] if item["adapter_id"] is not None}
    )
    assert summary["cells"] == len({item["cell"] for item in registry["systems"]})


def test_duplicate_repository_id_is_rejected(validator: ModuleType, documents) -> None:
    registry, authorities, aliases = copy.deepcopy(documents)
    registry["systems"][1]["github_repository_id"] = registry["systems"][0]["github_repository_id"]
    assert_rejected(validator, registry, authorities, aliases, "duplicate repository id")


def test_duplicate_current_repository_name_is_rejected(validator: ModuleType, documents) -> None:
    registry, authorities, aliases = copy.deepcopy(documents)
    registry["systems"][1]["current_repository"] = registry["systems"][0]["current_repository"]
    assert_rejected(validator, registry, authorities, aliases, "duplicate repository name")


def test_missing_authority_component_is_rejected(validator: ModuleType, documents) -> None:
    registry, authorities, aliases = copy.deepcopy(documents)
    authorities["authorities"] = authorities["authorities"][:-1]
    assert_rejected(validator, registry, authorities, aliases, "component coverage differ")


def test_authority_role_drift_is_rejected(validator: ModuleType, documents) -> None:
    registry, authorities, aliases = copy.deepcopy(documents)
    authority(authorities, "odoo")["role"] = "untrusted-central-runtime"
    assert_rejected(validator, registry, authorities, aliases, "authority role mismatch: odoo")


def test_authority_repository_name_drift_is_rejected(validator: ModuleType, documents) -> None:
    registry, authorities, aliases = copy.deepcopy(documents)
    authority(authorities, "n8n")["principal_repository"] = "appolon1908-hue/Middleware-"
    assert_rejected(validator, registry, authorities, aliases, "authority repository mismatch: n8n")


def test_controlled_rename_id_misbinding_is_rejected(validator: ModuleType, documents) -> None:
    registry, authorities, aliases = copy.deepcopy(documents)
    authority(authorities, "platform-infrastructure")["github_repository_id"] = 1
    assert_rejected(validator, registry, authorities, aliases, "authority repository id mismatch")


def test_alias_target_drift_is_rejected(validator: ModuleType, documents) -> None:
    registry, authorities, aliases = copy.deepcopy(documents)
    aliases["mappings"][0]["target_repository_after_cutover"] = "appolon1908-hue/other-target"
    assert_rejected(validator, registry, authorities, aliases, "registry alias target mismatch")


def test_alias_status_must_remain_prepared_not_renamed(validator: ModuleType, documents) -> None:
    registry, authorities, aliases = copy.deepcopy(documents)
    aliases["mappings"][0]["status"] = "RENAMED"
    assert_rejected(validator, registry, authorities, aliases, "invalid alias mapping status")


def test_n8n_cannot_become_provider_adapter(validator: ModuleType, documents) -> None:
    registry, authorities, aliases = copy.deepcopy(documents)
    n8n = system(registry, "n8n")
    n8n["cell"] = "communications"
    n8n["integration_mode"] = "provider-adapter"
    n8n["middleware_relationship"] = "target-and-event-source"
    n8n["adapter_id"] = "n8n-direct-provider"
    assert_rejected(validator, registry, authorities, aliases, "n8n must remain in the automation cell")


def test_provider_adapter_requires_adapter_binding(validator: ModuleType, documents) -> None:
    registry, authorities, aliases = copy.deepcopy(documents)
    system(registry, "telnexa-sms")["adapter_id"] = None
    assert_rejected(validator, registry, authorities, aliases, "provider adapter lacks adapter id")


def test_provider_adapter_cannot_bypass_middleware_relationship(validator: ModuleType, documents) -> None:
    registry, authorities, aliases = copy.deepcopy(documents)
    system(registry, "klyrow-email")["middleware_relationship"] = "caller"
    assert_rejected(validator, registry, authorities, aliases, "provider adapter bypass relationship")


def test_duplicate_adapter_binding_is_rejected(validator: ModuleType, documents) -> None:
    registry, authorities, aliases = copy.deepcopy(documents)
    system(registry, "social")["adapter_id"] = system(registry, "telnexa-sms")["adapter_id"]
    assert_rejected(validator, registry, authorities, aliases, "duplicate adapter id")


def test_disabled_legacy_system_cannot_retain_write_relationship(validator: ModuleType, documents) -> None:
    registry, authorities, aliases = copy.deepcopy(documents)
    system(registry, "scrapper")["middleware_relationship"] = "caller"
    assert_rejected(validator, registry, authorities, aliases, "disabled system retains Middleware relationship")


def test_unknown_cell_is_rejected(validator: ModuleType, documents) -> None:
    registry, authorities, aliases = copy.deepcopy(documents)
    system(registry, "marketing")["cell"] = "unreviewed-cross-system-cell"
    assert_rejected(validator, registry, authorities, aliases, "unsupported cell")


def test_fail_closed_policy_cannot_be_disabled(validator: ModuleType, documents) -> None:
    registry, authorities, aliases = copy.deepcopy(documents)
    registry["policy"]["runtime_certification_is_not_embedded"] = False
    assert_rejected(validator, registry, authorities, aliases, "registry policy must fail closed")


def test_hard_coded_inventory_count_is_rejected_as_schema_drift(validator: ModuleType, documents) -> None:
    registry, authorities, aliases = copy.deepcopy(documents)
    registry["repository_count"] = len(registry["systems"])
    assert_rejected(validator, registry, authorities, aliases, "registry top-level field inventory mismatch")
