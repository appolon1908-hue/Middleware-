"""The public API route contract, its pinned hash, the shared policy and both apps agree."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from app.core import route_policy
from app.entrypoints.integration_api import app as integration_app
from app.main import app as main_app

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "deploy/public-api-route-contract.json"
PINNED = ROOT / "deploy/public-api-route-contract.sha256"
DESIRED_STATE = ROOT / "deploy/keycloak/campaign-control-service-clients.v1.json"
COMPOSE = ROOT / "deploy/compose.runtime.yaml"

CANONICAL = {
    ("POST", "/api/v1/integrations/n8n/results"): "n8n.results.submit",
    ("GET", "/api/v1/integrations/n8n/results/{event_id}"): "n8n.results.read",
    ("GET", "/api/v1/integrations/odoo/campaigns/{campaign_id}"): "odoo.campaigns.read",
    ("GET", "/api/v1/integrations/odoo/campaigns/{campaign_id}/desired-state"): "odoo.campaigns.read",
}
INGRESS_SCOPES = set(CANONICAL.values())
OUTBOUND_SCOPE = "odoo.campaign.control.read"
FORBIDDEN_SCOPE = "odoo.campaign.control.write"
# Handler-authenticated but not yet an accepted edge exposure (mirrors
# scripts/audit_release_endpoints.py EDGE_EXPOSURE_UNDECIDED).
EDGE_EXPOSURE_UNDECIDED = {
    ("POST", "/api/v1/campaign-designs/preview"),
    ("POST", "/api/v1/campaign-designs/approvals"),
}


def contract() -> dict:
    return json.loads(CONTRACT.read_text(encoding="utf-8"))


def route_table(application) -> set[tuple[str, str]]:
    table: set[tuple[str, str]] = set()

    def walk(routes, prefix=""):
        for route in routes:
            original = getattr(route, "original_router", None)
            if original is not None:
                context = getattr(route, "include_context", None)
                walk(original.routes, prefix + (getattr(context, "prefix", "") or ""))
                continue
            path = getattr(route, "path", None)
            if path is None:
                continue
            for method in getattr(route, "methods", None) or ():
                table.add((method.upper(), prefix + path))

    walk(application.routes)
    return table


def test_contract_hash_is_pinned_and_canonical():
    canonical = json.dumps(contract(), sort_keys=True, separators=(",", ":")).encode("utf-8")
    assert PINNED.read_text(encoding="utf-8").strip() == hashlib.sha256(canonical).hexdigest()


def test_contract_declares_the_four_canonical_routes_with_exact_scopes():
    rows = {(r["method"], r["path"]): r.get("scope") for r in contract()["routes"]}
    for key, scope in CANONICAL.items():
        assert rows.get(key) == scope, key
    assert contract()["service"] == "middleware-integration-api"
    assert contract()["listener_port"] == 8095
    assert FORBIDDEN_SCOPE not in CONTRACT.read_text(encoding="utf-8")


def test_contract_and_shared_route_policy_are_the_same_table():
    rows = {(r["method"], r["path"]): r.get("scope") for r in contract()["routes"] if r["auth"] != "callback-jwt"}
    policy = {(r["method"], r["path"]): r.get("scope") for r in route_policy.service_jwt_route_contract()}
    assert set(policy) - EDGE_EXPOSURE_UNDECIDED == set(rows)
    for key, scope in rows.items():
        # Exact-path n8n rows carry their scope only in the contract; path-parameter
        # rows carry it in both places and must not drift.
        if policy[key] is not None:
            assert policy[key] == scope, key


@pytest.mark.parametrize("name,application", [("integration_api", integration_app), ("main", main_app)])
def test_both_apps_declare_every_contract_route_with_the_exact_method(name, application):
    table = route_table(application)
    for row in contract()["routes"]:
        assert (row["method"], row["path"]) in table, (name, row)
    for method, path in CANONICAL:
        other_methods = {m for m, p in table if p == path} - {method}
        assert not (other_methods - {"HEAD", "OPTIONS"}), (name, path, other_methods)


@pytest.mark.parametrize("application", [integration_app, main_app])
def test_retired_campaign_paths_are_absent(application):
    assert not [
        path
        for _method, path in route_table(application)
        if "campaign-actions" in path or "campaign-commands" in path
    ]


def test_every_integration_route_is_classified():
    shared_edge = {(r["method"], r["path"]) for r in contract()["routes"]}
    classification: dict[tuple[str, str], str] = {}
    for key in route_table(integration_app) | route_table(main_app):
        if not key[1].startswith("/api/v1/integrations/"):
            continue
        if "campaign-actions" in key[1] or "campaign-commands" in key[1]:
            classification[key] = "denied"
        elif key in shared_edge:
            classification[key] = "shared_edge"
        else:
            classification[key] = "private_only"
    assert set(classification.values()) <= {"shared_edge", "private_only", "denied"}
    assert {k for k, v in classification.items() if v == "shared_edge"} == set(CANONICAL)
    assert not [k for k, v in classification.items() if v == "denied"]
    # Private-only routes stay behind the shared-secret guard.
    for method, path in classification:
        if classification[(method, path)] == "private_only":
            sample = path.replace("{command_id}", "x").replace("{provider}", "odoo").replace("{post_id}", "x").replace("{action}", "x")
            assert not route_policy.handler_authenticated(method, sample), (method, path)


def test_compose_deploys_the_integration_api_entrypoint():
    compose = COMPOSE.read_text(encoding="utf-8")
    assert "middleware-integration-api:" in compose
    assert "app.entrypoints.integration_api" in compose


def test_keycloak_desired_state_separates_ingress_and_outbound_scopes():
    document = json.loads(DESIRED_STATE.read_text(encoding="utf-8"))
    assert any(f["scope"] == FORBIDDEN_SCOPE for f in document["forbidden_grants"])
    for environment, state in document["environments"].items():
        for client in state["clients"]:
            scopes = set(client["scopes"])
            assert FORBIDDEN_SCOPE not in scopes, (environment, client["client_id"])
            if OUTBOUND_SCOPE in scopes:
                assert client["direction"] == "middleware_to_odoo", (environment, client["client_id"])
                assert not (scopes & INGRESS_SCOPES), (environment, client["client_id"])
            if scopes & INGRESS_SCOPES:
                assert client["audience"] == "codestra-middleware", (environment, client["client_id"])
                assert client["interactive_flows_enabled"] is False
                assert client["service_accounts_enabled"] is True
    staging = document["environments"]["staging"]
    for client in staging["clients"]:
        if client["direction"] == "certification_negative":
            # Negative identities prove denial: wrong audience carries no ingress
            # scope; wrong tenant never holds TEST_SYN.
            assert not (set(client["scopes"]) & INGRESS_SCOPES) or "TEST_SYN" not in client["campaigns"]
        else:
            assert client["campaigns"] == ["TEST_SYN"], client["client_id"]
    ids = {c["client_id"] for c in staging["clients"]}
    assert {"test-syn-n8n-submit", "test-syn-n8n-read", "test-syn-odoo-reader", "test-syn-wrong-audience"} <= ids
