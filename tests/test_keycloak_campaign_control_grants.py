"""Keycloak desired state agrees with the Odoo catalog, the edge contract, and settings."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from app.adapters.odoo.campaign_control import load_catalog
from app.core import route_policy
from app.core.config import settings

ROOT = Path(__file__).resolve().parents[1]
GRANTS = json.loads(
    (ROOT / "deploy/keycloak/campaign-control-service-clients.v1.json").read_text(encoding="utf-8")
)
EDGE = json.loads((ROOT / "deploy/public-api-route-contract.json").read_text(encoding="utf-8"))
FORBIDDEN = "odoo.campaign.control.write"


def _migration():
    path = ROOT / "migrations/versions/0066_reconcile_odoo_campaign_scope.py"
    spec = importlib.util.spec_from_file_location("migration_0066", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _clients(environment: str) -> dict[str, dict]:
    return {c["client_id"]: c for c in GRANTS["environments"][environment]["clients"]}


@pytest.mark.parametrize("environment", ["staging", "production"])
def test_middleware_never_holds_the_desired_state_write_scope(environment):
    for client in _clients(environment).values():
        assert FORBIDDEN not in client["scopes"], client["client_id"]
    assert {g["scope"] for g in GRANTS["forbidden_grants"]} == {FORBIDDEN}
    assert {g["client_id"] for g in GRANTS["forbidden_grants"]} == {settings.odoo_results_client_id}


@pytest.mark.parametrize("environment", ["staging", "production"])
def test_middleware_to_odoo_client_scopes_equal_registered_route_scopes(environment):
    client = _clients(environment)[settings.odoo_results_client_id]
    registered = {
        spec["scope"]
        for spec in load_catalog()["operations"].values()
        if spec["registered_by"] in {"0050", "0066"}
    }
    assert set(client["scopes"]) == registered
    assert client["direction"] == "middleware_to_odoo"
    assert client["interactive_flows_enabled"] is False


@pytest.mark.parametrize("environment", ["staging", "production"])
def test_credential_and_audience_match_the_registry_rows(environment):
    migration = _migration()
    env_row = next(row for row in migration.ENVIRONMENTS if row[0] == environment)
    _env, _base_url, credential, audience = env_row[:4]
    client = _clients(environment)[settings.odoo_results_client_id]
    assert client["credential_reference_id"] == credential
    assert client["audience"] == audience


def test_staging_grants_are_bound_to_the_test_syn_triple_only():
    migration = _migration()
    organization, business_unit, campaign = migration.TEST_SYN_BINDING
    for client in _clients("staging").values():
        assert client["organizations"] == [organization]
        assert client["business_units"] == [business_unit]
        assert client["campaigns"] == [campaign]


@pytest.mark.parametrize("environment", ["staging", "production"])
def test_every_edge_contract_scope_is_granted_to_exactly_one_direction(environment):
    clients = _clients(environment)
    by_scope: dict[str, set[str]] = {}
    for client in clients.values():
        for scope in client["scopes"]:
            by_scope.setdefault(scope, set()).add(client["direction"])
    for row in EDGE["routes"]:
        scope = row.get("scope")
        if scope:
            assert by_scope.get(scope), f"{scope} not granted in {environment}"
            assert len(by_scope[scope]) == 1, f"{scope} granted to several directions"
    # Inbound scopes the handlers enforce (route policy) must be granted to the
    # inbound directions, never to the Middleware->Odoo client.
    outbound = set(clients[settings.odoo_results_client_id]["scopes"])
    for scope in {"odoo.campaigns.read", "n8n.results.read", "n8n.results.submit"}:
        assert scope not in outbound
        assert scope in by_scope


def test_n8n_client_ids_and_scopes_match_the_middleware_validator():
    production = _clients("production")
    n8n = production[settings.n8n_campaign_service_client_id]
    assert set(n8n["scopes"]) == {"n8n.results.submit", "n8n.results.read"}
    assert n8n["audience"] == settings.n8n_service_audience
    reader_scopes = {
        scope for _m, _t, _p, auth, scope in route_policy.INTEGRATION_SERVICE_JWT_ROUTES if auth == "odoo-service-jwt"
    }
    assert reader_scopes == {"odoo.campaigns.read"}
    assert set(production["codestra-odoo-campaign-reader-production"]["scopes"]) == reader_scopes


def test_production_declaration_states_no_activation():
    assert "not authorized" in GRANTS["environments"]["production"]["activation"]
