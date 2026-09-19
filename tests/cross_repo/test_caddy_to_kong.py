"""CADDY_TO_KONG: the public edge reaches Middleware, Odoo and N8N only through Kong."""

from __future__ import annotations

import re

from tests.cross_repo.conftest import load_json

REQUIRED_EDGE_HEADERS = (
    "Authorization",
    "X-Correlation-ID",
    "Idempotency-Key",
    "traceparent",
    "tracestate",
)


def test_every_shared_edge_operation_is_routed_to_kong(shared_rows, summary):
    fallthrough = [
        f"{r['METHOD']} {r['PATH']}"
        for r in shared_rows
        if r["CADDY_TO_KONG"] is not True
    ]
    assert fallthrough == [], (
        f"shared_edge operations Caddy does not hand to Kong: {fallthrough}"
    )
    assert summary["CADDY_FALLTHROUGH_ROUTES"] == []


def test_denied_operations_are_routed_to_kong_not_the_legacy_upstream(matrix, repos):
    """Kong answers the retired paths with its deny routes; Caddy must not let them
    fall through to the transitional legacy upstream."""
    from scripts.cross_repo_contract_matrix import CaddyView

    caddy = CaddyView.read(repos["Caddy"])
    denied = [r["PATH"] for r in matrix["rows"] if r["PUBLIC_PRIVATE"] == "DENIED"]
    assert denied and all(caddy.routes_to_kong(path) for path in denied)


def test_caddy_contract_prefixes_equal_the_site_matcher(summary):
    assert summary["CADDY_CONTRACT_PREFIXES_MATCH_SITE"] is True


def test_caddy_deletes_client_identity_headers_and_preserves_the_edge_headers(
    summary, repos
):
    assert summary["CADDY_STRIPS_CLIENT_IDENTITY_HEADERS"] is True
    assert summary["CADDY_REQUIRED_HEADERS_BLOCKED"] == []
    assert summary["CADDY_HEADER_UP_SET"] == ["Host", "X-Real-IP"]
    contract = load_json(repos["Caddy"] / "config" / "caddy-kong-contract.v1.json")
    assert (
        tuple(contract["identityHeaders"]["preservedToKong"]) == REQUIRED_EDGE_HEADERS
    )
    deleted = set(contract["identityHeaders"]["deletedBeforeKong"])
    assert {
        "X-Authenticated-Client",
        "X-Authenticated-Tenant",
        "X-Authenticated-Role",
        "X-Consumer-ID",
        "X-Codestra-Gateway-Secret",
    } <= deleted
    assert set(summary["CADDY_HEADER_UP_DELETED"]) == deleted


def test_caddy_never_targets_middleware_odoo_or_n8n_directly(repos):
    site = (repos["Caddy"] / "sites" / "api.codestra.co.caddy").read_text(
        encoding="utf-8"
    )
    contract = load_json(repos["Caddy"] / "config" / "caddy-kong-contract.v1.json")
    assert contract["publicApiDirect"] == {
        "PUBLIC_API_DIRECT_TO_MIDDLEWARE": 0,
        "PUBLIC_API_DIRECT_TO_ODOO": 0,
        "PUBLIC_API_DIRECT_TO_N8N": 0,
        "rule": contract["publicApiDirect"]["rule"],
    }
    for forbidden in (
        ":8095",
        ":8069",
        ":5678",
        "http://middleware",
        "https://middleware",
        "odoo:",
        "n8n:",
    ):
        assert forbidden not in site, forbidden
    upstreams = set(re.findall(r"reverse_proxy \{\$([A-Z_]+)\}", site))
    assert upstreams == {
        "CADDY_KONG_UPSTREAM",
        "CADDY_REALTIME_UPSTREAM",
        "CADDY_LEGACY_API_UPSTREAM",
    }


def test_kong_matched_paths_have_no_legacy_fallback(repos):
    """A request matched by @kong is handled by the Kong reverse_proxy block alone: when
    Kong is unavailable it fails there; the legacy catch-all only serves unmatched paths."""
    site = (repos["Caddy"] / "sites" / "api.codestra.co.caddy").read_text(
        encoding="utf-8"
    )
    kong_block = re.search(r"handle @kong \{(.*?)\n\t\t\}", site, re.S)
    assert kong_block is not None
    assert "CADDY_KONG_UPSTREAM" in kong_block.group(1)
    assert "CADDY_LEGACY_API_UPSTREAM" not in kong_block.group(1)
    assert "lb_try_duration" not in kong_block.group(
        1
    ) and "fail_duration" not in kong_block.group(1)


def test_caddy_pins_the_same_middleware_contract_digest_as_kong(summary, repos):
    contract = load_json(repos["Caddy"] / "config" / "caddy-kong-contract.v1.json")
    assert (
        contract["middlewareEdgeContract"]["sha256"]
        == summary["MIDDLEWARE_CONTRACT_HASH"]
    )
    assert (
        contract["middlewareEdgeContract"]["sharedEdgeOperations"]
        == summary["SHARED_EDGE_ROWS"]
    )
    assert (
        contract["middlewareEdgeContract"]["deniedOperations"] == summary["DENIED_ROWS"]
    )
