from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/validate_staging_intake_observability_contract.py"
BOUND_FILES = (
    "contracts/staging-intake-observability-runtime.v1.json",
    "config/runtime-profiles.v1.json",
    "config/environments/staging.intake-observability.runtime.env.example",
    "app/appolon_factory.py",
    "app/security.py",
)


@pytest.mark.parametrize("optimized", [False, True])
@pytest.mark.parametrize(
    "mutation",
    [
        "production_authorized",
        "effect_enabled",
        "public_metrics",
        "wrong_source",
        "commented_metrics_route",
    ],
)
def test_staging_contract_fails_closed(
    tmp_path: Path,
    optimized: bool,
    mutation: str,
) -> None:
    for relative in BOUND_FILES:
        source = ROOT / relative
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())

    contract_path = (
        tmp_path / "contracts/staging-intake-observability-runtime.v1.json"
    )
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    if mutation == "production_authorized":
        contract["production_authorized"] = True
    elif mutation == "effect_enabled":
        contract["runtime_recognized_external_effects"]["LIVE_WRITE"] = True
    elif mutation == "public_metrics":
        contract["authenticated_read_endpoints"][0]["public_exposure"] = True
    elif mutation == "wrong_source":
        contract["immutable_release"]["source_sha"] = "0" * 40
    contract_path.write_text(json.dumps(contract), encoding="utf-8")
    if mutation == "commented_metrics_route":
        factory_path = tmp_path / "app/appolon_factory.py"
        factory = factory_path.read_text(encoding="utf-8")
        factory = factory.replace(
            '    @app.get("/metrics")\n',
            '    # @app.get("/metrics")\n',
            1,
        )
        factory += '\n# @app.get("/metrics") required_scope="metrics.read"\n'
        factory_path.write_text(factory, encoding="utf-8")

    program = (
        "import importlib.util,pathlib;"
        f'spec=importlib.util.spec_from_file_location("staging_contract",{str(SCRIPT)!r});'
        "m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);"
        f"m.ROOT=pathlib.Path({str(tmp_path)!r});m.main()"
    )
    result = subprocess.run(
        [sys.executable, *(("-O",) if optimized else ()), "-c", program],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "ContractError" in result.stderr


def test_committed_staging_contract_is_valid() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "MIDDLEWARE_STAGING_INTAKE_OBSERVABILITY_CONTRACT=PASS" in result.stdout
