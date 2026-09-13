from __future__ import annotations

import importlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "contracts" / "observability-control-plane.v1.json"


def test_contract_is_valid_json_with_expected_shape():
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert contract["contract_id"] == "codestra.observability-control-plane"
    assert contract["canonical_owner"] == "appolon1908-hue/Middleware-"
    service_names = {service["service"] for service in contract["services"]}
    assert {
        "prometheus", "alertmanager", "grafana", "loki", "tempo", "alloy",
        "node-exporter", "cadvisor", "postgres-exporter", "redis-exporter",
        "blackbox-exporter", "superset", "openbao",
    } <= service_names
    for service in contract["services"]:
        if service["service"] in {
            "prometheus", "alertmanager", "loki", "tempo", "alloy",
            "node-exporter", "cadvisor", "postgres-exporter",
            "redis-exporter", "blackbox-exporter",
        }:
            assert service["public_route_allowed"] is False, service["service"]


def test_alertmanager_is_middleware_only():
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    alertmanager = next(
        s for s in contract["services"] if s["service"] == "alertmanager"
    )
    assert alertmanager["authorized_receiver"] == "appolon1908-hue/Middleware-"
    odoo = contract["endpoints"]["appolon1908-hue/Odoo"]
    assert odoo["alertmanager_receiver_present"] is False
    n8n = contract["endpoints"]["appolon1908-hue/N8N"]
    assert n8n["alertmanager_receiver_present"] is False


def test_validator_script_passes():
    module = importlib.import_module("scripts.validate_observability_control_plane")
    assert module.main() == 0
