#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import socket
import sys
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_GATE = ROOT / "config" / "stage4-runtime-gate.v1.json"
REQUIRED_STEP_IDS = [
    "middleware_original_bearer_ci",
    "staging_migration_lineage",
    "staging_dns_reachability",
    "live_authorization_matrix",
    "cp_odoo_no_effect_runtime_proof",
    "production_release_approval",
]
STEP_STATES = {"PASS", "PENDING", "BLOCKED", "FAIL"}
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
HOSTS = ("auth.codestra.co", "api.codestra.co")


class GateError(RuntimeError):
    pass


def load_gate(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GateError(f"cannot read gate {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise GateError("gate must be a JSON object")
    return value


def validate_gate(gate: dict[str, Any]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    lines: list[str] = []

    if gate.get("schema_version") != "1.0":
        errors.append("schema_version must be 1.0")
    if gate.get("target") != "stage4-orchestration-to-production":
        errors.append("target must be stage4-orchestration-to-production")
    if gate.get("production_activation") != "BLOCKED_UNTIL_ALL_STEPS_PASS":
        errors.append("production_activation must be BLOCKED_UNTIL_ALL_STEPS_PASS")
    if gate.get("live_mutation_performed") is not False:
        errors.append("live_mutation_performed must remain false in source evidence")
    if gate.get("required_order") != REQUIRED_STEP_IDS:
        errors.append("required_order does not match the approved sequence")

    raw_steps = gate.get("steps")
    if not isinstance(raw_steps, list):
        errors.append("steps must be a list")
        return errors, lines

    steps: dict[str, dict[str, Any]] = {}
    for index, step in enumerate(raw_steps, start=1):
        if not isinstance(step, dict):
            errors.append(f"step {index} must be an object")
            continue
        step_id = step.get("id")
        if not isinstance(step_id, str) or not step_id:
            errors.append(f"step {index} has missing id")
            continue
        if step_id in steps:
            errors.append(f"duplicate step id: {step_id}")
        steps[step_id] = step
        state = step.get("state")
        if state not in STEP_STATES:
            errors.append(f"step {step_id} has invalid state {state!r}")
        if step.get("blocks_production") is not True:
            errors.append(f"step {step_id} must block production")
        if state != "PASS":
            evidence = step.get("required_evidence")
            if not isinstance(evidence, list) or not evidence:
                errors.append(f"step {step_id} must list required evidence while not PASS")
        lines.append(f"STEP={step_id} STATE={state}")

    missing = [step_id for step_id in REQUIRED_STEP_IDS if step_id not in steps]
    if missing:
        errors.append("missing required step(s): " + ", ".join(missing))

    current_states = [steps[step_id].get("state") for step_id in REQUIRED_STEP_IDS if step_id in steps]
    calculated_status = "GO" if current_states and all(state == "PASS" for state in current_states) else "NO_GO"
    if gate.get("status") != calculated_status:
        errors.append(f"status must be {calculated_status} for current step states")

    seen_incomplete = False
    for step_id in REQUIRED_STEP_IDS:
        state = steps.get(step_id, {}).get("state")
        if state != "PASS":
            seen_incomplete = True
        elif seen_incomplete:
            errors.append(f"{step_id} cannot PASS before earlier steps pass")

    if calculated_status == "GO":
        approval = steps["production_release_approval"]
        approved_sha = str(approval.get("approved_source_sha", ""))
        if SHA_RE.fullmatch(approved_sha) is None:
            errors.append("GO requires production_release_approval.approved_source_sha")

    return errors, lines


def _probe_http(url: str, *, method: str = "GET") -> tuple[int, str]:
    request = Request(url, method=method, headers={"User-Agent": "codestra-stage4-runtime-gate/1"})
    try:
        with urlopen(request, timeout=10) as response:
            return int(getattr(response, "status", response.getcode())), response.read(4096).decode("utf-8", "replace")
    except HTTPError as exc:
        return int(exc.code), exc.read(4096).decode("utf-8", "replace")
    except (OSError, URLError) as exc:
        raise GateError(f"{url} probe failed: {type(exc).__name__}: {exc}") from exc


def probe_live() -> tuple[list[str], list[str]]:
    errors: list[str] = []
    lines: list[str] = []

    for host in HOSTS:
        try:
            addresses = sorted({item[4][0] for item in socket.getaddrinfo(host, 443)})
        except socket.gaierror as exc:
            errors.append(f"{host} DNS lookup failed: {exc}")
            continue
        lines.append(f"DNS={host} ADDRESSES={','.join(addresses)}")

    try:
        status, body = _probe_http(
            "https://auth.codestra.co/realms/codestra/.well-known/openid-configuration"
        )
    except GateError as exc:
        errors.append(str(exc))
    else:
        lines.append(f"OIDC_DISCOVERY_HTTP={status}")
        if status != 200:
            errors.append(f"OIDC discovery returned HTTP {status}")
        if "https://auth.codestra.co/realms/codestra" not in body:
            errors.append("OIDC discovery issuer not present in response")

    for label, method, url in (
        ("API_READY", "GET", "https://api.codestra.co/ready"),
        ("API_RUNTIME_SAFETY", "GET", "https://api.codestra.co/v1/runtime/safety"),
        ("API_COMMAND_ROUTE", "POST", "https://api.codestra.co/v1/commands"),
    ):
        try:
            status, _body = _probe_http(url, method=method)
        except GateError as exc:
            errors.append(str(exc))
            continue
        lines.append(f"{label}_HTTP={status}")
        if status == 404:
            errors.append(f"{label} returned 404; Kong/Middleware route is not active at {url}")

    return errors, lines


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", type=Path, default=DEFAULT_GATE)
    parser.add_argument("--allow-no-go", action="store_true")
    parser.add_argument("--probe-live", action="store_true")
    args = parser.parse_args()

    path = args.path if args.path.is_absolute() else ROOT / args.path
    try:
        gate = load_gate(path)
    except GateError as exc:
        print("STAGE4_RUNTIME_GATE=FAIL")
        print(f"ERROR={exc}")
        return 1

    errors, lines = validate_gate(gate)
    if args.probe_live:
        live_errors, live_lines = probe_live()
        errors.extend(live_errors)
        lines.extend(live_lines)

    if errors:
        print("STAGE4_RUNTIME_GATE=FAIL")
        for line in lines:
            print(line)
        for error in errors:
            print(f"ERROR={error}")
        return 1

    status = str(gate.get("status"))
    print(f"STAGE4_RUNTIME_GATE={status}")
    for line in lines:
        print(line)
    print("PRODUCTION_ACTIVATION=" + str(gate.get("production_activation")))
    if status == "GO":
        return 0
    return 0 if args.allow_no_go else 1


if __name__ == "__main__":
    raise SystemExit(main())
