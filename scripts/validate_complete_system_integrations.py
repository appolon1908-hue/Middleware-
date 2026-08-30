#!/usr/bin/env python3
"""Fail-closed validation for the complete Codestra integration authority."""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PATHS = {
    "registry": ROOT / "config/system-integration-registry.v3.json",
    "cells": ROOT / "config/integration-cells.v1.json",
    "status": ROOT / "config/integration-status.v1.json",
    "authorities": ROOT / "config/repository-authorities.v1.json",
    "adapters": ROOT / "config/adapter-registry.v2.json",
    "capabilities": ROOT / "config/capabilities.v2.json",
    "callers": ROOT / "config/control-plane-callers.v1.json",
    "products": ROOT / "config/product-integration-clients.v1.json",
    "workstream": ROOT / "config/complete-system-workstream.v1.json",
}
EXPECTED_COLUMNS = ["id","repository","category","lifecycle","cell","integration_mode","middleware_relationship","source_state","canonical","adapter_id"]
EXPECTED_CRITICAL = {
    "middleware":"appolon1908-hue/Middleware-","caddy":"appolon1908-hue/Caddy",
    "kong":"appolon1908-hue/Kong","keycloak":"appolon1908-hue/Keycloak",
    "n8n":"appolon1908-hue/N8N","odoo":"appolon1908-hue/Odoo",
    "telnexa-sms":"appolon1908-hue/telnexa","klyrow-email":"appolon1908-hue/klyrow.com",
    "kyqra-crawler":"appolon1908-hue/kyqra-crawler",
    "vicidial-asterisk":"appolon1908-hue/Vicidialer-Codestra",
    "provisioning":"appolon1908-hue/codestra-provisioning-service",
    "sdk":"appolon1908-hue/SDK-repository","social":"appolon1908-hue/social.codestra.co",
    "infrastructure":"appolon1908-hue/Infustruction-repo",
    "communications-architecture":"appolon1908-hue/communication-platform-",
}
REFERENCE = "appolon1908-hue/codestra-production-platform"
LEGACY = {"scrapper-legacy","kyqra-legacy","codestraxxxx"}
PLANNED = {"marketing-control-plane","communications-control-center","social-control-plane","ai-control-plane"}
EFFECTFUL_MODES = {"provider-adapter","business-system-adapter","product-adapter-nonfinancial"}

def fail(message: str) -> None:
    raise SystemExit(f"COMPLETE_SYSTEM_INTEGRATION_ERROR={message}")

def require(value: bool, message: str) -> None:
    if not value:
        fail(message)

def load(name: str) -> dict[str, Any]:
    path = PATHS[name]
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        fail(f"missing_file:{path.relative_to(ROOT)}")
    except json.JSONDecodeError as exc:
        fail(f"invalid_json:{path.relative_to(ROOT)}:{exc.lineno}:{exc.colno}")
    require(isinstance(raw, dict), f"root_not_object:{name}")
    return raw

