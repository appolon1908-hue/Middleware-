from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest


ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / ".codestra/run-trusted-production-orchestrator.py"
GATE = ROOT / ".github/workflows/trusted-production-orchestrator-gate.yml"


def load_launcher() -> ModuleType:
    spec = importlib.util.spec_from_file_location("trusted_orchestrator_launcher", LAUNCHER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_gate_runs_only_from_protected_pull_request_target_source() -> None:
    text = GATE.read_text(encoding="utf-8")
    assert "\n  pull_request_target:\n" in text
    assert "\n  pull_request:\n" not in text
    assert "github.event.pull_request.head.repo.full_name == github.repository" in text
    assert "checks: write" in text
    assert "persist-credentials: false" in text


def test_gate_publishes_required_context_on_exact_candidate_head() -> None:
    text = GATE.read_text(encoding="utf-8")
    assert "EXPECTED_SHA: ${{ github.event.pull_request.head.sha }}" in text
    assert "COMPARISON_SHA: ${{ github.event.pull_request.base.sha }}" in text
    assert "name: 'orchestrator-contract'" in text
    assert "head_sha: headSha" in text
    assert "VALIDATION_OUTCOME: ${{ steps.validation.outcome }}" in text
    assert "conclusion: passed ? 'success' : 'failure'" in text


def test_gate_uses_commit_pinned_actions() -> None:
    text = GATE.read_text(encoding="utf-8")
    assert (
        "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1" in text
    )
    assert (
        "actions/github-script@ed597411d8f924073f98dfc5c65a23a2325f34cd"
        in text
    )


def test_launcher_protects_itself_and_status_publisher() -> None:
    launcher = load_launcher()
    assert launcher.TRUST_GATE_WORKFLOW_PATH == Path(
        ".github/workflows/trusted-production-orchestrator-gate.yml"
    )
    source = LAUNCHER.read_text(encoding="utf-8")
    assert "require_unchanged_trust_file(LAUNCHER_PATH.relative_to(TRUST_ROOT), root)" in source
    assert "require_unchanged_trust_file(TRUST_GATE_WORKFLOW_PATH, root)" in source


def test_trust_file_comparison_rejects_candidate_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    launcher = load_launcher()
    trusted_root = tmp_path / "trusted"
    candidate_root = tmp_path / "candidate"
    relative = Path(".github/workflows/trusted-production-orchestrator-gate.yml")
    trusted_path = trusted_root / relative
    candidate_path = candidate_root / relative
    trusted_path.parent.mkdir(parents=True)
    candidate_path.parent.mkdir(parents=True)
    trusted_path.write_text("trusted\n", encoding="utf-8")
    candidate_path.write_text("changed\n", encoding="utf-8")
    monkeypatch.setattr(launcher, "TRUST_ROOT", trusted_root)

    with pytest.raises(launcher.TrustError, match="protected-base trust file changed"):
        launcher.require_unchanged_trust_file(relative, candidate_root)
