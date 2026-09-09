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
    "config/api-webhook-contracts.json",
    "config/environments/staging.intake-observability.runtime.env.example",
    "app/appolon_factory.py",
    "app/n8n_control_plane.py",
    "app/operations_dashboard.py",
    "app/operations.py",
    "app/control_api.py",
    "app/compatibility_api.py",
    "app/domain_api.py",
    "app/webhook_api.py",
    "app/telephony_api.py",
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
        "dead_metrics_authentication",
        "unrelated_metrics_verifier",
        "unawaited_metrics_verifier",
        "decorated_metrics_handler",
        "shadow_metrics_registration",
        "unapproved_included_router",
        "included_router_shadow",
        "webhook_shadow",
        "request_dependency_proxy",
        "rebound_request_type",
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
    elif mutation in {
        "dead_metrics_authentication",
        "unrelated_metrics_verifier",
        "unawaited_metrics_verifier",
    }:
        factory_path = tmp_path / "app/appolon_factory.py"
        factory = factory_path.read_text(encoding="utf-8")
        authentication = '''        await request.app.state.runtime.tokens.verify(
            request.headers.get("Authorization", ""),
            expected_client_id="monitoring-readonly",
            required_scope="metrics.read",
        )'''
        if mutation == "dead_metrics_authentication":
            replacement = '''        if False:
            await request.app.state.runtime.tokens.verify(
                request.headers.get("Authorization", ""),
                expected_client_id="monitoring-readonly",
                required_scope="metrics.read",
            )'''
        elif mutation == "unrelated_metrics_verifier":
            replacement = authentication.replace(
                "request.app.state.runtime.tokens.verify",
                "unrelated.verify",
            )
        else:
            replacement = authentication.replace("        await ", "        ", 1)
        require_replacement = factory.replace(authentication, replacement, 1)
        assert require_replacement != factory
        factory_path.write_text(require_replacement, encoding="utf-8")
    elif mutation in {
        "decorated_metrics_handler",
        "shadow_metrics_registration",
        "unapproved_included_router",
    }:
        factory_path = tmp_path / "app/appolon_factory.py"
        factory = factory_path.read_text(encoding="utf-8")
        marker = '    @app.get("/metrics")\n'
        if mutation == "decorated_metrics_handler":
            replacement = marker + "    @replace_handler\n"
        elif mutation == "shadow_metrics_registration":
            replacement = (
                "    app.add_api_route(\"/\" + \"metrics\", public_metrics, "
                "methods=[\"GET\"])\n\n" + marker
            )
        else:
            replacement = "    app.include_router(public_metrics_router)\n\n" + marker
        changed = factory.replace(marker, replacement, 1)
        assert changed != factory
        factory_path.write_text(changed, encoding="utf-8")
    elif mutation == "included_router_shadow":
        router_path = tmp_path / "app/control_api.py"
        source = router_path.read_text(encoding="utf-8")
        source += (
            '\nshadow_path = "/metrics"\n'
            'router.add_api_route(shadow_path, public_metrics, methods=["GET"])\n'
        )
        router_path.write_text(source, encoding="utf-8")
    elif mutation == "webhook_shadow":
        webhook_path = tmp_path / "config/api-webhook-contracts.json"
        webhook_contract = json.loads(webhook_path.read_text(encoding="utf-8"))
        webhook_contract["webhooks"][0]["path"] = "/metrics"
        webhook_path.write_text(json.dumps(webhook_contract), encoding="utf-8")
    elif mutation in {"request_dependency_proxy", "rebound_request_type"}:
        factory_path = tmp_path / "app/appolon_factory.py"
        factory = factory_path.read_text(encoding="utf-8")
        if mutation == "request_dependency_proxy":
            factory = factory.replace(
                "    async def metrics(request: Request) -> Response:\n",
                "    async def metrics(\n"
                "        request: object = Depends(public_request),\n"
                "    ) -> Response:\n",
                1,
            )
        else:
            factory = factory.replace(
                "from pydantic import AwareDatetime, BaseModel, Field, ValidationError\n",
                "from pydantic import AwareDatetime, BaseModel, Field, ValidationError\n"
                "Request = object\n",
                1,
            )
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
