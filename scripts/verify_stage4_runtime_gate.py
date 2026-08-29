#!/usr/bin/env python3
"""Verify the Stage 4 runtime gate before any production activation.

The default mode is source-only and does not call the network. It validates that
the gate is explicit, ordered, and fail-closed. Use --allow-no-go for CI checks
that should pass while the runtime remains blocked.
"""

from __future__ import annotations

import argparse
import json
import re
import socket
import sys
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_GATE = ROOT / "config" / "stage4-runtime-gate.v1.json"
STEP_STATES = {"PASS", "PENDING", "BLOCKED", "FAIL"}
NO_GO_STATES = {"PENDING", "BLOCKED", "FAIL"}
REQUIRED_STEP_IDS = [
    "middleware_original_bearer_ci",
    "staging_migration_lineage",
    "staging_dns_reachability",
    "live_authorization_matrix",
    "cp_odoo_no_effect_runtime_proof",
    "production_release_approval",
]
HOSTS = ("auth.codestra.co", "api.codestra.co")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def load_gate(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"gate cannot be read: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("gate must be a JSON object")
    return data


def validate_gate(data: dict[str, Any]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    lines: list[str] = []

    if data.get("schema_version") != "1.0":
        errors.append("schema_version must be 1.0")
    if data.get("target") != "stage4-orchestration-to-production":
        errors.append("target must be stage4-orchestration-to-production")
    if data.get("live_mutation_performed") is not False:
        errors.append("source gate must record live_mutation_performed=false")
    if data.get("production_activation") != "BLOCKED_UNTIL_ALL_STEPS_PASS":
        errors.append("production_activation must remain fail-closed")

    order = data.get("required_order")
    if order != REQUIRED_STEP_IDS:
        errors.append("required_order does not match the approved Stage 4 sequence")

    steps = data.get("steps")
    if not isinstance(steps, list):
        errors.append("steps must be a list")
        return errors, lines

    by_id: dict[str, dict[str, Any]] = {}
    for index, step in enumerate(steps, start=1):
        if not isinstance(step, dict):
            errors.append(f"step {index} must be an object")
            continue
        step_id = step.get("id")
        if not isinstance(step_id, str) or not step_id:
            errors.append(f"step {index} has missing id")
            continue
        if step_id in by_id:
            errors.append(f"duplicate step id: {step_id}")
        by_id[step_id] = step

        state = step.get("state")
        if state not in STEP_STATES:
            errors.append(f"step {step_id} has invalid state {state!r}")
        if step.get("blocks_production") is not True:
            errors.append(f"step {step_id} must block production")
        evidence = step.get("required_evidence")
        if not isinstance(evidence, list) or not evidence or not all(
            isinstance(item, str) and item.strip() for item in evidence
        ):
            errors.append(f"step {step_id} must list required evidence")
        lines.append(f"STEP={step_id} STATE={state}")

    missing = [step_id for step_id in REQUIRED_STEP_IDS if step_id not in by_id]
    if missing:
        errors.append("missing required steps: " + ", ".join(missing))

    states = [by_id[step_id].get("state") for step_id in REQUIRED_STEP_IDS if step_id in by_id]
    calculated = "GO" if states and all(state == "PASS" for state in states) else "NO_GO"
    if data.get("status") != calculated:
        errors.append(f"status must be {calculated} for current step states")

    seen_not_pass = False
    for step_id in REQUIRED_STEP_IDS:
        step = by_id.get(step_id)
        if not step:
            continue
        state = step.get("state")
        if state in NO_GO_STATES:
            seen_not_pass = True
        elif state == "PASS" and seen_not_pass:
            errors.append(f"step {step_id} cannot PASS before earlier blockers pass")

    if calculated == "GO":
        release = by_id["production_release_approval"]
        release_sha = str(release.get("approved_source_sha", ""))
        if not SHA_RE.fullmatch(release_sha):
            errors.append("GO requires production_release_approval.approved_source_sha")

    return errors, lines


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

    request = Request(
        "https://auth.codestra.co/realms/codestra/.well-known/openid-configuration",
        headers={"User-Agent": "codestra-stage4-runtime-gate/1"},
    )
    try:
        with urlopen(request, timeout=10) as response:
            status = getattr(response, "status", response.getcode())
            body = response.read(4096)
    except (OSError, URLError) as exc:
        errors.append(f"OIDC discovery failed: {type(exc).__name__}: {exc}")
    else:
        lines.append(f"OIDC_DISCOVERY_HTTP={status}")
        if status != 200:
            errors.append(f"OIDC discovery returned HTTP {status}")
        if b"https://auth.codestra.co/realms/codestra" not in body:
            errors.append("OIDC discovery issuer was not found in response body")
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
    except ValueError as exc:
        print("STAGE4_RUNTIME_GATE=FAIL")
        print(f"ERROR={exc}")
        return 1

    errors, lines = validate_gate(gate)
    live_errors: list[str] = []
    live_lines: list[str] = []
    if args.probe_live:
        live_errors, live_lines = probe_live()
        errors.extend(live_errors)

    status = gate.get("status")
    if errors:
        print("STAGE4_RUNTIME_GATE=FAIL")
        for line in lines + live_lines:
            print(line)
        for error in errors:
            print(f"ERROR={error}")
        return 1

    print(f"STAGE4_RUNTIME_GATE={status}")
    for line in lines + live_lines:
        print(line)
    print("PRODUCTION_ACTIVATION=" + str(gate.get("production_activation")))
    if status == "GO":
        return 0
    return 0 if args.allow_no_go else 1


if __name__ == "__main__":
    raise SystemExit(main())
