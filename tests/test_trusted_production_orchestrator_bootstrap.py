from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest


ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / ".codestra/run-trusted-production-orchestrator.py"
GOVERNANCE_VALIDATOR = ROOT / "scripts/validate_repository_governance.py"
BOOTSTRAP_WORKFLOW = (
    ROOT / ".github/workflows/trusted-production-orchestrator-bootstrap.yml"
)


def load_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_bootstrap_binds_both_approved_validator_generations() -> None:
    launcher = load_module("trusted_orchestrator_bootstrap", LAUNCHER)

    assert launcher.APPROVED_TRUST_WORKFLOW_SHA256 == {
        "b04b63ba17c8e3e2fdb6883f5a3e217d819464970f3a7082793ce60031ffba0a"
    }
    assert set(launcher.APPROVED_VALIDATOR_POLICIES) == {
        "3ebc283ef8c9b4c5bd2b3c92a173af042bf46d678b0746a1504992efa0ceda3a",
        "03885eb52f18fb03f56a02054ea774417d3cb0e9f9edf115d2bd7483b1854a95",
    }


def test_only_exact_bootstrap_target_workflow_is_governance_approved() -> None:
    governance = load_module("repository_governance_bootstrap", GOVERNANCE_VALIDATOR)
    text = BOOTSTRAP_WORKFLOW.read_text(encoding="utf-8")

    governance.validate_pull_request_target_workflow(BOOTSTRAP_WORKFLOW, text)
    with pytest.raises(governance.GovernanceError, match="pull_request_target is forbidden"):
        governance.validate_pull_request_target_workflow(
            BOOTSTRAP_WORKFLOW,
            text + "\n# unreviewed target mutation\n",
        )


def test_other_target_workflow_is_rejected(tmp_path: Path) -> None:
    governance = load_module("repository_governance_other", GOVERNANCE_VALIDATOR)
    workflow = tmp_path / "untrusted.yml"

    with pytest.raises(governance.GovernanceError, match="pull_request_target is forbidden"):
        governance.validate_pull_request_target_workflow(
            workflow,
            "on:\n  pull_request_target:\npermissions: read-all\n",
        )
