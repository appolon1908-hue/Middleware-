from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from collections.abc import Callable
from pathlib import Path
from typing import Any

from scripts import validate_observability_alert_contract as validator


ROOT = Path(__file__).resolve().parents[1]
BOUND_FILES = (
    "config/observability-alert-policy.v1.json",
    "config/capabilities.v2.json",
    "config/control-plane-callers.v1.json",
    "config/adapter-registry.v2.json",
    "connectors/generated/command-registry.v1.json",
    "contracts/observability/alert-api.v1.openapi.yaml",
    "deploy/observability-alerts/compose.core-production.yaml",
    "deploy/observability-alerts/production.env.example",
    "app/observability_alerts.py",
    "app/observability_alert_contract.py",
    "app/observability_incidents.py",
    "app/klyrow_alert_adapter.py",
    "workers/run_temporal.py",
    "migrations/0009_observability_incidents.sql",
)


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


class ObservabilityAlertContractValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.contract_root = Path(self.temporary_directory.name)
        for relative in BOUND_FILES:
            destination = self.contract_root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, destination)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def mutate_json(
        self,
        relative: str,
        mutation: Callable[[dict[str, Any]], None],
    ) -> None:
        path = self.contract_root / relative
        value = read_json(path)
        mutation(value)
        write_json(path, value)

    def assert_rejected(self, expected: str) -> None:
        with self.assertRaisesRegex(SystemExit, expected):
            validator.validate(self.contract_root)

    def test_current_contract_passes(self) -> None:
        self.assertEqual(validator.validate(ROOT), (18, 18))

    def test_duplicate_json_key_fails_closed(self) -> None:
        path = self.contract_root / "config/observability-alert-policy.v1.json"
        path.write_text(
            '{"schema_version":"1.0","schema_version":"1.0"}',
            encoding="utf-8",
        )
        self.assert_rejected("invalid_json:config/observability-alert-policy")

    def test_nonstandard_json_number_fails_closed(self) -> None:
        path = self.contract_root / "config/observability-alert-policy.v1.json"
        path.write_text('{"max_body_bytes":NaN}', encoding="utf-8")
        self.assert_rejected("invalid_json:config/observability-alert-policy")

    def test_policy_list_shape_fails_closed(self) -> None:
        self.mutate_json(
            "config/observability-alert-policy.v1.json",
            lambda policy: policy.update(allowed_severities="critical"),
        )
        self.assert_rejected("invalid_policy_list:allowed_severities")

    def test_body_limit_drift_fails_closed(self) -> None:
        self.mutate_json(
            "config/observability-alert-policy.v1.json",
            lambda policy: policy.update(max_body_bytes=10485760),
        )
        self.assert_rejected("policy_field_drifted:max_body_bytes")

    def test_alert_batch_limit_drift_fails_closed(self) -> None:
        self.mutate_json(
            "config/observability-alert-policy.v1.json",
            lambda policy: policy.update(max_alerts_per_request=100),
        )
        self.assert_rejected("policy_field_drifted:max_alerts_per_request")

    def test_capability_registry_shape_fails_closed(self) -> None:
        self.mutate_json(
            "config/capabilities.v2.json",
            lambda registry: registry.update(capabilities=[]),
        )
        self.assert_rejected("invalid_capability_registry")

    def test_enabled_capability_fails_closed(self) -> None:
        self.mutate_json(
            "config/capabilities.v2.json",
            lambda registry: registry["capabilities"].update(
                OBSERVABILITY_ALERT_EMAIL_DELIVERY=True
            ),
        )
        self.assert_rejected("alert_capability_must_default_false")

    def test_caller_shape_fails_closed(self) -> None:
        self.mutate_json(
            "config/control-plane-callers.v1.json",
            lambda registry: registry["callers"].update({"alertmanager-service": []}),
        )
        self.assert_rejected("missing_caller:alertmanager-service")

    def test_command_registry_entry_shape_fails_closed(self) -> None:
        self.mutate_json(
            "connectors/generated/command-registry.v1.json",
            lambda registry: registry["commands"].append([]),
        )
        self.assert_rejected("invalid_command_registry")

    def test_duplicate_alert_command_fails_closed(self) -> None:
        self.mutate_json(
            "connectors/generated/command-registry.v1.json",
            lambda registry: registry["commands"].append(
                next(
                    command.copy()
                    for command in registry["commands"]
                    if command["prefix"] == "observability.alert."
                )
            ),
        )
        self.assert_rejected("alert_command_policy_missing_or_duplicate:count=2")

    def test_duplicate_alert_adapter_fails_closed(self) -> None:
        self.mutate_json(
            "config/adapter-registry.v2.json",
            lambda registry: registry["adapters"].append(
                next(
                    adapter.copy()
                    for adapter in registry["adapters"]
                    if adapter["id"] == "klyrow-alert-email"
                )
            ),
        )
        self.assert_rejected("alert_adapter_missing_or_duplicate:count=2")

    def test_duplicate_openapi_route_fails_closed(self) -> None:
        path = self.contract_root / "contracts/observability/alert-api.v1.openapi.yaml"
        with path.open("a", encoding="utf-8") as contract:
            contract.write("\n  /health:\n    get: {}\n")
        self.assert_rejected("duplicate_openapi_route")

    def test_privileged_container_fails_closed(self) -> None:
        path = (
            self.contract_root
            / "deploy/observability-alerts/compose.core-production.yaml"
        )
        source = path.read_text(encoding="utf-8")
        path.write_text(
            source.replace(
                "    read_only: true", "    privileged: true\n    read_only: true"
            ),
            encoding="utf-8",
        )
        self.assert_rejected("container_boundary_forbidden:privileged")

    def test_inline_host_port_fails_closed(self) -> None:
        path = (
            self.contract_root
            / "deploy/observability-alerts/compose.core-production.yaml"
        )
        source = path.read_text(encoding="utf-8")
        path.write_text(
            source.replace("    expose:", '    ports: ["8080:8080"]\n    expose:'),
            encoding="utf-8",
        )
        self.assert_rejected("container_boundary_forbidden:host_port")

    def test_hardening_cannot_be_borrowed_from_another_service(self) -> None:
        path = (
            self.contract_root
            / "deploy/observability-alerts/compose.core-production.yaml"
        )
        source = path.read_text(encoding="utf-8")
        source = source.replace("    read_only: true\n", "", 1)
        source = source.replace(
            "\nnetworks:\n",
            "\n  decoy-service:\n    read_only: true\n\nnetworks:\n",
            1,
        )
        path.write_text(source, encoding="utf-8")
        self.assert_rejected("container_hardening_drifted:read_only")

    def test_inline_smtp_credential_fails_closed(self) -> None:
        path = self.contract_root / "deploy/observability-alerts/production.env.example"
        with path.open("a", encoding="utf-8") as environment:
            environment.write("\nsmtp_password = placeholder\n")
        self.assert_rejected(
            "secret_bearing_alert_configuration:direct_smtp_credential"
        )


if __name__ == "__main__":
    unittest.main()
