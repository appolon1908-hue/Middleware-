"""ODOO_TO_MIDDLEWARE and MIDDLEWARE_TO_ODOO: both directions of the Odoo loop.

Odoo → Middleware: every outbound call Odoo's add-ons make targets a path
Middleware actually serves, commands carry Idempotency-Key and X-Correlation-ID,
and the calls that are part of the public edge contract reach Middleware through
Caddy → Kong. Middleware → Odoo: the paths Middleware's Odoo sync adapter calls
are Odoo inbound controllers with the right method, and the campaign-control
endpoint registry seeds are compared with those controllers.

Known gaps are strict xfails with the exact finding, never a pass.
"""

from __future__ import annotations

import re

import pytest

from tests.cross_repo.conftest import ROOT, odoo_controller_routes

COMMAND_KINDS = {"COMMAND", "EVENT", "CALLBACK", "RESULT"}


def outbound(summary) -> dict[str, dict]:
    return {
        path: meta
        for path, meta in summary["ODOO_OUTBOUND_TARGETS"].items()
        if not meta["classification"].startswith("OTHER_SERVICE:")
    }


def test_every_odoo_outbound_middleware_call_targets_a_path_middleware_serves(summary):
    assert summary["ODOO_OUTBOUND_NOT_SERVED_BY_MIDDLEWARE"] == []
    for path, meta in outbound(summary).items():
        assert meta["classification"] != "NOT_SERVED_BY_MIDDLEWARE", path


def test_odoo_commands_and_events_carry_idempotency_and_correlation(summary):
    for path, meta in outbound(summary).items():
        if meta["kind"] in COMMAND_KINDS and meta["classification"] == "EDGE_CONTRACT":
            assert "Idempotency-Key" in meta["headers"], path
            assert "X-Correlation-ID" in meta["headers"], path


def test_odoo_edge_contract_calls_go_through_caddy_and_kong(summary):
    for path, meta in outbound(summary).items():
        if meta["classification"] == "EDGE_CONTRACT":
            assert meta["caddy_to_kong"] is True, path


def test_odoo_calls_no_provider_directly_over_http_and_reaches_n8n_only_through_middleware(
    summary, repos
):
    http_direct = [
        f for f in summary["ODOO_DIRECT_PROVIDER_PATHS"] if f["kind"] == "HTTP"
    ]
    assert http_direct == []
    n8n_targets = []
    for file in (repos["Odoo"] / "custom-addons").rglob("*.py"):
        if "/tests/" in file.as_posix():
            continue
        text = file.read_text(encoding="utf-8", errors="ignore")
        if (
            re.search(r"https?://[a-z0-9.-]*n8n[a-z0-9.-]*", text)
            or "N8N_WEBHOOK" in text
        ):
            n8n_targets.append(file.relative_to(repos["Odoo"]).as_posix())
    assert n8n_targets == []


@pytest.mark.xfail(
    strict=True,
    reason="ODOO_DIRECT_PROVIDER_PATH: codestra_klyrow_smtp pins an ir.mail_server to mail.klyrow.com:25 (SMTP relay), an email path that does not go through Middleware; retiring it is an Odoo owner decision",
)
def test_odoo_has_no_direct_provider_path_at_all(summary):
    assert summary["ODOO_DIRECT_PROVIDER_PATHS"] == []


@pytest.mark.xfail(
    strict=True,
    reason="ODOO_OUTBOUND_OUTSIDE_EDGE_CONTRACT: email/SMS transports (/v1/communications/messages), telephony (/v1/telephony/*, /v1/calls/originate), campaign-design preview, control-callback operations and recordings playback call Middleware control-plane/monolith routes that are not in the 8095 public edge contract; each needs an edge contract row (Caddy→Kong) or an internal route contract",
)
def test_every_odoo_outbound_call_is_in_the_public_edge_contract(summary):
    assert summary["ODOO_OUTBOUND_NOT_IN_EDGE_CONTRACT"] == []


