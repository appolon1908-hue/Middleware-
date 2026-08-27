#!/usr/bin/env python3
"""Validate the Connector SDK, manifests, capabilities, and API source."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from middleware.connector_sdk import ConnectorRegistry, ConnectorState  # noqa: E402
from middleware.connector_sdk.errors import ConnectorError  # noqa: E402
from middleware.connector_sdk.generation import (  # noqa: E402
    build_generated_artifacts,
    render_generated_artifact,
)


def load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    errors: list[str] = []
    manifest_dir = ROOT / "connectors" / "manifests"
    files = sorted(manifest_dir.glob("*.connector.json"))
    if len(files) != 8:
        errors.append(f"expected 8 connector manifests, found {len(files)}")

    registry = ConnectorRegistry()
    try:
        records = registry.load_directory(
            manifest_dir,
            state=ConnectorState.DECLARED,
        )
    except (OSError, ValueError, ConnectorError) as error:
        errors.append(f"cannot load connector manifests: {error}")
        records = ()

    errors.extend(registry.validate_global_invariants())

    manifest_ids = {record.manifest.connector_id for record in records}
    adapter_registry_path = ROOT / "config" / "adapter-registry.v2.json"
    if adapter_registry_path.is_file():
        raw_adapter_registry = load_json(adapter_registry_path)
        if not isinstance(raw_adapter_registry, dict):
            errors.append("config/adapter-registry.v2.json must be an object")
        else:
            adapters = raw_adapter_registry.get("adapters")
            if not isinstance(adapters, list):
                errors.append("adapter registry adapters must be an array")
            else:
                adapter_ids = {
                    item.get("id")
                    for item in adapters
                    if isinstance(item, dict)
                }
                if manifest_ids != adapter_ids:
                    errors.append(
                        "connector manifest IDs must exactly match the v2 "
                        f"adapter registry: manifests={sorted(manifest_ids)} "
                        f"registry={sorted(str(value) for value in adapter_ids)}"
                    )

    capabilities: dict[str, bool] = {}
    for path in (
        ROOT / "config" / "capabilities.v2.json",
        ROOT / "connectors" / "capabilities.v1.json",
    ):
        raw = load_json(path)
        if not isinstance(raw, dict):
            errors.append(f"{path.relative_to(ROOT)} must be an object")
            continue
        values = raw.get("capabilities")
        if not isinstance(values, dict):
            errors.append(
                f"{path.relative_to(ROOT)} capabilities must be an object"
            )
            continue
        for key, value in values.items():
            if not isinstance(key, str) or not isinstance(value, bool):
                errors.append(
                    f"{path.relative_to(ROOT)} has invalid capability {key!r}"
                )
                continue
            if value is not False:
                errors.append(
                    f"source capability must remain false: {key}={value}"
                )
            capabilities[key] = value

    for record in records:
        manifest = record.manifest
        if manifest.enabled_by_default or manifest.direct_n8n_access:
            errors.append(
                f"{manifest.connector_id} violates disabled/Middleware-only policy"
            )
        if manifest.runtime_binding.status != "UNVERIFIED_TEMPLATE_ONLY":
            errors.append(
                f"{manifest.connector_id} runtime binding is not source-only"
            )
        if not manifest.runtime_binding.base_url.endswith(".internal.invalid"):
            errors.append(
                f"{manifest.connector_id} source base URL is not reserved .invalid"
            )
        for command in manifest.command_policies:
            if (
                command.required_capability != "NONE"
                and command.required_capability not in capabilities
            ):
                errors.append(
                    f"{manifest.connector_id} references unknown capability "
                    f"{command.required_capability}"
                )

    expected_generated = build_generated_artifacts(manifest_dir)
    for name, data in expected_generated.items():
        path = ROOT / "connectors" / "generated" / name
        if not path.is_file():
            errors.append(f"missing generated artifact: {path.relative_to(ROOT)}")
        elif path.read_text(encoding="utf-8") != render_generated_artifact(data):
            errors.append(f"stale generated artifact: {path.relative_to(ROOT)}")

    schema = load_json(
        ROOT / "contracts" / "connectors" / "connector-manifest.v1.schema.json"
    )
    if not isinstance(schema, dict) or schema.get("$schema") != (
        "https://json-schema.org/draft/2020-12/schema"
    ):
        errors.append("connector manifest JSON Schema is missing or invalid")

    storage_text = (
        ROOT / "contracts" / "connectors" / "connector-storage.v1.sql"
    ).read_text(encoding="utf-8")
    for marker in (
        "connector_manifests",
        "connector_installations",
        "connector_connections",
        "connector_webhook_endpoints",
        "connector_webhook_inbox",
        "connector_operations",
        "connector_outbox",
        "FORCE ROW LEVEL SECURITY",
    ):
        if marker not in storage_text:
            errors.append(f"connector storage contract is missing {marker}")

    api_text = (
        ROOT / "contracts" / "connectors" / "connector-management-api.v1.yaml"
    ).read_text(encoding="utf-8")
    for marker in (
        "openapi: 3.1.0",
        "/v1/connectors/validate:",
        "/v1/connectors/install:",
        "/v1/connectors/{connector_id}/upgrade:",
        "/v1/webhooks/{webhook_id}/rotate-secret:",
        "/v1/webhook-deliveries/{delivery_id}/replay-request:",
        "/v1/webhooks/{connector_id}/{endpoint_key}:",
    ):
        if marker not in api_text:
            errors.append(f"connector API is missing {marker}")

    if errors:
        print("CONNECTOR_SDK_VALIDATION=FAIL", file=sys.stderr)
        for error in errors:
            print(f"ERROR={error}", file=sys.stderr)
        return 1

    print(
        "CONNECTOR_SDK_VALIDATION=PASS "
        f"CONNECTORS={len(records)} "
        f"CAPABILITIES={len(capabilities)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
