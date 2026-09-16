"""Both API entrypoints delegate service-JWT exemptions to one shared policy."""

from pathlib import Path

from app.core import route_policy

MAIN = Path("app/main.py").read_text(encoding="utf-8")
RUNTIME = Path("app/entrypoints/runtime.py").read_text(encoding="utf-8")

APPROVED_N8N_ROUTES = {
    ("POST", "/api/v1/automation/policy-check"),
    ("POST", "/api/v1/campaign-designs/preview"),
    ("POST", "/api/v1/campaign-designs/approvals"),
    ("POST", "/api/v1/integrations/n8n/results"),
}
APPROVED_INTEGRATION_ROUTES = {
    ("GET", "/api/v1/integrations/odoo/campaigns/{campaign_id}", "odoo.campaigns.read"),
    ("GET", "/api/v1/integrations/odoo/campaigns/{campaign_id}/desired-state", "odoo.campaigns.read"),
    ("GET", "/api/v1/integrations/n8n/results/{event_id}", "n8n.results.read"),
}


def test_shared_policy_is_exactly_the_approved_route_set():
    assert set(route_policy.N8N_SERVICE_JWT_ROUTES) == APPROVED_N8N_ROUTES
    assert {
        (method, template, scope)
        for method, template, _pattern, _auth, scope in route_policy.INTEGRATION_SERVICE_JWT_ROUTES
    } == APPROVED_INTEGRATION_ROUTES


def test_both_entrypoints_delegate_to_the_shared_policy_and_keep_no_local_copy():
    for source in (MAIN, RUNTIME):
        assert "route_policy.handler_authenticated(request.method, request.url.path)" in source
        assert "verify_bearer(" in source
        assert "N8N_SERVICE_JWT_ROUTES = " not in source
        assert "CALLBACK_JWT_PATH = " not in source
        assert "INTEGRATION_SERVICE_JWT_ROUTES = " not in source
        assert "campaign-actions" not in source
        assert "campaign-commands" not in source


def test_exemptions_are_exact_method_and_path_not_prefixes():
    ok = route_policy.handler_authenticated
    assert ok("POST", "/api/v1/integrations/n8n/results")
    assert not ok("GET", "/api/v1/integrations/n8n/results")
    assert not ok("POST", "/api/v1/integrations/n8n/results/")
    assert not ok("POST", "/api/v1/integrations/n8n/results/anything")
    assert ok("GET", "/api/v1/integrations/n8n/results/event-1")
    assert not ok("POST", "/api/v1/integrations/n8n/results/event-1")
    assert not ok("GET", "/api/v1/integrations/n8n/results/event-1/extra")
    assert ok("GET", "/api/v1/integrations/odoo/campaigns/CMP-MBL")
    assert ok("GET", "/api/v1/integrations/odoo/campaigns/CMP-MBL/desired-state")
    assert not ok("GET", "/api/v1/integrations/odoo/campaigns/CMP-MBL/other")
    assert not ok("GET", "/api/v1/integrations/odoo/campaigns/")
    assert not ok("POST", "/api/v1/integrations/odoo/campaigns/CMP-MBL")
    assert not ok("GET", "/api/v1/integrations/odoo/campaign-commands/x")
    assert not ok("POST", "/api/v1/integration/campaign-actions")
    assert ok("POST", "/api/v1/callbacks/anything")


def test_contract_rows_expose_auth_and_scope_for_every_exempt_route():
    rows = route_policy.service_jwt_route_contract()
    assert {(r["method"], r["path"]) for r in rows} == APPROVED_N8N_ROUTES | {
        (m, p) for m, p, _s in APPROVED_INTEGRATION_ROUTES
    }
    assert all(r["auth"] in {"n8n-service-jwt", "odoo-service-jwt"} for r in rows)
    assert {r["scope"] for r in rows if "scope" in r} == {"odoo.campaigns.read", "n8n.results.read"}
