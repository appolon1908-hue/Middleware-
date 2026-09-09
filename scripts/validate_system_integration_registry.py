#!/usr/bin/env python3
"""Validate the stable-ID system integration registry against current authorities."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "config/system-integration-registry.v4.json"
AUTHORITY_PATH = ROOT / "config/repository-authorities.v1.json"
ALIAS_PATH = ROOT / "config/repository-name-aliases.v1.json"

REPOSITORY_RE = re.compile(r"^appolon1908-hue/[A-Za-z0-9._-]+$")
REGISTRY_KEYS = {
    "schema_version",
    "identity_key",
    "authority_source",
    "name_alias_source",
    "scope",
    "policy",
    "systems",
}
POLICY_KEYS = {
    "counts_are_derived",
    "repository_names_are_mutable_attributes",
    "repository_ids_are_immutable_identity",
    "release_state_is_not_embedded",
    "runtime_certification_is_not_embedded",
    "middleware_is_cross_system_command_authority",
    "n8n_is_orchestration_only",
    "provider_callbacks_terminate_at_middleware",
    "frontends_hold_no_provider_credentials",
    "documentation_is_not_deployment_authorization",
}
SYSTEM_KEYS = {
    "component",
    "github_repository_id",
    "current_repository",
    "authority_role",
    "lifecycle",
    "cell",
    "integration_mode",
    "middleware_relationship",
    "adapter_id",
    "name_aliases",
}
AUTHORITY_KEYS = {
    "component",
    "principal_repository",
    "role",
    "status",
    "github_repository_id",
    "target_repository_after_cutover",
    "rename_status",
}
ALIAS_MAPPING_KEYS = {
    "github_repository_id",
    "current_repository",
    "target_repository_after_cutover",
    "status",
}
REGISTRY_ALIAS_KEYS = {"repository", "status"}
ALLOWED_CELLS = {
    "middleware-core",
    "edge-identity",
    "automation",
    "communications",
    "product-clients",
    "crawler",
    "legacy-disabled",
    "telephony-restricted",
    "core-control-plane",
    "governance",
    "financial-isolated",
    "planned-control-planes",
}
ALLOWED_LIFECYCLES = {"active", "deprecated", "legacy-migration", "planned-name-review"}
ALLOWED_INTEGRATION_MODES = {
    "middleware-authority",
    "edge-compatibility",
    "gateway-compatibility",
    "identity-compatibility",
    "orchestration-client",
    "business-system-adapter",
    "provider-adapter",
    "public-intake-client",
    "disabled",
    "contract-authority",
    "product-client",
    "product-adapter-nonfinancial",
    "planned-client",
    "infrastructure-coordinator",
    "documentation-reference",
}
ALLOWED_RELATIONSHIPS = {
    "authority",
    "compatibility",
    "identity-authority",
    "caller",
    "target-and-event-source",
    "none",
    "governance",
    "caller-and-target",
}
PROVIDER_CELLS = {"communications", "crawler", "telephony-restricted", "core-control-plane"}

JsonObject = dict[str, Any]


class RegistryError(ValueError):
    """Raised when registry evidence is ambiguous or unsafe."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RegistryError(message)


def as_object(value: Any, label: str) -> JsonObject:
    require(isinstance(value, dict), f"{label} must be an object")
    return value


def as_list(value: Any, label: str) -> list[Any]:
    require(isinstance(value, list), f"{label} must be a list")
    return value


def load_object(path: Path) -> JsonObject:
    try:
        value: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RegistryError(f"cannot read valid JSON: {path}") from exc
    return as_object(value, str(path))


def valid_repository(value: Any) -> bool:
    return isinstance(value, str) and bool(REPOSITORY_RE.fullmatch(value))


def positive_repository_id(value: Any) -> bool:
    return type(value) is int and value > 0