def validate_registry() -> tuple[dict[str, dict[str, Any]], set[str]]:
    raw = load("registry")
    require(raw.get("schema_version") == "3.0", "unsupported_registry_schema")
    inventory = raw.get("inventory")
    require(isinstance(inventory, dict), "missing_inventory")
    require(inventory.get("account") == "appolon1908-hue", "wrong_account")
    require(inventory.get("repository_count") == 54, "wrong_declared_repository_count")
    require(inventory.get("authority") == "appolon1908-hue/Middleware-", "wrong_registry_authority")
    require(raw.get("columns") == EXPECTED_COLUMNS, "registry_columns_drift")
    policy = raw.get("policy")
    require(isinstance(policy, dict), "missing_registry_policy")
    for key in (
        "middleware_is_only_cross_system_write_authority","principal_repository_owns_runtime",
        "sdk_repository_is_contract_authority","n8n_is_orchestration_only",
        "provider_callbacks_terminate_at_middleware","tenant_identity_is_derived_not_trusted_from_headers",
        "effectful_writes_require_idempotency","unknown_outcome_requires_readback_before_retry",
        "external_effects_disabled_by_default","frontends_never_hold_provider_credentials",
        "observability_is_read_only_for_business_state","legacy_and_placeholder_repositories_are_disabled",
        "documentation_merge_is_not_deployment_authorization",
    ):
        require(policy.get(key) is True, f"policy_disabled:{key}")
    rows = raw.get("systems")
    require(isinstance(rows, list) and len(rows) == 54, "wrong_system_count")
    by_id: dict[str, dict[str, Any]] = {}
    repositories: set[str] = set()
    adapters: set[str] = set()
    for index, row in enumerate(rows):
        require(isinstance(row, list) and len(row) == len(EXPECTED_COLUMNS), f"invalid_system_row:{index}")
        system = dict(zip(EXPECTED_COLUMNS, row, strict=True))
        sid, repo = system["id"], system["repository"]
        require(isinstance(sid, str) and sid and sid not in by_id, f"invalid_or_duplicate_system:{index}")
        require(isinstance(repo, str) and repo.startswith("appolon1908-hue/") and repo not in repositories,
                f"invalid_or_duplicate_repository:{sid}")
        require(isinstance(system["canonical"], bool), f"invalid_canonical:{sid}")
        require(isinstance(system["cell"], str) and system["cell"], f"missing_cell:{sid}")
        adapter_id = system["adapter_id"]
        require(adapter_id is None or isinstance(adapter_id, str), f"invalid_adapter_id:{sid}")
        if adapter_id is not None:
            require(adapter_id not in adapters, f"duplicate_adapter_binding:{adapter_id}")
            adapters.add(adapter_id)
        by_id[sid] = system
        repositories.add(repo)
    for sid, repo in EXPECTED_CRITICAL.items():
        require(sid in by_id and by_id[sid]["repository"] == repo, f"critical_repository_drift:{sid}")
    for sid in LEGACY:
        require(by_id[sid]["integration_mode"] == "disabled" and by_id[sid]["canonical"] is False,
                f"legacy_not_disabled:{sid}")
    for sid in PLANNED:
        require(by_id[sid]["source_state"] == "planned" and by_id[sid]["canonical"] is False,
                f"planned_state_invalid:{sid}")
    require(by_id["middleware"]["middleware_relationship"] == "authority", "middleware_not_authority")
    require(by_id["middleware"]["integration_mode"] == "middleware-authority", "middleware_mode_drift")
    require(by_id["codestra-production-platform"]["integration_mode"] == "reference-only", "reference_role_drift")
    return by_id, repositories

def validate_cells(by_id: dict[str, dict[str, Any]]) -> None:
    raw = load("cells")
    require(raw.get("schema_version") == "1.0", "unsupported_cells_schema")
    policy = raw.get("policy")
    require(isinstance(policy, dict) and policy.get("default") == "DENY", "cells_not_deny")
    require(policy.get("cross_cell_mutations_via_middleware_only") is True, "cross_cell_rule_disabled")
    require(policy.get("direct_database_links_across_cells") is False, "cross_cell_database_enabled")
    require(policy.get("live_effects_enabled") is False, "cell_live_effects_enabled")
    membership: dict[str, str] = {}
    cells = raw.get("cells")
    require(isinstance(cells, list) and cells, "missing_cells")
    for cell in cells:
        require(isinstance(cell, dict) and isinstance(cell.get("id"), str), "invalid_cell")
        cid = cell["id"]
        systems = cell.get("systems")
        require(isinstance(systems, list), f"cell_systems_not_array:{cid}")
        for sid in systems:
            require(sid in by_id and sid not in membership, f"invalid_cell_membership:{cid}:{sid}")
            membership[sid] = cid
    require(set(membership) == set(by_id), "cell_membership_incomplete")
    for sid, system in by_id.items():
        require(system["cell"] == membership[sid], f"registry_cell_drift:{sid}")

