from __future__ import annotations

import importlib.util
import shutil
from pathlib import Path
from types import ModuleType

import pytest


ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / ".codestra/run-trusted-production-orchestrator.py"


def load_launcher() -> ModuleType:
    spec = importlib.util.spec_from_file_location("trusted_orchestrator", LAUNCHER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def candidate_copy(tmp_path: Path) -> Path:
    for relative in (
        ".codestra/run-trusted-production-orchestrator.py",
        ".codestra/validate-production-orchestrator-contract.py",
        ".codestra/validate-release-intent.py",
        ".github/workflows/production-orchestrator-contract.yml",
    ):
        source = ROOT / relative
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
    return tmp_path


def test_current_validator_pair_is_approved() -> None:
    launcher = load_launcher()

    assert launcher.validate_candidate(ROOT) == (
        ROOT / ".codestra/validate-production-orchestrator-contract.py"
    )


def test_coordinated_candidate_validator_replacement_is_rejected(
    tmp_path: Path,
) -> None:
    launcher = load_launcher()
    candidate = candidate_copy(tmp_path)
    orchestrator = candidate / ".codestra/validate-production-orchestrator-contract.py"
    release_validator = candidate / ".codestra/validate-release-intent.py"
    orchestrator.write_bytes(orchestrator.read_bytes() + b"\n# candidate replacement\n")
    release_validator.write_bytes(
        release_validator.read_bytes() + b"\n# matching candidate digest replacement\n"
    )

    with pytest.raises(
        launcher.TrustError, match="orchestrator validator is not approved"
    ):
        launcher.validate_candidate(candidate)


def test_candidate_cannot_replace_trust_workflow(tmp_path: Path) -> None:
    launcher = load_launcher()
    candidate = candidate_copy(tmp_path)
    workflow = candidate / ".github/workflows/production-orchestrator-contract.yml"
    workflow.write_bytes(workflow.read_bytes() + b"\n# candidate trust bypass\n")

    with pytest.raises(launcher.TrustError, match="protected-base trust file changed"):
        launcher.validate_candidate(candidate)
