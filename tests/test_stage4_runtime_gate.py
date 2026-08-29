from __future__ import annotations

import json
from pathlib import Path

from scripts.verify_stage4_runtime_gate import REQUIRED_STEP_IDS, validate_gate


ROOT = Path(__file__).resolve().parents[1]


def load_gate() -> dict:
    return json.loads((ROOT / "config/stage4-runtime-gate.v1.json").read_text())


def test_stage4_runtime_gate_is_ordered_and_fail_closed() -> None:
    gate = load_gate()
    errors, lines = validate_gate(gate)

    assert errors == []
    assert gate["status"] == "NO_GO"
    assert gate["production_activation"] == "BLOCKED_UNTIL_ALL_STEPS_PASS"
    assert gate["live_mutation_performed"] is False
    assert gate["required_order"] == REQUIRED_STEP_IDS
    assert lines[0] == "STEP=middleware_original_bearer_ci STATE=PASS"
    assert "0053_callback_worker_grants" in gate["steps"][1]["blocker"]


def test_runtime_gate_go_requires_every_step_to_pass() -> None:
    gate = load_gate()
    gate["steps"][1]["state"] = "PASS"
    errors, _lines = validate_gate(gate)

    assert "status must be NO_GO for current step states" not in errors
    assert gate["status"] == "NO_GO"

    for step in gate["steps"]:
        step["state"] = "PASS"
        step.pop("required_evidence", None)
    gate["status"] = "GO"
    errors, _lines = validate_gate(gate)
    assert "GO requires production_release_approval.approved_source_sha" in errors

    gate["steps"][-1]["approved_source_sha"] = "a" * 40
    errors, _lines = validate_gate(gate)
    assert errors == []
