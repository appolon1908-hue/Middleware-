"""Port contract across the six core repositories (mission phase 23).

Every reference to a core port in the tracked source of Middleware, Kong, Caddy,
Keycloak, Odoo and N8N is classified from its own context. The canonical
Middleware listener is 8095; 8080 references are Keycloak's own listener and
token endpoints, Kong's retired/denied Middleware alias, standby fixtures,
legacy provider adapters marked for deprecation, or unrelated listeners
(websocket gateway, observability alert API, the legacy monolith canary), and
nothing activatable binds Middleware on 8080.
"""

from __future__ import annotations

import pytest

from tests.cross_repo.conftest import _root, load_json


@pytest.fixture(scope="module")
def port_report(repos):
    from scripts.cross_repo_port_contract import scan

    return scan(_root())


def test_every_port_reference_is_classified_and_no_canonical_8080_exists(port_report):
    summary = port_report["summary"]
    assert summary["UNCLASSIFIED"] == []
    assert summary["CANONICAL_8080"] == 0
    assert summary["BY_CLASSIFICATION"].get("UNCLASSIFIED", 0) == 0


def test_middleware_canonical_listener_is_8095_everywhere_it_is_deployed(repos):
    dockerfile = (repos["Middleware-"] / "Dockerfile").read_text(encoding="utf-8")
    assert "EXPOSE 8095" in dockerfile and "EXPOSE 8080" not in dockerfile
    compose = (repos["Middleware-"] / "deploy" / "compose.runtime.yaml").read_text(
        encoding="utf-8"
    )
    assert "--port=8095" in compose or '"8095"' in compose or "8095:" in compose
    contract = load_json(
        repos["Middleware-"] / "deploy" / "public-api-route-contract.json"
    )
    assert (
        contract["listener_port"] == 8095
        and contract["service"] == "middleware-integration-api"
    )


def test_8080_references_outside_kong_are_never_middleware_upstreams(port_report):
    for row in port_report["rows"]:
        if row["port"] != "8080" or row["repository"] == "Kong":
            continue
        assert row["classification"] not in {
            "MIDDLEWARE_RETIRED_ALIAS_DENIED",
            "UNCLASSIFIED",
        }, row
        if row["repository"] in {"Caddy", "N8N"}:
            pytest.fail(f"{row['repository']} must not reference 8080 at all: {row}")


def test_kong_8080_references_are_retired_standby_legacy_or_test_only(port_report):
    allowed = {
        "MIDDLEWARE_RETIRED_ALIAS_DENIED",
        "KONG_STANDBY_AUTH_FIXTURE",
        "KONG_TEST_UPSTREAM_RETIRE_CANDIDATE",
        "KONG_TRANSITIONAL_CERTIFICATION_PROBE",
        "LEGACY_PROVIDER_ADAPTER_DEPRECATE",
        "KONG_VALIDATOR_OR_TEST_REFERENCE",
        "COMMUNITY_N8N_EGRESS_PLAIN_HTTP_PROPOSED_TLS",
        "KEYCLOAK_HTTP_LISTENER_OR_TOKEN_ENDPOINT",
        "TEST_FIXTURE",
    }
    for row in port_report["rows"]:
        if row["port"] == "8080" and row["repository"] == "Kong":
            assert row["classification"] in allowed, row


def test_keycloak_8080_is_only_its_own_listener_and_token_endpoints(port_report, repos):
    keycloak_rows = [
        r
        for r in port_report["rows"]
        if r["repository"] == "Keycloak" and r["port"] == "8080"
    ]
    assert keycloak_rows and all(
        r["classification"] == "KEYCLOAK_HTTP_LISTENER_OR_TOKEN_ENDPOINT"
        for r in keycloak_rows
    )
    compose = (repos["Keycloak"] / "compose.yaml").read_text(encoding="utf-8")
    assert "127.0.0.1:${KEYCLOAK_HTTP_PORT:-8080}:8080" in compose, (
        "Keycloak's HTTP listener stays bound to loopback"
    )


def test_odoo_and_n8n_listeners_are_reached_only_through_middleware(
    port_report, middleware_contract
):
    odoo_rows = [r for r in port_report["rows"] if r["port"] == "8069"]
    assert odoo_rows and {r["repository"] for r in odoo_rows} <= {"Middleware-", "Odoo"}
    n8n_rows = [r for r in port_report["rows"] if r["port"] == "5678"]
    assert n8n_rows
    for row in n8n_rows:
        if row["repository"] in {"N8N", "Middleware-"}:
            continue
        # The only other 5678 references are the human editor host (automation.codestra.co)
        # behind the Keycloak browser flow / oauth2-proxy — never the API edge.
        context = (row["file"] + " " + row["context"]).lower()
        assert row["repository"] in {"Kong", "Caddy"} and (
            "editor" in context
            or "community_n8n" in context
            or "community-n8n" in context
            or "validate_repository" in context
        ), row
        assert "api.codestra.co" not in context
    private = [
        r
        for r in middleware_contract["routes"]
        if r["classification"] == "private_only"
    ]
    assert {r["upstream"] for r in private} == {"odoo:8069"}
