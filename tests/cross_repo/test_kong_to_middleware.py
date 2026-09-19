"""KONG_TO_MIDDLEWARE: Kong's Middleware routes are the Middleware contract, on 8095 only."""

from __future__ import annotations

from collections import Counter

from tests.cross_repo.conftest import load_json

CANONICAL_UPSTREAM = "middleware-integration-api:8095"
V3_ROUTES = {
    ("POST", "/platform/v1/commands"),
    ("GET", "/platform/v1/kernel/describe"),
    ("GET", "/platform/v1/operations/{operation_id}"),
    ("POST", "/platform/v1/operations/{operation_id}/cancel"),
    ("POST", "/platform/v1/operations/{operation_id}/replay"),
    ("GET", "/platform/v1/operations/{operation_id}/timeline"),
}


def test_kong_vendors_the_exact_middleware_contract(summary, repos):
    assert summary["KONG_VENDORED_CONTRACT_STALE"] is False
    assert summary["KONG_VENDORED_CONTRACT_HASH"] == summary["MIDDLEWARE_CONTRACT_HASH"]
    vendored = load_json(
        repos["Kong"] / "config" / "middleware-public-api-route-contract.v1.json"
    )
    ours = load_json(repos["Middleware-"] / "deploy" / "public-api-route-contract.json")
    assert vendored == ours


def test_every_shared_edge_operation_has_exactly_one_kong_route_on_the_canonical_upstream(
    shared_rows, summary
):
    assert summary["KONG_MISSING_ROUTES"] == []
    assert (
        summary["KONG_STABLE_ROUTES"] == summary["SHARED_EDGE_ROWS"] == len(shared_rows)
    )
    assert summary["KONG_UPSTREAM_NON_CANONICAL"] == []
    assert all(row["KONG_UPSTREAM"] == CANONICAL_UPSTREAM for row in shared_rows)
    names = Counter(row["KONG_ROUTE"] for row in shared_rows)
    assert [name for name, count in names.items() if count > 1] == [], (
        "DUPLICATE_KONG_ROUTES"
    )


def test_kong_security_authority_matches_the_middleware_contract_row_for_row(summary):
    assert summary["AUDIENCE_MISMATCHES"] == []
    assert summary["SCOPE_MISMATCHES"] == []
    assert summary["AZP_MISMATCHES"] == []
    assert summary["AUTH_MISMATCHES"] == []
    assert summary["METHOD_MISMATCHES"] == []


def test_kong_keeps_business_authorization_in_middleware(shared_rows, repos):
    """Kong enforces issuer, audience, scope and azp-to-consumer mapping; the symbolic
    client families and tenant/resource ownership are re-authorized by Middleware."""
    for row in shared_rows:
        assert row["KONG_ACCESS_CLASS"] in {"AUTHENTICATED", "SERVICE_AUTHENTICATED"}, (
            row["PATH"]
        )
        assert row["KONG_TENANT_POLICY"] == "CLAIM_ONLY_MIDDLEWARE_VALIDATES", row[
            "PATH"
        ]
        assert row["KONG_IDENTITY_PROPAGATION"] == "OIDC_STRIP_AND_CONTRACT_METADATA", (
            row["PATH"]
        )
    canonical = load_json(
        repos["Kong"] / "config" / "kong-canonical-middleware-routes.json"
    )
    for route in canonical["contractRoutes"]:
        assert set(route["requiredPlugins"]) == {
            "openid-connect",
            "post-function",
            "correlation-id",
            "rate-limiting",
            "request-size-limiting",
        }, route["name"]
        assert route["stripPath"] is False and route["preserveHost"] is True


def test_kong_does_not_retry_middleware_posts_and_does_not_enable_provider_effects(
    summary, repos
):
    assert summary["KONG_PROVIDER_EFFECTS_ENABLED"] is False
    assert summary["KONG_LEGACY_HOST_ENABLED"] is False
    foundation = load_json(repos["Kong"] / "config" / "kong-gateway-foundation.v1.json")
    services = {s["serviceId"]: s for s in foundation["services"]}
    for service_id in ("middleware-integration-api", "middleware-v3-command-api"):
        service = services[service_id]
        assert service["upstream"] == {
            "protocol": "http",
            "host": "middleware-integration-api",
            "port": 8095,
        }
        assert service["retryProfile"] == "NONE"
        assert foundation["profiles"]["retry"]["NONE"]["retries"] == 0


