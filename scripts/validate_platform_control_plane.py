#!/usr/bin/env python3
"""Validate repository-owned pieces of the platform control-plane v1 contract."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "contracts" / "platform-control-plane.v1.json"
MAIN_PATH = ROOT / "app" / "main.py"
N8N_PATH = ROOT / "app" / "n8n_control_plane.py"
ODOO_PATH = ROOT / "app" / "odoo_provider_adapter.py"
WORKER_PATH = ROOT / "workers" / "run_temporal.py"
CAPABILITIES_PATH = ROOT / "config" / "capabilities.v2.json"


def fail(message: str) -> None:
    raise SystemExit(f"PLATFORM_CONTROL_PLANE=FAIL {message}")


def main() -> int:
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    capabilities = json.loads(CAPABILITIES_PATH.read_text(encoding="utf-8"))["capabilities"]
    main_source = MAIN_PATH.read_text(encoding="utf-8")
    n8n_source = N8N_PATH.read_text(encoding="utf-8")
    odoo_source = ODOO_PATH.read_text(encoding="utf-8")
    worker_source = WORKER_PATH.read_text(encoding="utf-8")

    if contract.get("status") != "PREPARED_DISABLED":
        fail("source integration must remain PREPARED_DISABLED")
    repositories = contract.get("repositories", {})
    if repositories.get("write_authority") != "appolon1908-hue/Middleware-":
        fail("Middleware repository is not declared write authority")

    edge = contract.get("n8n_to_middleware", {})
    if edge.get("client_id") != "n8n-automation":
        fail("n8n client identity drifted")
    if edge.get("audience") != "middleware-api":
        fail("middleware audience drifted")
    if edge.get("submit_scope") != "middleware.request.forward":
        fail("n8n submit scope drifted")
    if edge.get("read_scope") != "middleware.status.read":
        fail("n8n read scope drifted")
    if edge.get("direct_provider_access") is not False:
        fail("n8n direct-provider access must remain false")

    required_n8n_markers = (
        'router = APIRouter(prefix="/v1/integrations/n8n"',
        '@router.post("/commands")',
        '@router.get("/operations/{command_id}")',
        'expected_client_id="n8n-automation"',
        'required_scope="middleware.request.forward"',
        'required_scope="middleware.status.read"',
        'authorize_tenant(claims, command.tenant_id)',
        'request.headers.get("Idempotency-Key") != command.idempotency_key',
    )
    missing = [marker for marker in required_n8n_markers if marker not in n8n_source]
    if missing:
        fail("n8n control-plane implementation drifted: " + ", ".join(missing))
    if "app.include_router(n8n_control_plane_router)" not in main_source:
        fail("n8n control-plane router is not mounted")

    boundary = contract.get("middleware_to_odoo", {})
    if boundary.get("target") != "odoo-19" or boundary.get("capability") != "ODOO_WRITE":
        fail("Odoo command ownership drifted")
    if boundary.get("readback_required") is not True:
        fail("Odoo read-back must remain mandatory")
    required_odoo_markers = (
        'CREATE_LEAD = "crm.lead.create.v1"',
        'UPDATE_LEAD = "crm.lead.update.v1"',
        'self.settings.external_effects.get("ODOO_WRITE") is not True',
        '"/codestra/middleware/v1/crm/leads"',
        '"/codestra/middleware/v1/crm/leads/{quote(external_id, safe=\'\')}"',
        'return ActivityResult(\n            status="matched"',
        'ODOO_INBOUND_HMAC_SECRET',
    )
    missing = [marker for marker in required_odoo_markers if marker not in odoo_source]
    if missing:
        fail("Odoo adapter implementation drifted: " + ", ".join(missing))
    if "OdooProviderAdapter(settings)" not in worker_source:
        fail("Temporal worker does not register Odoo adapter")

    if capabilities.get("ODOO_WRITE") is not False:
        fail("ODOO_WRITE must remain false in the source capability registry")
    for flag in ("EMAIL_DELIVERY", "SMS_DELIVERY", "PRODUCTION_DIALING"):
        if capabilities.get(flag) is not False:
            fail(f"{flag} unexpectedly enabled")

    serialized = CONTRACT_PATH.read_text(encoding="utf-8").lower()
    for forbidden in ("client_secret", "password", "access_token", "private_key"):
        if forbidden in serialized:
            fail(f"shared contract contains forbidden secret-bearing field: {forbidden}")

    print("PLATFORM_CONTROL_PLANE=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
