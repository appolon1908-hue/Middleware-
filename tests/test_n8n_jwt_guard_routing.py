from pathlib import Path


MAIN = Path("app/main.py").read_text()
RUNTIME = Path("app/entrypoints/runtime.py").read_text()


def test_main_guard_delegates_only_exact_n8n_service_jwt_routes():
    assert '("POST", "/api/v1/automation/policy-check")' in MAIN
    assert '("POST", "/api/v1/integrations/n8n/results")' in MAIN
    assert "(request.method, request.url.path) not in N8N_SERVICE_JWT_ROUTES" in MAIN


def test_split_runtime_guard_delegates_only_exact_n8n_service_jwt_routes():
    assert '("POST", "/api/v1/automation/policy-check")' in RUNTIME
    assert '("POST", "/api/v1/integrations/n8n/results")' in RUNTIME
    assert "(request.method, request.url.path) not in N8N_SERVICE_JWT_ROUTES" in RUNTIME


def test_legacy_guard_remains_default_for_other_api_routes():
    assert "verify_bearer(" in MAIN
    assert "verify_bearer(" in RUNTIME
