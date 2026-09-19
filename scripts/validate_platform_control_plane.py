#!/usr/bin/env python3
"""Validate repository-owned pieces of the platform control-plane contract."""

from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "contracts" / "platform-control-plane.v1.json"
HMAC_VECTOR_PATH = ROOT / "contracts" / "odoo-hmac-test-vector.v1.json"
MAIN_PATH = ROOT / "app" / "main.py"
# Route ownership: the v2 automation router is canonical and the deprecated
# n8n aliases are a monolith-only group; both are mounted only through the
# single router registry. The deployed integration entrypoint never mounts
# the aliases, and the edge contract keeps them denied.
REGISTRY_PATH = ROOT / "app" / "router_registry.py"
DEPLOYED_ENTRYPOINT_PATH = ROOT / "app" / "entrypoints" / "integration_api.py"
APP_ROOT = ROOT / "app"
EDGE_CONTRACT_PATH = ROOT / "deploy" / "public-api-route-contract.json"
N8N_PATH = ROOT / "app" / "n8n_control_plane.py"
API_INPUTS_PATH = ROOT / "app" / "api_inputs.py"
ODOO_PATH = ROOT / "app" / "odoo_provider_adapter.py"
WORKER_PATH = ROOT / "workers" / "run_temporal.py"
WORKFLOW_PATH = ROOT / "app" / "temporal_workflows.py"
CAPABILITIES_PATH = ROOT / "config" / "capabilities.v2.json"
ROUTE_AUTHORITY_PATH = ROOT / "config" / "route-authority.v1.json"


def fail(message: str) -> None:
    raise SystemExit(f"PLATFORM_CONTROL_PLANE=FAIL {message}")


