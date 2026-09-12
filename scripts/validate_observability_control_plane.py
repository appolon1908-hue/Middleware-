#!/usr/bin/env python3
"""Fail CI if Middleware's own side of the observability control plane drifts.

Sibling of ``validate_platform_control_plane.py`` - same style (AST-scan the
real decorated routes, compare against the checked-in contract, ``fail()``
on any mismatch). This validator can only check Middleware's own codebase;
the negative "only Middleware receives Alertmanager" assertion is checked
per-repo, in each pinned consumer's own validator, scoped to that repo.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "contracts" / "observability-control-plane.v1.json"
MAIN_API = ROOT / "app" / "appolon_factory.py"
ALERTS_API = ROOT / "app" / "observability_alerts.py"


def fail(message: str) -> None:
    raise SystemExit(f"OBSERVABILITY_CONTROL_PLANE=FAIL {message}")


def decorated_routes(source: str) -> dict[str, set[str]]:
    """Map each string-literal route path to the set of HTTP methods it's
    registered under, by walking every ``@app.<method>(...)``/
    ``@router.<method>(...)`` decorator in the module - regardless of
    nesting depth (both files here register routes on functions nested
    inside a ``create_app()`` closure, not at module level)."""
    routes: dict[str, set[str]] = {}
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if not (
                isinstance(decorator, ast.Call)
                and isinstance(decorator.func, ast.Attribute)
                and decorator.func.attr in {"get", "post", "put", "patch", "delete", "head"}
                and decorator.args
                and isinstance(decorator.args[0], ast.Constant)
                and isinstance(decorator.args[0].value, str)
            ):
                continue
            routes.setdefault(decorator.args[0].value, set()).add(
                decorator.func.attr.upper()
            )
    return routes


def main() -> int:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))

    if contract.get("contract_id") != "codestra.observability-control-plane":
        fail("unexpected contract identity")
    if contract.get("canonical_owner") != "appolon1908-hue/Middleware-":
        fail("Middleware is not the declared canonical owner")

    endpoints = contract.get("endpoints", {}).get("appolon1908-hue/Middleware-", {})
    processes = {p["process"]: p for p in endpoints.get("processes", [])}

    main_process = processes.get("middleware-api")
    if not main_process:
        fail("contract is missing the middleware-api process entry")
    main_routes = decorated_routes(MAIN_API.read_text(encoding="utf-8"))
    metrics_path = main_process["metrics_path"]
    if metrics_path not in main_routes or "GET" not in main_routes[metrics_path]:
        fail(f"middleware-api does not actually register GET {metrics_path}")

    alerts_process = processes.get("middleware-observability-alerts")
    if not alerts_process:
        fail("contract is missing the middleware-observability-alerts process entry")
    alerts_routes = decorated_routes(ALERTS_API.read_text(encoding="utf-8"))

    for key in ("health_path", "readiness_path", "version_path", "capabilities_path", "metrics_path"):
        path = alerts_process[key]
        if path not in alerts_routes:
            fail(f"middleware-observability-alerts does not actually register {path} ({key})")

    webhook_path = alerts_process["alertmanager_webhook_path"]
    if webhook_path not in alerts_routes or "POST" not in alerts_routes[webhook_path]:
        fail(f"Alertmanager webhook path {webhook_path} is not registered as POST")

    status_path = alerts_process["alertmanager_status_webhook_path"]
    if status_path not in alerts_routes or "POST" not in alerts_routes[status_path]:
        fail(f"Alertmanager status-webhook path {status_path} is not registered as POST")

    for alias in alerts_process.get("deprecated_aliases", []):
        if alias not in alerts_routes:
            fail(f"declared deprecated alias {alias} no longer exists - update the contract")

    # Sanity check on this repo's own side of the "only Middleware receives
    # Alertmanager" rule: the same client-id constant this repo's real
    # webhook route actually authorizes against must match what the
    # contract declares - if a second, different client id ever gets wired
    # to an alert-shaped route in this repo, that's exactly the kind of
    # silent authority drift this contract exists to catch.
    contract_client_id = alerts_process.get("alertmanager_client_id")
    source_text = ALERTS_API.read_text(encoding="utf-8")
    if f'expected_client_id={ "ALERTMANAGER_CLIENT_ID" }' not in source_text:
        fail("observability_alerts.py no longer authorizes against ALERTMANAGER_CLIENT_ID")
    contract_file = ROOT / "app" / "observability_alert_contract.py"
    contract_source = contract_file.read_text(encoding="utf-8")
    if f'ALERTMANAGER_CLIENT_ID = "{contract_client_id}"' not in contract_source:
        fail("ALERTMANAGER_CLIENT_ID no longer matches the contract's declared client id")

    print("OBSERVABILITY_CONTROL_PLANE=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