def validate_authorities(repositories: set[str]) -> None:
    raw = load("authorities")
    policy = raw.get("policy")
    require(raw.get("schema_version") == "1.0" and isinstance(policy, dict), "invalid_authorities")
    require(policy.get("middleware_repository") == "appolon1908-hue/Middleware-", "middleware_authority_drift")
    require(policy.get("reference_repository") == REFERENCE, "reference_repository_drift")
    require(policy.get("owning_repository_is_principal") is True, "principal_rule_disabled")
    require(policy.get("central_release_authority") is False, "central_release_authority_reintroduced")
    entries = raw.get("authorities")
    require(isinstance(entries, list) and entries, "missing_authorities")
    authority_repos: set[str] = set()
    components: set[str] = set()
    for entry in entries:
        require(isinstance(entry, dict), "invalid_authority_entry")
        component, repo = entry.get("component"), entry.get("principal_repository")
        require(isinstance(component, str) and component not in components, f"duplicate_authority:{component}")
        require(isinstance(repo, str) and repo.startswith("appolon1908-hue/") and repo not in authority_repos,
                f"invalid_authority_repository:{component}")
        require(repo != REFERENCE, f"reference_marked_principal:{component}")
        components.add(component); authority_repos.add(repo)
    refs = raw.get("reference_only")
    require(isinstance(refs, list) and len(refs) == 1 and refs[0].get("repository") == REFERENCE,
            "reference_only_contract_missing")
    require(authority_repos | {REFERENCE} == repositories, "authority_registry_repository_set_mismatch")

def validate_adapters(by_id: dict[str, dict[str, Any]]) -> None:
    raw = load("adapters")
    entries = raw.get("adapters")
    require(raw.get("schema_version") == "2.0" and isinstance(entries, list), "invalid_adapter_registry")
    registered: dict[str, dict[str, Any]] = {}
    repo_to_system = {s["repository"]: s for s in by_id.values()}
    for adapter in entries:
        require(isinstance(adapter, dict), "invalid_adapter")
        aid, repo = adapter.get("id"), adapter.get("repository")
        require(isinstance(aid, str) and aid not in registered, f"duplicate_adapter:{aid}")
        require(adapter.get("direct_n8n") is False, f"direct_n8n_adapter:{aid}")
        require(repo in repo_to_system, f"adapter_repository_not_registered:{aid}")
        require(repo_to_system[repo]["integration_mode"] in EFFECTFUL_MODES, f"adapter_mode_invalid:{aid}")
        require(repo_to_system[repo]["adapter_id"] == aid, f"adapter_binding_drift:{aid}")
        require(isinstance(adapter.get("command_prefixes"), list) and adapter["command_prefixes"],
                f"adapter_prefixes_missing:{aid}")
        registered[aid] = adapter
    manifests: set[str] = set()
    for path in sorted((ROOT / "connectors/manifests").glob("*.connector.json")):
        manifest = json.loads(path.read_text(encoding="utf-8"))
        aid = manifest.get("connector_id")
        require(aid in registered, f"manifest_not_registered:{aid}")
        require(manifest.get("enabled_by_default") is False, f"connector_enabled:{aid}")
        require(manifest.get("direct_n8n_access") is False, f"manifest_direct_n8n:{aid}")
        metadata = manifest.get("metadata")
        require(isinstance(metadata, dict) and metadata.get("runtime_activation_authorized") is False,
                f"manifest_activation_authorized:{aid}")
        manifests.add(aid)
    require(manifests == set(registered), "adapter_manifest_inventory_mismatch")
    callers = load("callers").get("callers")
    require(isinstance(callers, dict), "missing_callers")
    for caller_id, caller in callers.items():
        require(isinstance(caller, dict), f"invalid_caller:{caller_id}")
        targets = caller.get("allowed_targets"); prefixes = caller.get("allowed_command_prefixes")
        require(isinstance(targets, list) and isinstance(prefixes, list), f"invalid_caller_permissions:{caller_id}")
        require(all(target in registered for target in targets), f"caller_unknown_target:{caller_id}")
        supported = {p for target in targets for p in registered[target]["command_prefixes"]}
        require(all(prefix in supported for prefix in prefixes), f"caller_prefix_not_supported:{caller_id}")

