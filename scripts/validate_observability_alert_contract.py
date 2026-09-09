#!/usr/bin/env python3
"""Validate the fixed-recipient observability alert source contract."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Never, cast

ROOT = Path(__file__).resolve().parents[1]

POLICY_SCALARS: dict[str, object] = {
    "schema_version": "1.0",
    "policy_id": "codestra-observability-alert-mail-v1",
    "tenant_id": "codestra-platform",
    "receiver": "codestra-observability-email",
    "recipient_policy_id": "codestra-observability-admin-v1",
    "sender_policy_id": "codestra-alert-sender-v1",
    "recipient": "appolon@codestra.co",
    "sender": "alerts@codestra.co",
    "reply_to": "appolon@codestra.co",
    "warning_group_wait_seconds": 300,
    "warning_repeat_interval_seconds": 14400,
    "max_alerts_per_request": 1,
    "max_body_bytes": 131072,
    "normal_delivery_path": "middleware-klyrow-adapter",
    "direct_smtp_allowed": False,
    "delivery_enabled_by_default": False,
}
POLICY_LISTS = {
    "allowed_environments": ["production"],
    "allowed_severities": ["critical", "high", "warning", "info"],
    "immediate_severities": ["critical", "high"],
    "grouped_severities": ["warning"],
    "state_only_severities": ["info"],
}
CALLER_CONTRACTS: dict[str, dict[str, object]] = {
    "alertmanager-service": {
        "command_scope": "observability.alerts.write",
        "status_scope": "observability.alerts.read",
        "allowed_command_prefixes": ["observability.alert."],
        "allowed_targets": ["klyrow-alert-email"],
        "compatibility_only": False,
        "staging_auth_matrix": True,
    },
    "klyrow-alert-adapter": {
        "command_scope": "observability.alerts.events.write",
        "status_scope": "observability.alerts.read",
        "allowed_command_prefixes": ["observability.alert."],
        "allowed_targets": ["klyrow-alert-email"],
        "compatibility_only": False,
        "staging_auth_matrix": True,
    },
    "observability-operator": {
        "command_scope": "observability.incidents.write",
        "status_scope": "observability.incidents.read",
        "connector_commands_allowed": False,
        "allowed_command_prefixes": [],
        "allowed_targets": [],
        "compatibility_only": False,
        "staging_auth_matrix": True,
    },
}
COMMAND_CONTRACT: dict[str, object] = {
    "connector_id": "klyrow-alert-email",
    "prefix": "observability.alert.",
    "readback_required": True,
    "required_capability": "OBSERVABILITY_ALERT_EMAIL_DELIVERY",
    "timeout_seconds": 30,
    "unknown_outcome_requires_readback": True,
}
ADAPTER_CONTRACT: dict[str, object] = {
    "id": "klyrow-alert-email",
    "cell": "core-communications",
    "repository": "appolon1908-hue/klyrow.com",
    "command_prefixes": ["observability.alert."],
    "direct_n8n": False,
}
REQUIRED_PATHS = {
    "/health",
    "/readiness",
    "/version",
    "/capabilities",
    "/v1/integrations/alertmanager/events",
    "/v1/integrations/alertmanager/status-events",
    "/v1/observability/alerts",
    "/v1/observability/alerts/{operation_id}",
    "/v1/observability/alerts/{operation_id}/events",
    "/v1/observability/incidents",
    "/v1/observability/incidents/{incident_id}",
    "/v1/observability/incidents/{incident_id}/timeline",
    "/v1/observability/incidents/{incident_id}/notification-attempts",
    "/v1/observability/incidents/{incident_id}/acknowledge",
    "/v1/observability/incidents/{incident_id}/resolve",
    "/v1/observability/incidents/{incident_id}/reopen",
    "/v1/observability/alert-delivery-events",
    "/metrics",
}


def fail(message: str) -> Never:
    raise SystemExit(f"OBSERVABILITY_ALERT_CONTRACT=FAIL {message}")


def unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate key: {key}")
        result[key] = value
    return result


def reject_nonstandard_json_constant(value: str) -> Never:
    raise ValueError(f"non-standard JSON constant: {value}")


def load_object(root: Path, relative: str) -> dict[str, Any]:
    path = root / relative
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=unique_json_object,
            parse_constant=reject_nonstandard_json_constant,
        )
    except (OSError, UnicodeError, ValueError) as error:
        fail(f"invalid_json:{relative}:{error}")
    if not isinstance(value, dict):
        fail(f"invalid_object:{relative}")
    return cast(dict[str, Any], value)


def read_text(root: Path, relative: str) -> str:
    try:
        return (root / relative).read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        fail(f"invalid_text:{relative}:{error}")


def require_object(value: object, message: str) -> dict[str, Any]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        fail(message)
    return cast(dict[str, Any], value)


def require_list(value: object, message: str) -> list[Any]:
    if not isinstance(value, list):
        fail(message)
    return cast(list[Any], value)


def require_string(value: object, message: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        fail(message)
    return cast(str, value)


def require_string_list(value: object, message: str) -> list[str]:
    items = [require_string(item, message) for item in require_list(value, message)]
    if len(items) != len(set(items)):
        fail(message)
    return items


def require_exact_record(
    record: dict[str, Any], expected: dict[str, object], message: str
) -> None:
    if set(record) != set(expected):
        fail(f"{message}:fields")
    for key, expected_value in expected.items():
        observed = record.get(key)
        if type(observed) is not type(expected_value) or observed != expected_value:
            fail(f"{message}:{key}")


def require_record_list(value: object, message: str) -> list[dict[str, Any]]:
    return [
        require_object(item, f"{message}:{index}")
        for index, item in enumerate(require_list(value, message))
    ]


def find_exact_record(
    records: list[dict[str, Any]], key: str, value: str, message: str
) -> dict[str, Any]:
    matches = [record for record in records if record.get(key) == value]
    if len(matches) != 1:
        fail(f"{message}:count={len(matches)}")
    return matches[0]


def validate(root: Path = ROOT) -> tuple[int, int]:
    policy = load_object(root, "config/observability-alert-policy.v1.json")
    if set(policy) != set(POLICY_SCALARS) | set(POLICY_LISTS):
        fail("policy_fields_drifted")
    for key, expected in POLICY_SCALARS.items():
        observed = policy.get(key)
        if type(observed) is not type(expected) or observed != expected:
            fail(f"policy_field_drifted:{key}")
    for key, expected in POLICY_LISTS.items():
        if (
            require_string_list(policy.get(key), f"invalid_policy_list:{key}")
            != expected
        ):
            fail(f"policy_list_drifted:{key}")

    capability_registry = load_object(root, "config/capabilities.v2.json")
    if capability_registry.get("schema_version") != "2.0":
        fail("capability_registry_schema_drifted")
    capabilities = require_object(
        capability_registry.get("capabilities"), "invalid_capability_registry"
    )
    if not capabilities:
        fail("empty_capability_registry")
    if capabilities.get("OBSERVABILITY_ALERT_EMAIL_DELIVERY") is not False:
        fail("alert_capability_must_default_false")
    if any(value is not False for value in capabilities.values()):
        fail("all_repository_capabilities_must_remain_false")

    caller_registry = load_object(root, "config/control-plane-callers.v1.json")
    if caller_registry.get("schema_version") != "1.0":
        fail("caller_registry_schema_drifted")
    callers = require_object(caller_registry.get("callers"), "invalid_caller_registry")
    for caller_id, expected in CALLER_CONTRACTS.items():
        caller = require_object(callers.get(caller_id), f"missing_caller:{caller_id}")
        require_exact_record(caller, expected, f"caller_drifted:{caller_id}")

    command_registry = load_object(
        root, "connectors/generated/command-registry.v1.json"
    )
    if command_registry.get("schema_version") != "1.0":
        fail("command_registry_schema_drifted")
    commands = require_record_list(
        command_registry.get("commands"), "invalid_command_registry"
    )
    command = find_exact_record(
        commands,
        "prefix",
        "observability.alert.",
        "alert_command_policy_missing_or_duplicate",
    )
    require_exact_record(command, COMMAND_CONTRACT, "alert_command_policy_drifted")

    adapter_registry = load_object(root, "config/adapter-registry.v2.json")
    if adapter_registry.get("schema_version") != "2.0":
        fail("adapter_registry_schema_drifted")
    adapters = require_record_list(
        adapter_registry.get("adapters"), "invalid_adapter_registry"
    )
    adapter = find_exact_record(
        adapters,
        "id",
        "klyrow-alert-email",
        "alert_adapter_missing_or_duplicate",
    )
    require_exact_record(adapter, ADAPTER_CONTRACT, "alert_adapter_drifted")

    contract_source = read_text(
        root, "contracts/observability/alert-api.v1.openapi.yaml"
    )
    route_entries = re.findall(r"^  (/[^:]+):\s*$", contract_source, flags=re.MULTILINE)
    if len(route_entries) != len(set(route_entries)):
        fail("duplicate_openapi_route")
    if set(route_entries) != REQUIRED_PATHS:
        fail("openapi_route_inventory_drifted")

    compose_source = read_text(
        root, "deploy/observability-alerts/compose.core-production.yaml"
    )
    service_match = re.search(
        r"^  observability-alert-api:\n(?P<body>.*?)"
        r"(?=^  [A-Za-z0-9_.-]+:\s*$|^\S|\Z)",
        compose_source,
        flags=re.MULTILINE | re.DOTALL,
    )
    if service_match is None:
        fail("observability_alert_compose_service_missing")
    service_source = service_match.group("body")
    image_authority = (
        "image: ${MIDDLEWARE_IMAGE:?set exact registry/repository@sha256:<digest>}"
    )
    if (
        re.search(
            rf"^    {re.escape(image_authority)}\s*$",
            service_source,
            flags=re.MULTILINE,
        )
        is None
    ):
        fail("production_image_must_require_immutable_digest")
    for pattern, label in (
        (r"^    read_only:\s*true\s*$", "read_only"),
        (r"^    cap_drop:\s*\[ALL\]\s*$", "cap_drop"),
        (r"^      - no-new-privileges:true\s*$", "no_new_privileges"),
        (r'^    user:\s*["\']65532:65532["\']\s*$', "unprivileged_user"),
    ):
        if re.search(pattern, service_source, flags=re.MULTILINE) is None:
            fail(f"container_hardening_drifted:{label}")
    for pattern, label in (
        (r"^    ports:\s*", "host_port"),
        (r'^    privileged:\s*["\']?true["\']?\s*$', "privileged"),
        (r'^    network_mode:\s*["\']?host["\']?\s*$', "host_network"),
        (r'^    pid:\s*["\']?host["\']?\s*$', "host_pid"),
    ):
        if re.search(pattern, service_source, flags=re.MULTILINE | re.IGNORECASE):
            fail(f"container_boundary_forbidden:{label}")

    api_source = "".join(
        read_text(root, relative)
        for relative in (
            "app/observability_alerts.py",
            "app/observability_alert_contract.py",
            "app/observability_incidents.py",
        )
    )
    adapter_source = read_text(root, "app/klyrow_alert_adapter.py")
    worker_source = read_text(root, "workers/run_temporal.py")
    required_api_markers = (
        'COMMAND_TYPE = "observability.alert.email.send.v1"',
        'COMMAND_TARGET = "klyrow-alert-email"',
        'COMMAND_CAPABILITY = "OBSERVABILITY_ALERT_EMAIL_DELIVERY"',
        "recipient_policy_id",
        "direct_smtp_allowed",
        'authoritative_completion": "provider-readback"',
        "PostgresIncidentStore",
        "request_idempotency_key",
        "X-Source-Deployment",
    )
    for marker in required_api_markers:
        if marker not in api_source:
            fail(f"alert_api_marker_missing:{marker}")

    migration = read_text(root, "migrations/0009_observability_incidents.sql")
    for marker in (
        "middleware_observability_incidents",
        "middleware_observability_incident_events",
        "middleware_observability_incident_audit",
        "middleware_observability_notification_intents",
        "middleware_observability_incident_mutations",
        "request_idempotency_key",
        "notification_repeat",
        "notification_suppressed",
        "REFERENCES middleware_commands(tenant_id,command_id)",
    ):
        if marker not in migration:
            fail(f"incident_migration_marker_missing:{marker}")
    for marker in (
        'MESSAGE_PATH = "/v1/email/messages"',
        'MESSAGE_STATUS_PATH = "/v1/email/messages/{message_id}"',
        'CLIENT_ID = "middleware-alert-delivery"',
        '"appolon@codestra.co"',
        '"alerts@codestra.co"',
        "general LIVE_EMAIL_DELIVERY must remain disabled",
    ):
        if marker not in adapter_source:
            fail(f"klyrow_alert_adapter_marker_missing:{marker}")
    if "KlyrowAlertAdapter(settings)" not in worker_source:
        fail("temporal_worker_alert_adapter_missing")

    serialized = "\n".join(
        read_text(root, relative).casefold()
        for relative in (
            "config/observability-alert-policy.v1.json",
            "deploy/observability-alerts/compose.core-production.yaml",
            "deploy/observability-alerts/production.env.example",
        )
    )
    for pattern, label in (
        (r"\bsmtp_(?:password|username)\s*[:=]", "direct_smtp_credential"),
        (r"\bclient_secret\s*[:=]", "inline_client_secret"),
    ):
        if re.search(pattern, serialized):
            fail(f"secret_bearing_alert_configuration:{label}")

    return len(REQUIRED_PATHS), len(capabilities)


def main() -> None:
    route_count, capability_count = validate()
    print("OBSERVABILITY_ALERT_CONTRACT=PASS")
    print(f"OBSERVABILITY_ALERT_ROUTES={route_count}")
    print(f"REPOSITORY_CAPABILITIES_DISABLED={capability_count}")
    print("ALERT_RECIPIENT=appolon@codestra.co")
    print("ALERT_SENDER=alerts@codestra.co")
    print("DIRECT_SMTP_ALLOWED=NO")
    print("ALERT_DELIVERY_DEFAULT=DISABLED")


if __name__ == "__main__":
    main()
