#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_SOURCE = "f6748a58f8d2590520a4f28776770957061cdea1"
EXPECTED_DIGEST = "sha256:695fa3ce3f50ba4d0ae0784976b946a0a683ca731155e4bd3bd9e90a4670b820"


def parse_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        assert separator == "=" and key and key not in values
        values[key] = value
    return values


def main() -> None:
    contract = json.loads((ROOT / "contracts/staging-intake-observability-runtime.v1.json").read_text())
    assert contract["schema_version"] == "1.0"
    release = contract["immutable_release"]
    assert release["source_sha"] == EXPECTED_SOURCE
    assert release["image_digest"] == EXPECTED_DIGEST
    assert release["image_reference"].endswith("@" + EXPECTED_DIGEST)
    assert re.fullmatch(r"sha256:[0-9a-f]{64}", release["image_digest"])
    assert release["schema_head"] == "0003_immutable_event_ledger"

    runtime = contract["runtime"]
    assert runtime["environment"] == "staging"
    assert runtime["allow_in_memory_storage"] is False
    assert runtime["host_ports_published"] is False
    assert runtime["private_network_only"] is True
    assert runtime["nats_dispatch_mode"] == "disabled"
    assert runtime["temporal_worker_mode"] == "disabled"
    assert runtime["outbox_dispatch_enabled"] is False
    assert runtime["production_dialing"] == "DISABLED"
    assert runtime["production_activation_configured"] is False

    endpoints = contract["authenticated_read_endpoints"]
    expected_endpoints = {
        ("GET", "/metrics", "monitoring-readonly", "metrics.read", "middleware-api", False),
        ("GET", "/v1/runtime/safety", "monitoring-readonly", "health.read", "middleware-api", False),
    }
    actual = {(e["method"], e["path"], e["client_id"], e["scope"], e["audience"], e["public_exposure"]) for e in endpoints}
    assert actual == expected_endpoints and len(endpoints) == 2
    assert contract["token_policy"]["maximum_lifetime_seconds"] == 300
    assert contract["token_policy"]["minimum_independent_tokens"] == 2
    assert contract["token_policy"]["token_values_in_logs_or_artifacts"] is False
    assert contract["external_effects"] and all(value is False for value in contract["external_effects"].values())
    assert contract["evidence"]["checksum_state"] == "PENDING_RUNTIME_EXECUTION"
    assert contract["evidence"]["prometheus_target_state"] == "pending"
    assert contract["evidence"]["blackbox_target_state"] == "pending"
    assert contract["production_authorized"] is False

    env = parse_env(ROOT / "config/environments/staging.intake-observability.runtime.env.example")
    assert env["APP_ENV"] == "staging"
    assert env["RUNTIME_PROFILE_ID"] == runtime["profile_id"]
    assert env["APP_SOURCE_SHA"] == EXPECTED_SOURCE
    assert env["IMAGE_DIGEST"] == EXPECTED_DIGEST
    assert env["SCHEMA_HEAD"] == release["schema_head"]
    assert env["ALLOW_IN_MEMORY_STORAGE"] == "false"
    assert env["NATS_DISPATCH_MODE"] == "disabled"
    assert env["TEMPORAL_WORKER_MODE"] == "disabled"
    assert env["PRODUCTION_DIALING"] == "DISABLED"
    for name in contract["external_effects"]:
        assert env[name] == "false", name
    assert "<inject-secret>" in env["DATABASE_URL"] and "<inject-secret>" in env["REDIS_URL"]

    main_source = (ROOT / "app/main.py").read_text()
    security_source = (ROOT / "app/security.py").read_text()
    assert '@app.get("/metrics")' in main_source
    assert 'required_scope="metrics.read"' in main_source
    assert '@app.get("/v1/runtime/safety")' in main_source
    assert 'required_scope="health.read"' in main_source
    assert "expires_at - issued_at > 300" in security_source
    print("MIDDLEWARE_STAGING_INTAKE_OBSERVABILITY_CONTRACT=PASS")


if __name__ == "__main__":
    main()