def validate_products(repositories: set[str]) -> None:
    raw = load("products")
    policy = raw.get("policy")
    require(raw.get("schema_version") == "1.0" and isinstance(policy, dict), "invalid_product_registry")
    require(policy.get("frontends_hold_machine_credentials") is False, "frontend_machine_credentials_enabled")
    require(policy.get("direct_odoo_n8n_provider_access") is False, "product_direct_access_enabled")
    require(policy.get("live_effects_enabled") is False, "product_live_effects_enabled")
    callers = load("callers").get("callers")
    products = raw.get("products")
    require(isinstance(callers, dict) and isinstance(products, list), "missing_product_data")
    seen: set[str] = set()
    for product in products:
        pid = product.get("id")
        require(isinstance(pid, str) and pid not in seen, f"duplicate_product:{pid}")
        seen.add(pid)
        repos = product.get("repositories")
        require(isinstance(repos, list) and repos and all(r in repositories for r in repos), f"product_repo_invalid:{pid}")
        caller_id = product.get("caller_id")
        targets = product.get("allowed_targets"); prefixes = product.get("allowed_command_prefixes")
        require(isinstance(targets, list) and isinstance(prefixes, list), f"product_permissions_invalid:{pid}")
        if caller_id is None:
            require(not targets and not prefixes, f"public_product_has_machine_permissions:{pid}")
        else:
            require(caller_id in callers, f"product_caller_missing:{pid}:{caller_id}")
            require(targets == callers[caller_id].get("allowed_targets"), f"product_target_drift:{pid}")
            require(prefixes == callers[caller_id].get("allowed_command_prefixes"), f"product_prefix_drift:{pid}")

def validate_safety_and_docs() -> None:
    capability_map = load("capabilities").get("capabilities")
    require(isinstance(capability_map, dict) and capability_map and not any(capability_map.values()), "capability_enabled")
    status = load("status")
    overall = status.get("overall")
    require(isinstance(overall, dict) and overall.get("deployment_state") == "DISABLED", "deployment_not_disabled")
    require(overall.get("production_state") == "NO_GO", "production_not_no_go")
    for item in status.get("integrations", []):
        require(isinstance(item.get("done"), list), f"status_done_invalid:{item.get('id')}")
        require(isinstance(item.get("missing"), list) and item["missing"], f"status_missing_empty:{item.get('id')}")
    workstream = load("workstream")
    safety = workstream.get("safety")
    require(workstream.get("branch") == "integration/complete-system-registry-v3-20260830", "workstream_branch_drift")
    require(isinstance(safety, dict) and safety.get("source_only") is True, "workstream_not_source_only")
    require(safety.get("live_effects_enabled") is False and safety.get("deployment_authorized") is False
            and safety.get("production_authorized") is False, "workstream_effect_or_deployment_enabled")
    required = {
        "docs/integrations/COMPLETE_SYSTEM_INTEGRATION_MAP.md":["MIDDLEWARE_ONLY_CROSS_SYSTEM_WRITE_AUTHORITY=YES","REPOSITORY_COUNT=54","LIVE_EFFECTS_ENABLED=NO"],
        "docs/integrations/INTEGRATION_STATUS_AND_ROADMAP.md":["PRODUCTION_STATE=NO_GO","DEPLOYMENT_STATE=DISABLED"],
        "docs/integrations/ROUTE_EVENT_COMMAND_CATALOG.md":["Unknown outcomes are reconciled before resubmission"],
        "docs/integrations/CROSS_REPOSITORY_TEST_PLAN.md":["No test may enable a live provider effect"],
    }
    for relative, markers in required.items():
        path = ROOT / relative
        require(path.exists(), f"missing_document:{relative}")
        text = path.read_text(encoding="utf-8")
        require(all(marker in text for marker in markers), f"missing_document_marker:{relative}")

def main() -> None:
    by_id, repos = validate_registry()
    validate_cells(by_id)
    validate_authorities(repos)
    validate_adapters(by_id)
    validate_products(repos)
    validate_safety_and_docs()
    print("COMPLETE_SYSTEM_INTEGRATION_REGISTRY=PASS")
    print("REPOSITORY_COUNT=54")
    print("MIDDLEWARE_ONLY_CROSS_SYSTEM_WRITE_AUTHORITY=YES")
    print("DIRECT_N8N_PROVIDER_ACCESS=NO")
    print("LIVE_EFFECTS_ENABLED=NO")
    print("DEPLOYMENT_STATE=DISABLED")
    print("PRODUCTION_STATE=NO_GO")

if __name__ == "__main__":
    main()