@pytest.mark.xfail(
    strict=True,
    reason="ODOO_STATIC_BEARER: the agent-onboarding outbox (POST /api/v1/odoo/events) and the campaign-design preview send a pre-provisioned bearer file (+HMAC) while the edge contract requires odoo-service-jwt (Keycloak client_credentials, azp=odoo-integration); aligning them is an Odoo owner decision",
)
def test_every_odoo_edge_contract_call_authenticates_with_keycloak_client_credentials(
    summary,
):
    for path, meta in outbound(summary).items():
        if meta["classification"] == "EDGE_CONTRACT":
            assert meta["auth"] == "keycloak-client-credentials", path


def middleware_sync_paths() -> set[str]:
    text = (ROOT / "app" / "adapters" / "odoo" / "sync.py").read_text(encoding="utf-8")
    found = set(
        re.findall(r"""["']f?(/api/v1/integration/[A-Za-z0-9/_{}.-]+)["']""", text)
    )
    return {re.sub(r"\{[^}]+\}", "{}", p) for p in found}


def test_middleware_sync_adapter_calls_only_existing_odoo_controllers(repos):
    routes = odoo_controller_routes(repos["Odoo"])
    missing = sorted(p for p in middleware_sync_paths() if p not in routes)
    assert missing == []
    assert "POST" in routes["/api/v1/integration/outbox/claims"]
    assert "GET" in routes["/api/v1/integration/capabilities"]


def campaign_control_seeds() -> dict[str, tuple[str, str]]:
    """Endpoint-registry seeds Middleware's campaign-control client resolves at runtime."""
    seeds: dict[str, tuple[str, str]] = {}
    for file in (ROOT / "migrations" / "versions").glob("*.py"):
        text = file.read_text(encoding="utf-8", errors="ignore")
        for key, method, path in re.findall(
            r'"(odoo\.[a-z_.]+)", "(GET|POST|PATCH|PUT|DELETE)", "(/api/v1/[A-Za-z0-9/_{}.-]+)"',
            text,
        ):
            seeds[key] = (method, path)
    return seeds


def test_middleware_campaign_control_seeds_are_declared():
    seeds = campaign_control_seeds()
    assert {
        "odoo.automation_results.apply",
        "odoo.campaign.actual_state.write",
        "odoo.provider_activities.create",
    } <= set(seeds)
    assert seeds["odoo.provider_activities.create"] == (
        "POST",
        "/api/v1/integration/provider-activities",
    )


@pytest.mark.xfail(
    strict=True,
    reason="MIDDLEWARE_TO_ODOO_PATH_GAP: Middleware's endpoint-registry seeds (0066) name POST /api/v1/integration/automation-results, POST …/campaigns/actual-state, POST …/campaigns/read and POST …/desired-state/read, while Odoo exposes POST …/results, GET …/campaigns/<id> and GET …/desired-state/<type>/<id> and no actual-state controller; one side must move before the campaign-control saga can run",
)
def test_middleware_campaign_control_seeds_match_odoo_controllers(repos):
    routes = odoo_controller_routes(repos["Odoo"])
    mismatches = []
    for key, (method, path) in campaign_control_seeds().items():
        template = re.sub(r"\{[^}]+\}", "{}", path)
        if template not in routes or method not in routes[template]:
            mismatches.append(f"{key}: {method} {path}")
    assert mismatches == []


def test_middleware_private_odoo_rows_never_appear_at_the_public_edge(matrix, repos):
    private = [r for r in matrix["rows"] if r["PUBLIC_PRIVATE"] == "PRIVATE"]
    assert {r["UPSTREAM"] for r in private} == {"odoo:8069"}
    assert all(r["KONG_ROUTE"] == "n/a" and r["CADDY_TO_KONG"] is None for r in private)
    from scripts.cross_repo_contract_matrix import CaddyView, KongView

    kong = KongView.read(repos["Kong"])
    caddy = CaddyView.read(repos["Caddy"])
    for row in private:
        assert (row["METHOD"], row["PATH"]) not in kong.contract_routes
        assert not caddy.routes_to_kong(row["PATH"]) or row["PATH"].startswith(
            "/api/v1/integration/campaign-actions"
        )
