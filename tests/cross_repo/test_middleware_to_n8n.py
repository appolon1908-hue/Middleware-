"""MIDDLEWARE_TO_N8N and the N8N executor boundary.

N8N is a workflow executor only: every HTTP target in its workflow templates is a
Middleware ``/v2/automation`` contract operation, every such node carries the
Authorization, X-Correlation-ID and Idempotency-Key headers, commands and
approvals carry ``idempotency_key`` in the body (the contract's carrier for
those routes), its integration layer names the Middleware audience and issuer,
and its capability catalogue enables no external effect. Middleware → N8N is
the reservation transport: one attested target, one reservation, one POST with
Idempotency-Key and a correlation header, redirects rejected, non-202 refused.
"""

from __future__ import annotations

import json
import re

from tests.cross_repo.conftest import ROOT, load_json

REQUIRED_NODE_HEADERS = {"Authorization", "X-Correlation-ID", "Idempotency-Key"}
BODY_CARRIER_ROUTES = {"/v2/automation/commands", "/v2/automation/approvals"}


def middleware_nodes(repos):
    for file in sorted((repos["N8N"] / "workflows").rglob("*.json")):
        document = load_json(file)
        for node in document.get("nodes", []):
            parameters = node.get("parameters", {})
            url = str(parameters.get("url") or "")
            if "middleware" in url:
                yield file.relative_to(repos["N8N"]).as_posix(), node, parameters, url


def test_every_n8n_http_target_is_a_middleware_automation_contract_operation(
    summary, middleware_contract
):
    assert summary["N8N_TARGETS_NOT_IN_CONTRACT"] == []
    contract = {
        (r["method"], r["path"].split("{", 1)[0].rstrip("/"))
        for r in middleware_contract["routes"]
        if r["classification"] == "shared_edge"
    }
    for url in summary["N8N_TARGETS"]:
        path = re.sub(r"^[a-z]+://[^/]+", "", url).split("{{", 1)[0].rstrip("/")
        assert path.startswith("/v2/automation/"), url
        assert any(
            path == p or path.startswith(p + "/") or p.startswith(path)
            for _m, p in contract
        ), url


def test_every_middleware_node_sends_the_edge_headers_and_the_right_idempotency_carrier(
    repos, middleware_contract
):
    carriers = {
        r["path"]: r["idempotency"]["carrier"] for r in middleware_contract["routes"]
    }
    seen = 0
    for source, node, parameters, url in middleware_nodes(repos):
        seen += 1
        names = {
            h.get("name")
            for h in parameters.get("headerParameters", {}).get("parameters", [])
        }
        assert REQUIRED_NODE_HEADERS <= names, (source, node.get("name"))
        assert parameters.get("method") == "POST", source
        assert int(parameters.get("options", {}).get("timeout", 0)) <= 10000, source
        path = re.sub(r"^[a-z]+://[^/]+", "", url).split("{{", 1)[0].rstrip("/")
        body = json.dumps(
            parameters.get("jsonBody")
            or parameters.get("bodyParameters")
            or parameters.get("body")
            or ""
        )
        if path in BODY_CARRIER_ROUTES:
            assert (
                carriers[path] == "body.idempotency_key" and "idempotency_key" in body
            ), source
        assert node.get("retryOnFail") is not True, (
            "the executor never retries a Middleware POST on its own"
        )
    assert seen >= 6


def test_n8n_integration_layer_targets_middleware_only_and_enables_no_effects(repos):
    layer = load_json(repos["N8N"] / "config" / "integration-layer.v2.json")
    assert (
        layer["status"] == "SOURCE_ONLY" and layer["external_effects_enabled"] is False
    )
    assert layer["identity"]["audience"] == "middleware-api"
    assert layer["identity"]["issuer"] == "https://auth.codestra.co/realms/codestra"
    capabilities = load_json(repos["N8N"] / "config" / "capabilities.json")
    assert capabilities["safety_mode"] == "SOURCE_ONLY"
    flags = {**capabilities["umbrella_controls"], **capabilities["capabilities"]}
    assert flags and not any(flags.values()), {k: v for k, v in flags.items() if v}
    for required in (
        "N8N_EXTERNAL_PROVIDER_WRITES",
        "ODOO_WRITE",
        "SMS_SEND",
        "EMAIL_SEND",
        "PRODUCTION_DIALING",
        "DEAD_LETTER_REPLAY",
    ):
        assert flags[required] is False


def test_n8n_workflows_call_no_provider_or_odoo_directly(repos):
    hosts = set()
    for file in (repos["N8N"] / "workflows").rglob("*.json"):
        for url in re.findall(
            r'"url":\s*"([^"]+)"', file.read_text(encoding="utf-8", errors="ignore")
        ):
            hosts.add(re.sub(r"^[a-z]+://", "", url).split("/", 1)[0])
    assert hosts == {"middleware.invalid"}


def test_middleware_delivers_to_n8n_only_through_the_attested_reservation_transport():
    transport = (ROOT / "app" / "adapters" / "n8n" / "transport.py").read_text(
        encoding="utf-8"
    )
    for guarantee in (
        "async def attest_target",
        "async def reserve_delivery",
        "async def submit_reserved",
        "follow_redirects=False",
        '"Idempotency-Key": delivery.idempotency_key',
        '"X-Codestra-Correlation-ID": str(envelope["correlation_id"])',
        "if response.is_redirect:",
        "if response.status_code != 202:",
        "fresh production target attestation is required",
    ):
        assert guarantee in transport, guarantee
    assert "verify=settings.n8n_target_ca_file or True" in transport
    assert "trust_env=False" in transport