def main() -> int:
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    vector = json.loads(HMAC_VECTOR_PATH.read_text(encoding="utf-8"))
    capabilities = json.loads(CAPABILITIES_PATH.read_text(encoding="utf-8"))[
        "capabilities"
    ]
    route_authority = json.loads(ROUTE_AUTHORITY_PATH.read_text(encoding="utf-8"))
    main_source = MAIN_PATH.read_text(encoding="utf-8")
    registry_source = REGISTRY_PATH.read_text(encoding="utf-8")
    deployed_source = DEPLOYED_ENTRYPOINT_PATH.read_text(encoding="utf-8")
    edge_contract = json.loads(EDGE_CONTRACT_PATH.read_text(encoding="utf-8"))
    n8n_source = N8N_PATH.read_text(encoding="utf-8")
    api_inputs_source = API_INPUTS_PATH.read_text(encoding="utf-8")
    odoo_source = ODOO_PATH.read_text(encoding="utf-8")
    worker_source = WORKER_PATH.read_text(encoding="utf-8")
    workflow_source = WORKFLOW_PATH.read_text(encoding="utf-8")

    if contract.get("status") != "PREPARED_DISABLED":
        fail("source integration must remain PREPARED_DISABLED")
    if contract.get("decision") != "middleware_adopts_automation_v2":
        fail("automation v2 authority decision drifted")
    repositories = contract.get("repositories", {})
    if repositories.get("write_authority") != "appolon1908-hue/Middleware-":
        fail("Middleware repository is not declared write authority")

    edge = contract.get("n8n_to_middleware", {})
    expected_edge = {
        "canonical_submit_path": "/v2/automation/commands",
        "canonical_read_path": "/v2/automation/commands/{command_id}",
        "client_id": "n8n-crm-automation",
        "audience": "middleware-api",
        "submit_scope": "automation.command.crm",
        "read_scope": "automation.command.read",
        "tenant_authority": "verified_token_and_durable_job",
        "header_body_agreement_required": True,
        "direct_provider_access": False,
    }
    for key, value in expected_edge.items():
        if edge.get(key) != value:
            fail(f"n8n edge field {key} drifted")

    automation_authority = route_authority.get("automation", {})
    if route_authority.get("decision") != "middleware_adopts_automation_v2":
        fail("automation v2 authority decision drifted")
    if (
        automation_authority.get("canonical_command_submit")
        != "POST /v2/automation/commands"
    ):
        fail("canonical automation command submit route drifted")
    if (
        automation_authority.get("canonical_command_read")
        != "GET /v2/automation/commands/{command_id}"
    ):
        fail("canonical automation command read route drifted")

    required_n8n_markers = (
        'router = APIRouter(tags=["n8n-control-plane"])',
        '@router.post("/v1/integrations/n8n/commands", deprecated=True)',
        (
            "@router.get("
            '"/v1/integrations/n8n/operations/{command_id}", deprecated=True)'
        ),
        'expected_client_id="n8n-automation"',
        'required_scope="middleware.request.forward"',
        'required_scope="middleware.status.read"',
        "authorize_tenant(claims, command.tenant_id)",
        "idempotency = required_header(",
        '"Idempotency-Key"',
        "if idempotency != command.idempotency_key",
        '"Deprecation": "true"',
        '"Sunset": _LEGACY_SUNSET',
        'rel="successor-version"',
    )
    missing = [marker for marker in required_n8n_markers if marker not in n8n_source]
    if missing:
        fail("legacy n8n compatibility route drifted: " + ", ".join(missing))
    # The v2 successor is mounted by the registry in every factory; nesting it
    # inside the deprecated, edge-denied aliases would mount it twice and tie
    # the canonical route set to the aliases' sunset.
    forbidden_n8n_markers = (
        "include_router(",
        "automation_v2",
    )
    nested = [marker for marker in forbidden_n8n_markers if marker in n8n_source]
    if nested:
        fail(
            "v2 automation router is nested in the legacy n8n aliases: "
            + ", ".join(nested)
        )
    required_input_markers = (
        "request.headers.getlist(name)",
        "if len(values) != 1",
        'request.headers.getlist("Authorization")',
        "if len(values) > 1",
    )
    missing_inputs = [
        marker for marker in required_input_markers if marker not in api_inputs_source
    ]
    if missing_inputs:
        fail("shared API input validation drifted: " + ", ".join(missing_inputs))
    # Route ownership (registry). 1. v2 is canonical; 3. the deprecated aliases
    # are exactly the monolith-only group; 5. each is bound once, by the
    # registry alone.
    registry_markers = (
        "from app.automation_v2 import v2_router as automation_v2_router",
        "from app.n8n_control_plane import router as n8n_control_plane_router",
        "LEGACY_MONOLITH_ONLY_ROUTERS = (n8n_control_plane_router,)",
        "def mount_canonical_routers(app: FastAPI) -> None:",
        "def mount_legacy_monolith_routers(app: FastAPI) -> None:",
        "    for router in CANONICAL_ROUTERS:\n        app.include_router(router)",
        (
            "    for router in LEGACY_MONOLITH_ONLY_ROUTERS:\n"
            "        app.include_router(router)"
        ),
    )
    missing_registry = [m for m in registry_markers if m not in registry_source]
    if missing_registry:
        fail("router registry drifted: " + ", ".join(missing_registry))
    canonical_tuple = registry_source.split("CANONICAL_ROUTERS = (", 1)[-1].split(
        ")", 1
    )[0]
    if canonical_tuple.count("automation_v2_router,") != 1:
        fail("automation v2 router must be bound exactly once in CANONICAL_ROUTERS")
    if "n8n_control_plane_router" in canonical_tuple:
        fail("legacy n8n compatibility router must not be canonical")
    if registry_source.count("automation_v2_router,") != 1:
        fail("automation v2 router is bound more than once by the registry")
    if registry_source.count("app.include_router(") != 2:
        fail("router registry mounts outside its two approved loops")
    # 2./5. Neither router is imported or mounted by any other application
    # module: the registry is the only owner, so v2 cannot be nested in the
    # aliases or mounted twice, and the aliases cannot reach another factory.
    foreign_owners: list[str] = []
    for module in sorted(APP_ROOT.rglob("*.py")):
        if module in {REGISTRY_PATH, N8N_PATH, APP_ROOT / "automation_v2.py"}:
            continue
        source = module.read_text(encoding="utf-8")
        if "n8n_control_plane" in source or "v2_router" in source:
            foreign_owners.append(module.relative_to(ROOT).as_posix())
    if foreign_owners:
        fail("n8n/v2 routers are owned outside the registry: " + ", ".join(foreign_owners))
    # app.main exposes the aliases only through the registry.
    for marker in ("mount_canonical_routers(app)", "mount_legacy_monolith_routers(app)"):
        if marker not in main_source:
            fail(f"monolith application does not call {marker}")
    if "include_router(n8n_control_plane_router)" in main_source:
        fail("legacy n8n compatibility router is mounted outside the registry")
    # 4. The deployed integration API never mounts the aliases.
    if "mount_canonical_routers(app)" not in deployed_source:
        fail("deployed entrypoint does not mount the canonical routers")
    for forbidden in ("mount_legacy_monolith_routers", "LEGACY_MONOLITH_ONLY_ROUTERS"):
        if forbidden in deployed_source:
            fail(f"deployed entrypoint mounts edge-denied n8n aliases: {forbidden}")
    # 6. Retired aliases stay denied at the deployed edge; the v2 successor is
    # the shared-edge route.
    edge_classes = {
        (row["method"], row["path"]): row["classification"]
        for row in edge_contract["routes"]
    }
    for method, path in (
        ("POST", "/v1/integrations/n8n/commands"),
        ("GET", "/v1/integrations/n8n/operations/{command_id}"),
    ):
        if edge_classes.get((method, path)) != "denied":
            fail(f"retired n8n alias is not denied at the edge: {method} {path}")
    for method, path in (
        ("POST", "/v2/automation/commands"),
        ("GET", "/v2/automation/commands/{command_id}"),
    ):
        if edge_classes.get((method, path)) != "shared_edge":
            fail(f"canonical automation route is not a shared edge route: {method} {path}")

    aliases = automation_authority.get("compatibility_aliases")
    if not isinstance(aliases, list) or len(aliases) != 2:
        fail("exactly two n8n v1 compatibility aliases must be declared")
    expected_aliases = {
        "POST /v1/integrations/n8n/commands",
        "GET /v1/integrations/n8n/operations/{command_id}",
    }
    observed_aliases = {
        item.get("route")
        for item in aliases
        if isinstance(item, dict) and item.get("status") == "deprecated"
    }
    if observed_aliases != expected_aliases:
        fail("n8n v1 compatibility alias declaration drifted")

    boundary = contract.get("middleware_to_odoo", {})
    expected_boundary = {
        "target": "odoo-19",
        "capability": "ODOO_WRITE",
        "bridge_module": "codestra_middleware_bridge",
        "canonical_command_type": "crm.lead.upsert",
        "canonical_command_version": "1.0",
        "canonical_command_path": ("/codestra/middleware/v1/commands/crm.lead.upsert"),
        "canonical_status_path": (
            "/codestra/middleware/v1/commands/{command_id}/status"
        ),
        "readback_required": True,
        "unknown_outcome_policy": "query_command_status_before_any_retry",
        "blind_resubmission_allowed": False,
    }
    for key, value in expected_boundary.items():
        if boundary.get(key) != value:
            fail(f"Odoo boundary field {key} drifted")
    expected_hmac_fields = [
        "X-Codestra-Timestamp",
        "X-Codestra-Event-ID",
        "HTTP_METHOD_UPPERCASE",
        "REQUEST_PATH",
        "X-Tenant-ID",
        "X-Correlation-ID",
        "Idempotency-Key",
        "RAW_REQUEST_BODY",
    ]
    if boundary.get("hmac_canonical_fields_in_order") != expected_hmac_fields:
        fail("Odoo HMAC canonical field order drifted")

    required_odoo_markers = (
        (
            'ODOO_LEAD_COMMAND_SCHEMA = ROOT / "contracts" / '
            '"odoo-lead-command.schema.json"'
        ),
        'UPSERT_LEAD = "crm.lead.upsert"',
        "SUPPORTED = {UPSERT_LEAD}",
        ('COMMAND_PATH = "/codestra/middleware/v1/commands/crm.lead.upsert"'),
        ('STATUS_PATH = "/codestra/middleware/v1/commands/{command_id}/status"'),
        'self.settings.external_effects.get("ODOO_WRITE") is not True',
        "len(value) > 255",
        "_odoo_lead_command_validator().iter_errors(document)",
        'request.tenant_id.encode("utf-8")',
        'request.correlation_id.encode("utf-8")',
        'idempotency_key.encode("utf-8")',
        "return await self._reconcile_unknown_write(request, exc)",
        "reconciliation = await self.readback(request)",
        'data.get("operation") != self.UPSERT_LEAD',
        "ODOO_INBOUND_HMAC_SECRET",
    )
    missing = [marker for marker in required_odoo_markers if marker not in odoo_source]
    if missing:
        fail("Odoo adapter implementation drifted: " + ", ".join(missing))
    for forbidden in (
        'CREATE_LEAD = "crm.lead.create.v1"',
        'UPDATE_LEAD = "crm.lead.update.v1"',
        'return "POST", "/codestra/middleware/v1/crm/leads"',
    ):
        if forbidden in odoo_source:
            fail(f"obsolete Odoo adapter contract remains: {forbidden}")
    if "OdooProviderAdapter(settings)" not in worker_source:
        fail("Temporal worker does not register Odoo adapter")
    if "retry_policy=RetryPolicy(maximum_attempts=1)" not in workflow_source:
        fail("command adapter execution may be retried after an unknown outcome")

    canonical = "\n".join(
        (
            vector["timestamp"],
            vector["event_id"],
            vector["method"],
            vector["path"],
            vector["tenant_id"],
            vector["correlation_id"],
            vector["idempotency_key"],
            vector["body_utf8"],
        )
    ).encode("utf-8")
    digest = hmac.new(
        vector["secret"].encode("utf-8"), canonical, hashlib.sha256
    ).hexdigest()
    if digest != vector.get("expected_hmac_sha256_hex"):
        fail("published Odoo HMAC test vector is invalid")
    if vector.get("secret") != "test-secret-not-production":
        fail("HMAC vector must remain synthetic")
    document = json.loads(vector["body_utf8"])
    if vector.get("event_id") != document.get("command_id"):
        fail("HMAC vector event ID does not match command ID")

    if capabilities.get("ODOO_WRITE") is not False:
        fail("ODOO_WRITE must remain false in the source capability registry")
    for flag in ("EMAIL_DELIVERY", "SMS_DELIVERY", "PRODUCTION_DIALING"):
        if capabilities.get(flag) is not False:
            fail(f"{flag} unexpectedly enabled")

    serialized = (
        CONTRACT_PATH.read_text(encoding="utf-8")
        + HMAC_VECTOR_PATH.read_text(encoding="utf-8")
    ).lower()
    for forbidden in (
        "client_secret",
        "password",
        "access_token",
        "private_key",
    ):
        if forbidden in serialized:
            fail(
                f"shared contract contains forbidden secret-bearing field: {forbidden}"
            )

    print("PLATFORM_CONTROL_PLANE=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
