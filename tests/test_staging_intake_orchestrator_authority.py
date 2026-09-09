from __future__ import annotations

import hashlib
import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest


ROOT = Path(__file__).resolve().parents[1]
VALIDATOR_PATH = ROOT / ".codestra" / "validate-production-orchestrator-contract.py"
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "staging-intake-e2e-no-effect.yml"
SCRIPT_PATH = ROOT / "scripts" / "staging-intake-e2e-no-effect.py"
WORKFLOW_RELATIVE = ".github/workflows/staging-intake-e2e-no-effect.yml"


def _validator() -> ModuleType:
    spec = importlib.util.spec_from_file_location("staging_orchestrator_validator", VALIDATOR_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _workflow() -> str:
    return WORKFLOW_PATH.read_text(encoding="utf-8")


def test_exact_staging_no_effect_workflow_is_the_only_live_mutation_exception() -> None:
    validator = _validator()
    text = _workflow()

    validator.require_mutating_jobs_disabled(text, WORKFLOW_RELATIVE)
    assert validator.STAGING_NO_EFFECT_SCRIPT_SHA256 == hashlib.sha256(SCRIPT_PATH.read_bytes()).hexdigest()


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("github.repository == 'appolon1908-hue/Middleware-'", "github.repository != 'appolon1908-hue/Middleware-'"),
        ("github.actor == 'appolon1908-hue'", "github.actor != 'appolon1908-hue'"),
        ("github.ref == 'refs/heads/main'", "github.ref == 'refs/heads/staging'"),
        ("inputs.confirm_no_effect == true", "inputs.confirm_no_effect == false"),
        ("environment: intake-staging-certification", "environment: production"),
        ('LIVE_EMAIL_DELIVERY: "false"', 'LIVE_EMAIL_DELIVERY: "true"'),
        ("PRODUCTION_DEPLOYMENT_AUTHORIZED=NO", "PRODUCTION_DEPLOYMENT_AUTHORIZED=YES"),
    ],
)
def test_staging_mutation_exception_fails_closed_when_authority_drifts(old: str, new: str) -> None:
    validator = _validator()
    text = _workflow()
    assert old in text

    with pytest.raises(validator.ContractError):
        validator.require_mutating_jobs_disabled(text.replace(old, new, 1), WORKFLOW_RELATIVE)


def test_staging_mutation_exception_rejects_an_extra_mutating_command() -> None:
    validator = _validator()
    text = _workflow()
    needle = '            --expected-source-sha "$EXPECTED_SOURCE_SHA"'
    assert needle in text
    mutated = text.replace(
        needle,
        needle + '\n          curl -X POST https://runtime.example/mutate',
        1,
    )

    with pytest.raises(validator.ContractError):
        validator.require_mutating_jobs_disabled(mutated, WORKFLOW_RELATIVE)
