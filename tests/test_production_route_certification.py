from scripts import certify_production_route_contract as certification
from pathlib import Path


def test_certification_uses_parameterized_operation_and_exact_provider_route():
    assert certification.COMMAND_PATH == "/v1/commands"
    assert certification.OPERATION_COLLECTION_PATH == "/v1/operations"
    assert certification.OPERATION_TEMPLATE == "/v1/operations/{command_id}"
    assert certification.OPERATION_PROBE.endswith("00000000-0000-0000-0000-000000000000")
    assert certification.VICIDIAL_PATH == "/api/v1/vicidial/events"
    assert certification.OPERATION_PROBE != certification.OPERATION_COLLECTION_PATH
    assert "/v1/operations-dashboard/overview" in certification.OPERATIONS_DASHBOARD_PATHS
    assert "/v1/operations-dashboard/tenants/{tenant_id}" in certification.OPERATIONS_DASHBOARD_PATHS


def test_certification_rejects_unregistered_or_open_responses():
    certification.assert_fail_closed(
        401,
        {"error": {"code": "authentication_failed"}},
    )
    certification.assert_fail_closed(
        403,
        {"error": {"code": "authorization_denied"}},
    )


def test_dashboard_and_generated_contract_certification_are_explicit():
    assert certification.certify.__kwdefaults__ == {
        "expect_operations_dashboard": False,
        "contract_file": None,
    }


def test_generated_contract_loader_requires_an_openapi_paths_object(tmp_path):
    contract = tmp_path / "openapi.json"
    contract.write_text('{"openapi":"3.1.0","paths":{}}', encoding="utf-8")
    assert certification.load_contract(str(contract))["paths"] == {}


def test_middleware_independently_enforces_complete_machine_identity_contract():
    security = Path("app/security.py").read_text()
    control_plane = Path("app/n8n_control_plane.py").read_text()
    for required in (
        'algorithms=["RS256"]',
        "audience=self.settings.audience",
        "issuer=self.settings.issuer",
        '"exp"',
        '"iat"',
        '"iss"',
        '"aud"',
        '"azp"',
        '"jti"',
        '"scope"',
        "authorize_tenant(claims, command.tenant_id)",
    ):
        assert required in security + control_plane
    assert 'expected_client_id="n8n-automation"' in control_plane
    assert 'required_scope="middleware.request.forward"' in control_plane
    assert 'required_scope="middleware.status.read"' in control_plane
    assert 'request.headers.get("X-Correlation-ID") != command.correlation_id' in control_plane
    assert 'request.headers.get("Idempotency-Key") != command.idempotency_key' in control_plane


def test_write_disabled_adapter_contract_is_certified():
    test_source = Path("tests/test_platform_control_plane.py").read_text()
    adapter = Path("app/odoo_provider_adapter.py").read_text()
    assert "test_odoo_adapter_fails_closed_when_write_capability_is_off" in test_source
    assert 'external_effects.get("ODOO_WRITE") is not True' in adapter