def validate(
    registry: JsonObject,
    authorities: JsonObject,
    aliases: JsonObject,
) -> dict[str, int]:
    require(set(registry) == REGISTRY_KEYS, "registry top-level field inventory mismatch")
    require(registry.get("schema_version") == "4.0", "registry schema version mismatch")
    require(registry.get("identity_key") == "github_repository_id", "registry identity key mismatch")
    require(
        registry.get("authority_source") == "config/repository-authorities.v1.json",
        "registry authority source mismatch",
    )
    require(
        registry.get("name_alias_source") == "config/repository-name-aliases.v1.json",
        "registry alias source mismatch",
    )
    require(
        registry.get("scope") == "authority-backed systems on current protected main",
        "registry scope mismatch",
    )

    policy = as_object(registry.get("policy"), "registry policy")
    require(set(policy) == POLICY_KEYS, "registry policy field inventory mismatch")
    for key in sorted(POLICY_KEYS):
        require(policy.get(key) is True, f"registry policy must fail closed: {key}")

    systems_raw = as_list(registry.get("systems"), "registry systems")
    require(bool(systems_raw), "registry systems must not be empty")
    systems: list[JsonObject] = []
    system_by_component: dict[str, JsonObject] = {}
    system_by_id: dict[int, JsonObject] = {}
    repository_names: set[str] = set()
    adapter_ids: set[str] = set()

    for index, raw in enumerate(systems_raw):
        system = as_object(raw, f"registry system {index}")
        require(set(system) == SYSTEM_KEYS, f"registry system {index} field inventory mismatch")
        component = system.get("component")
        repository_id = system.get("github_repository_id")
        repository = system.get("current_repository")
        role = system.get("authority_role")
        lifecycle = system.get("lifecycle")
        cell = system.get("cell")
        mode = system.get("integration_mode")
        relationship = system.get("middleware_relationship")
        adapter = system.get("adapter_id")
        name_aliases = as_list(system.get("name_aliases"), f"registry aliases for {component}")

        require(isinstance(component, str) and bool(component), f"invalid component at index {index}")
        require(component not in system_by_component, f"duplicate component: {component}")
        require(positive_repository_id(repository_id), f"invalid repository id for {component}")
        require(repository_id not in system_by_id, f"duplicate repository id: {repository_id}")
        require(valid_repository(repository), f"invalid repository name for {component}")
        require(repository not in repository_names, f"duplicate repository name: {repository}")
        require(isinstance(role, str) and bool(role), f"invalid authority role for {component}")
        require(lifecycle in ALLOWED_LIFECYCLES, f"unsupported lifecycle for {component}: {lifecycle}")
        require(cell in ALLOWED_CELLS, f"unsupported cell for {component}: {cell}")
        require(mode in ALLOWED_INTEGRATION_MODES, f"unsupported integration mode for {component}: {mode}")
        require(
            relationship in ALLOWED_RELATIONSHIPS,
            f"unsupported Middleware relationship for {component}: {relationship}",
        )
        require(adapter is None or (isinstance(adapter, str) and bool(adapter)), f"invalid adapter id for {component}")
        if isinstance(adapter, str):
            require(adapter not in adapter_ids, f"duplicate adapter id: {adapter}")
            adapter_ids.add(adapter)
        for alias_index, alias_raw in enumerate(name_aliases):
            alias = as_object(alias_raw, f"registry alias {component}[{alias_index}]")
            require(set(alias) == REGISTRY_ALIAS_KEYS, f"registry alias field inventory mismatch: {component}")
            require(valid_repository(alias.get("repository")), f"invalid registry alias repository: {component}")
            require(alias.get("status") == "PREPARED_NOT_RENAMED", f"invalid registry alias status: {component}")

        systems.append(system)
        system_by_component[component] = system
        system_by_id[repository_id] = system
        repository_names.add(repository)

    authority_policy = as_object(authorities.get("policy"), "repository authority policy")
    require(
        authority_policy.get("repository_identity_key") == registry.get("identity_key"),
        "authority identity key differs from registry",
    )
    require(
        authority_policy.get("repository_name_migration_manifest") == registry.get("name_alias_source"),
        "authority rename manifest differs from registry",
    )

    authority_raw = as_list(authorities.get("authorities"), "repository authorities")
    authority_by_component: dict[str, JsonObject] = {}
    authority_rename_ids: set[int] = set()
    for index, raw in enumerate(authority_raw):
        authority = as_object(raw, f"authority {index}")
        require(set(authority) <= AUTHORITY_KEYS, f"authority {index} contains unsupported fields")
        require(
            {"component", "principal_repository", "role"} <= set(authority),
            f"authority {index} is incomplete",
        )
        component = authority.get("component")
        require(isinstance(component, str) and bool(component), f"invalid authority component at {index}")
        require(component not in authority_by_component, f"duplicate authority component: {component}")
        require(valid_repository(authority.get("principal_repository")), f"invalid authority repository: {component}")
        require(isinstance(authority.get("role"), str) and bool(authority.get("role")), f"invalid authority role: {component}")
        authority_by_component[component] = authority

        rename_fields = {
            "github_repository_id",
            "target_repository_after_cutover",
            "rename_status",
        }
        present_rename_fields = rename_fields & set(authority)
        require(
            not present_rename_fields or present_rename_fields == rename_fields,
            f"partial authority rename binding: {component}",
        )
        if present_rename_fields:
            repository_id = authority.get("github_repository_id")
            require(positive_repository_id(repository_id), f"invalid authority rename repository id: {component}")
            require(repository_id not in authority_rename_ids, f"duplicate authority rename repository id: {repository_id}")
            require(
                valid_repository(authority.get("target_repository_after_cutover")),
                f"invalid authority rename target: {component}",
            )
            require(authority.get("rename_status") == "PREPARED_NOT_RENAMED", f"invalid authority rename status: {component}")
            authority_rename_ids.add(repository_id)

    require(
        set(authority_by_component) == set(system_by_component),
        "registry and repository-authority component coverage differ",
    )
    for component, system in system_by_component.items():
        authority = authority_by_component[component]
        require(
            authority.get("principal_repository") == system.get("current_repository"),
            f"authority repository mismatch: {component}",
        )
        require(authority.get("role") == system.get("authority_role"), f"authority role mismatch: {component}")
        if "github_repository_id" in authority:
            require(
                authority.get("github_repository_id") == system.get("github_repository_id"),
                f"authority repository id mismatch: {component}",
            )
        if authority.get("status") == "deprecated":
            require(system.get("lifecycle") == "deprecated", f"deprecated authority remains active: {component}")

    require(aliases.get("schema_version") == "1.0", "alias schema version mismatch")
    require(aliases.get("status") == "PREPARED_NOT_RENAMED", "alias manifest status mismatch")
    require(aliases.get("identity_key") == registry.get("identity_key"), "alias identity key differs from registry")
    require(aliases.get("historical_evidence_immutable") is True, "alias history immutability must be true")
    alias_raw = as_list(aliases.get("mappings"), "repository alias mappings")
    alias_by_id: dict[int, JsonObject] = {}
    alias_current_names: set[str] = set()
    alias_target_names: set[str] = set()
    for index, raw in enumerate(alias_raw):
        mapping = as_object(raw, f"alias mapping {index}")
        require(set(mapping) == ALIAS_MAPPING_KEYS, f"alias mapping {index} field inventory mismatch")
        repository_id = mapping.get("github_repository_id")
        current_repository = mapping.get("current_repository")
        target_repository = mapping.get("target_repository_after_cutover")
        require(positive_repository_id(repository_id), f"invalid alias repository id at {index}")
        require(repository_id not in alias_by_id, f"duplicate alias repository id: {repository_id}")
        require(valid_repository(current_repository), f"invalid alias current repository at {index}")
        require(valid_repository(target_repository), f"invalid alias target repository at {index}")
        require(current_repository not in alias_current_names, f"duplicate alias current repository: {current_repository}")
        require(target_repository not in alias_target_names, f"duplicate alias target repository: {target_repository}")
        require(mapping.get("status") == "PREPARED_NOT_RENAMED", f"invalid alias mapping status at {index}")
        alias_by_id[repository_id] = mapping
        alias_current_names.add(current_repository)
        alias_target_names.add(target_repository)

    require(set(alias_by_id) == authority_rename_ids, "alias mappings and authority rename bindings differ")
    for repository_id, system in system_by_id.items():
        registry_aliases = as_list(system.get("name_aliases"), f"registry aliases for id {repository_id}")
        mapping = alias_by_id.get(repository_id)
        if mapping is None:
            require(not registry_aliases, f"unregistered alias attached to repository id {repository_id}")
            continue
        require(system.get("current_repository") == mapping.get("current_repository"), f"alias current name mismatch: {repository_id}")
        require(len(registry_aliases) == 1, f"registry alias count mismatch: {repository_id}")
        registry_alias = as_object(registry_aliases[0], f"registry alias for id {repository_id}")
        require(
            registry_alias.get("repository") == mapping.get("target_repository_after_cutover"),
            f"registry alias target mismatch: {repository_id}",
        )
        require(registry_alias.get("status") == mapping.get("status"), f"registry alias status mismatch: {repository_id}")
        component = system.get("component")
        authority = authority_by_component[str(component)]
        require(
            authority.get("target_repository_after_cutover") == mapping.get("target_repository_after_cutover"),
            f"authority alias target mismatch: {component}",
        )
        require(authority.get("rename_status") == mapping.get("status"), f"authority alias status mismatch: {component}")

    middleware = system_by_component.get("middleware")
    require(middleware is not None, "middleware registry row is missing")
    require(middleware.get("cell") == "middleware-core", "Middleware must remain in middleware-core")
    require(middleware.get("integration_mode") == "middleware-authority", "Middleware authority mode drift")
    require(middleware.get("middleware_relationship") == "authority", "Middleware relationship drift")
    require(middleware.get("adapter_id") is None, "Middleware must not masquerade as a provider adapter")

    n8n = system_by_component.get("n8n")
    require(n8n is not None, "n8n registry row is missing")
    require(n8n.get("cell") == "automation", "n8n must remain in the automation cell")
    require(n8n.get("integration_mode") == "orchestration-client", "n8n must remain orchestration-only")
    require(n8n.get("middleware_relationship") == "caller", "n8n must call Middleware rather than providers")
    require(n8n.get("adapter_id") is None, "n8n must not own a provider adapter")

    for system in systems:
        component = str(system["component"])
        mode = system["integration_mode"]
        lifecycle = system["lifecycle"]
        cell = system["cell"]
        relationship = system["middleware_relationship"]
        adapter = system["adapter_id"]
        if mode == "provider-adapter":
            require(lifecycle == "active", f"provider adapter is not active: {component}")
            require(cell in PROVIDER_CELLS, f"provider adapter is in an invalid cell: {component}")
            require(relationship == "target-and-event-source", f"provider adapter bypass relationship: {component}")
            require(isinstance(adapter, str) and bool(adapter), f"provider adapter lacks adapter id: {component}")
        elif mode == "business-system-adapter":
            require(cell == "communications", f"business-system adapter cell drift: {component}")
            require(relationship == "target-and-event-source", f"business-system adapter relationship drift: {component}")
            require(isinstance(adapter, str) and bool(adapter), f"business-system adapter lacks adapter id: {component}")
        elif mode == "product-adapter-nonfinancial":
            require(cell == "financial-isolated", f"nonfinancial product adapter cell drift: {component}")
            require(relationship == "caller-and-target", f"nonfinancial product adapter relationship drift: {component}")
            require(isinstance(adapter, str) and bool(adapter), f"nonfinancial product adapter lacks adapter id: {component}")
        elif mode == "disabled":
            require(cell == "legacy-disabled", f"disabled system is outside legacy-disabled cell: {component}")
            require(relationship == "none", f"disabled system retains Middleware relationship: {component}")
            require(adapter is None, f"disabled system retains provider adapter: {component}")
            require(
                lifecycle in {"deprecated", "legacy-migration"},
                f"disabled system has active lifecycle: {component}",
            )
        elif adapter is not None:
            raise RegistryError(f"unexpected adapter binding for integration mode {mode}: {component}")

    return {
        "systems": len(systems),
        "aliases": len(alias_by_id),
        "adapters": len(adapter_ids),
        "cells": len({str(system["cell"]) for system in systems}),
    }


def main() -> int:
    try:
        summary = validate(
            load_object(REGISTRY_PATH),
            load_object(AUTHORITY_PATH),
            load_object(ALIAS_PATH),
        )
    except RegistryError as exc:
        print(f"SYSTEM_INTEGRATION_REGISTRY=FAIL reason={exc}", file=sys.stderr)
        return 1
    print(
        "SYSTEM_INTEGRATION_REGISTRY=PASS "
        f"systems={summary['systems']} aliases={summary['aliases']} "
        f"adapters={summary['adapters']} cells={summary['cells']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