def test_no_activatable_kong_route_targets_middleware_on_8080(repos):
    """CANONICAL_8080=0: the only Middleware-bound 8080 binding left in the registry is the
    retired alias behind the PREPARED_DISABLED provider-control contract."""
    foundation = load_json(repos["Kong"] / "config" / "kong-gateway-foundation.v1.json")
    middleware_8080 = [
        s
        for s in foundation["services"]
        if s["upstream"].get("port") == 8080
        and "middleware" in s["upstream"].get("host", "")
    ]
    assert [s["serviceId"] for s in middleware_8080] == ["provider-control-middleware"]
    assert middleware_8080[0]["lifecycle"] == "PREPARED_DISABLED"
    routes = [
        r
        for r in foundation["routes"]
        if r["serviceId"] == "provider-control-middleware"
    ]
    assert routes and all(r["activation"] == "PREPARED_DISABLED" for r in routes)
    canonical = load_json(
        repos["Kong"] / "config" / "kong-canonical-middleware-routes.json"
    )
    assert all(r["servicePort"] == 8095 for r in canonical["contractRoutes"])
    authority = load_json(
        repos["Kong"] / "config" / "kong-middleware-authority.v2.json"
    )
    assert authority["upstream"] == {"host": "middleware-integration-api", "port": 8095}


def test_direct_provider_routes_are_zero_in_the_production_inventory(repos):
    """DIRECT_PROVIDER_ROUTES=0: no production route's upstream is a provider (Klyrow,
    Telnexa, VICIdial), N8N or Odoo. Middleware-bound routes use 8095; the two live
    routes the readback still shows on the retired 8080 alias are RETIRE_CANDIDATE /
    DELETE in the registry and denied by the canonical manifest (CANONICAL_8080=0)."""
    inventory = load_json(
        repos["Kong"] / "config" / "kong-production-route-inventory.v2.json"
    )
    foundation = load_json(repos["Kong"] / "config" / "kong-gateway-foundation.v1.json")
    registry = {r["routeId"]: r for r in foundation["routes"]}
    provider_markers = ("klyrow", "telnexa", "vicidial", "n8n.", "odoo")
    direct = [
        r["name"]
        for r in inventory["routes"]
        if any(m in r["service"]["host"].lower() for m in provider_markers)
    ]
    assert direct == []
    middleware_bound = [
        r for r in inventory["routes"] if "middleware" in r["service"]["host"]
    ]
    assert middleware_bound
    for route in middleware_bound:
        if route["service"]["port"] == 8095:
            continue
        assert route["service"]["host"] == "appolon-middleware-integration-api", route[
            "name"
        ]
        entry = registry[route["name"]]
        assert (
            entry["lifecycle"] == "RETIRE_CANDIDATE"
            and entry["disposition"] == "DELETE"
        ), route["name"]
    aliases = {
        (a["host"], a["port"]): a["role"]
        for a in foundation["boundaryRules"]["middlewareUpstreamAliases"]
    }
    assert aliases[("appolon-middleware-integration-api", 8080)].startswith("RETIRED")
    assert aliases[("middleware-integration-api", 8095)] == "CANONICAL_PUBLIC_API"


def test_v3_kernel_routes_are_prepared_but_pending_the_frozen_contract(
    summary, repos, middleware_contract
):
    assert summary["V3_PENDING_FINAL_MIDDLEWARE_CONTRACT"] is True
    pending = load_json(
        repos["Kong"] / "config" / "kong-middleware-v3-command-routes.v1.json"
    )
    assert (
        pending["status"] == "V3_PENDING_FINAL_MIDDLEWARE_CONTRACT"
        and pending["V3_PENDING_FINAL_MIDDLEWARE_CONTRACT"] is True
    )
    assert (
        pending["runtimeApplyAuthorized"] is False
        and pending["activation"]["runtimeApplyAuthorized"] is False
    )
    assert {
        (m, r["path"]) for r in pending["routes"] for m in r["methods"]
    } == V3_ROUTES
    assert pending["security"]["businessAuthorizationInKong"] is False
    assert pending["commonPolicy"]["gatewayRetriesNonIdempotentPosts"] is False
    contract_keys = {(r["method"], r["path"]) for r in middleware_contract["routes"]}
    assert not (V3_ROUTES & contract_keys), (
        "the V3 routes must not be in the frozen contract yet"
    )
    for entry in summary["V3_PENDING_ROUTES"]:
        assert (
            entry["KONG_ROUTE"] == "V3_PENDING_FINAL_MIDDLEWARE_CONTRACT"
            and entry["IN_MIDDLEWARE_CONTRACT"] is False
        )
