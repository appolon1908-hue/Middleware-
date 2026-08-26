#!/usr/bin/env python3
"""Validate the sole cross-system write boundary and Odoo ownership contract."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "config" / "system-ownership.json"
MUTATION_SCHEMA_PATH = ROOT / "contracts" / "mutation-command.schema.json"
HTTP_CONVENTIONS_PATH = ROOT / "contracts" / "http-conventions.md"
BOUNDARY_DOC_PATH = ROOT / "docs" / "WRITE-BOUNDARY-AND-OWNERSHIP.md"

REQUIRED_MIDDLEWARE_OWNERSHIP = {
    "service_authorization",
    "tenant_isolation",
    "contract_validation",
    "event_normalization",
    "idempotency",
    "semantic_replay_detection",
    "correlation_ids",
    "signed_webhook_inbox",
    "transactional_outbox",
    "retry_and_backoff",
    "dead_letter_queues",
    "circuit_breakers",
    "consent_and_suppression_checks",
    "provider_adapters",
    "odoo_mappings",
    "n8n_trigger_contracts",
    "telephony_command_records",
    "audit_and_reconciliation",
}

REQUIRED_ODOO_OWNERSHIP = {
    "customers_and_contacts",
    "leads_and_opportunities",
    "activities_and_campaigns",
    "call_history",
    "post_call_forms_and_notes",
    "callbacks_and_appointments",
    "consent_and_communication_preferences",
    "sms_and_email_history",
    "delivery_results",
    "agent_and_supervisor_business_views",
    "business_reporting",
}

REQUIRED_MUTATION_FIELDS = {
    "specversion",
    "command_id",
    "command_type",
    "schema_version",
    "tenant_id",
    "actor",
    "target",
    "operation",
    "requested_at",
    "correlation_id",
    "causation_id",
    "idempotency_key",
    "semantic_fingerprint",
    "policy_context",
    "payload",
}

REQUIRED_MUTATING_CONTROLS = {
    "service_authorization_required": True,
    "tenant_authorization_required": True,
    "contract_validation_required": True,
    "idempotency_required": True,
    "semantic_replay_detection_required": True,
    "correlation_id_required": True,
    "causation_id_required": True,
    "audit_record_required": True,
    "transactional_outbox_for_external_effects": True,
    "durable_inbox_for_callbacks": True,
    "bounded_retry_and_dead_letter_required": True,
    "provider_reconciliation_after_unknown_outcome": True,
    "consent_and_suppression_required_when_applicable": True,
}

FORBIDDEN_N8N_NODE_MARKERS = {
    "n8n-nodes-base.odoo",
    "n8n-nodes-base.postgres",
    "n8n-nodes-base.mySql",
    "n8n-nodes-base.microsoftSql",
    "n8n-nodes-base.twilio",
    "n8n-nodes-base.emailSend",
}

ODOO_DATABASE_CREDENTIAL_RE = re.compile(
    r"\b(?:ODOO_(?:DB|DATABASE)_(?:HOST|PORT|NAME|USER|PASSWORD)|"
    r"ODOO_DATABASE_URL|ODOO_PG_DSN)\b",
    re.IGNORECASE,
)

SOURCE_SUFFIXES = {".py", ".js", ".ts", ".mjs", ".cjs", ".sh", ".yaml", ".yml", ".toml"}


def load_json(path: Path, errors: list[str]) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        errors.append(f"cannot load {path.relative_to(ROOT)}: {exc}")
        return None
    if not isinstance(value, dict):
        errors.append(f"{path.relative_to(ROOT)} root must be an object")
        return None
    return value


def string_set(value: Any, location: str, errors: list[str]) -> set[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        errors.append(f"{location} must be an array of strings")
        return set()
    if len(value) != len(set(value)):
        errors.append(f"{location} contains duplicates")
    return set(value)


def validate_policy(policy: dict[str, Any], errors: list[str]) -> None:
    if policy.get("version") != 1:
        errors.append("system ownership policy version must be 1")
    if policy.get("repository_role") != "sole_cross_system_write_boundary":
        errors.append("repository_role must declare the sole cross-system write boundary")
    if policy.get("orchestration_system") != "n8n":
        errors.append("orchestration_system must be n8n")
    if policy.get("business_system_of_record") != "odoo-19":
        errors.append("business_system_of_record must be odoo-19")

    ownership = policy.get("ownership")
    if not isinstance(ownership, dict):
        errors.append("ownership must be an object")
        ownership = {}

    middleware = string_set(ownership.get("middleware"), "ownership.middleware", errors)
    missing_middleware = sorted(REQUIRED_MIDDLEWARE_OWNERSHIP - middleware)
    if missing_middleware:
        errors.append(
            "Middleware ownership is incomplete: " + ", ".join(missing_middleware)
        )

    odoo = string_set(ownership.get("odoo-19"), "ownership.odoo-19", errors)
    missing_odoo = sorted(REQUIRED_ODOO_OWNERSHIP - odoo)
    if missing_odoo:
        errors.append("Odoo ownership is incomplete: " + ", ".join(missing_odoo))

    n8n = string_set(ownership.get("n8n"), "ownership.n8n", errors)
    if "workflow_orchestration" not in n8n:
        errors.append("n8n must own workflow_orchestration")

    mutating = policy.get("mutating_path_requirements")
    if not isinstance(mutating, dict):
        errors.append("mutating_path_requirements must be an object")
        mutating = {}
    if mutating.get("entrypoint") != "middleware":
        errors.append("every mutating path must enter through middleware")
    for key, expected in REQUIRED_MUTATING_CONTROLS.items():
        if mutating.get(key) is not expected:
            errors.append(f"mutating_path_requirements.{key} must be true")

    odoo_policy = policy.get("odoo_write_policy")
    if not isinstance(odoo_policy, dict):
        errors.append("odoo_write_policy must be an object")
        odoo_policy = {}
    interfaces = string_set(
        odoo_policy.get("approved_interfaces"),
        "odoo_write_policy.approved_interfaces",
        errors,
    )
    if interfaces != {"odoo_service_api", "odoo_orm_bridge"}:
        errors.append(
            "approved Odoo interfaces must be exactly odoo_service_api and "
            "odoo_orm_bridge"
        )
    for key in (
        "direct_postgresql_write_allowed",
        "external_service_database_credentials_allowed",
        "generic_model_write_endpoint_allowed",
    ):
        if odoo_policy.get(key) is not False:
            errors.append(f"odoo_write_policy.{key} must be false")
    for key in (
        "service_identity_required",
        "tenant_mapping_required",
        "idempotency_required",
    ):
        if odoo_policy.get(key) is not True:
            errors.append(f"odoo_write_policy.{key} must be true")

    n8n_policy = policy.get("n8n_policy")
    if not isinstance(n8n_policy, dict):
        errors.append("n8n_policy must be an object")
        n8n_policy = {}
    if n8n_policy.get("owns_orchestration_only") is not True:
        errors.append("n8n must own orchestration only")
    if (
        n8n_policy.get(
            "direct_mutating_calls_to_business_or_provider_systems_allowed"
        )
        is not False
    ):
        errors.append("n8n direct mutating calls must be forbidden")

    forbidden = string_set(
        policy.get("forbidden_write_paths"), "forbidden_write_paths", errors
    )
    required_forbidden = {
        "n8n_to_odoo",
        "n8n_to_provider",
        "external_service_to_odoo_postgresql",
        "external_service_to_provider_without_middleware",
        "browser_or_portal_to_odoo",
        "browser_or_portal_to_provider",
    }
    missing_forbidden = sorted(required_forbidden - forbidden)
    if missing_forbidden:
        errors.append(
            "forbidden write paths are incomplete: " + ", ".join(missing_forbidden)
        )


def validate_mutation_schema(schema: dict[str, Any], errors: list[str]) -> None:
    if schema.get("type") != "object":
        errors.append("mutation command schema type must be object")
    if schema.get("additionalProperties") is not False:
        errors.append("mutation command schema must reject unknown top-level fields")

    required = string_set(schema.get("required"), "mutation schema required", errors)
    missing = sorted(REQUIRED_MUTATION_FIELDS - required)
    if missing:
        errors.append("mutation command schema is missing: " + ", ".join(missing))

    properties = schema.get("properties")
    if not isinstance(properties, dict):
        errors.append("mutation command schema properties must be an object")
        return

    missing_properties = sorted(REQUIRED_MUTATION_FIELDS - set(properties))
    if missing_properties:
        errors.append(
            "mutation command schema has no definitions for: "
            + ", ".join(missing_properties)
        )

    specversion = properties.get("specversion")
    if not isinstance(specversion, dict) or specversion.get("const") != "1.0":
        errors.append("mutation command specversion must be fixed to 1.0")

    fingerprint = properties.get("semantic_fingerprint")
    if (
        not isinstance(fingerprint, dict)
        or fingerprint.get("pattern") != "^[a-f0-9]{64}$"
    ):
        errors.append("semantic_fingerprint must be a lowercase SHA-256 digest")


def validate_contract_text(errors: list[str]) -> None:
    required_files = (
        POLICY_PATH,
        MUTATION_SCHEMA_PATH,
        HTTP_CONVENTIONS_PATH,
        BOUNDARY_DOC_PATH,
    )
    for path in required_files:
        if not path.is_file():
            errors.append(f"missing write-boundary artifact: {path.relative_to(ROOT)}")
    if errors:
        return

    http_text = HTTP_CONVENTIONS_PATH.read_text(encoding="utf-8")
    for phrase in ("Idempotency-Key", "Every write is idempotent"):
        if phrase not in http_text:
            errors.append(f"HTTP conventions are missing required phrase: {phrase}")

    boundary_text = BOUNDARY_DOC_PATH.read_text(encoding="utf-8")
    for phrase in (
        "Middleware is the only component allowed",
        "n8n owns orchestration",
        "No external service may receive Odoo PostgreSQL write credentials",
    ):
        if phrase not in boundary_text:
            errors.append(f"write-boundary document is missing required phrase: {phrase}")


def iter_source_files() -> list[Path]:
    files: list[Path] = []
    for directory_name in ("app", "src", "middleware", "workers", "n8n", "workflows"):
        directory = ROOT / directory_name
        if not directory.is_dir():
            continue
        for path in directory.rglob("*"):
            if path.is_file() and path.suffix in SOURCE_SUFFIXES:
                files.append(path)
    return sorted(files)


def validate_no_odoo_database_credentials(errors: list[str]) -> None:
    for path in iter_source_files():
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            errors.append(f"cannot read source file {path.relative_to(ROOT)}: {exc}")
            continue
        if ODOO_DATABASE_CREDENTIAL_RE.search(text):
            errors.append(
                "direct Odoo database credential reference is forbidden: "
                f"{path.relative_to(ROOT)}"
            )


def walk_json(value: Any):
    yield value
    if isinstance(value, dict):
        for nested in value.values():
            yield from walk_json(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from walk_json(nested)


def validate_n8n_exports(errors: list[str]) -> None:
    workflow_paths: list[Path] = []
    for directory_name in ("n8n", "workflows"):
        directory = ROOT / directory_name
        if directory.is_dir():
            workflow_paths.extend(sorted(directory.rglob("*.json")))

    for path in workflow_paths:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            errors.append(f"cannot parse n8n workflow {path.relative_to(ROOT)}: {exc}")
            continue

        markers = {
            item
            for item in walk_json(value)
            if isinstance(item, str) and item in FORBIDDEN_N8N_NODE_MARKERS
        }
        if markers:
            errors.append(
                f"{path.relative_to(ROOT)} contains direct-effect n8n nodes: "
                + ", ".join(sorted(markers))
            )


def report(errors: list[str]) -> int:
    print("Write-boundary validation failed:", file=sys.stderr)
    for error in errors:
        print(f"  - {error}", file=sys.stderr)
    return 1


def main() -> int:
    errors: list[str] = []
    policy = load_json(POLICY_PATH, errors)
    schema = load_json(MUTATION_SCHEMA_PATH, errors)
    validate_contract_text(errors)
    if policy is not None:
        validate_policy(policy, errors)
    if schema is not None:
        validate_mutation_schema(schema, errors)
    validate_no_odoo_database_credentials(errors)
    validate_n8n_exports(errors)

    if errors:
        return report(errors)

    print(
        "Write-boundary validation passed: Middleware is the sole mutation "
        "boundary, n8n is orchestration-only, and Odoo writes require the "
        "approved service API or ORM bridge."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
