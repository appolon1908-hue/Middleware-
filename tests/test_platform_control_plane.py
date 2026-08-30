from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.commands import CommandPolicy, CommandPolicyRegistry, CommandService, MemoryCommandStore
from app.main import create_app
from app.odoo_provider_adapter import OdooProviderAdapter, OdooProviderAdapterError
from app.replay import MemoryReplayGuard
from app.runtime import Runtime
from app.storage import MemoryInboxStore
from app.temporal_workflows import CommandExecutionRequest


class N8nTokenVerifier:
    async def verify(
        self,
        authorization: str,
        *,
        expected_client_id: str,
        required_scope: str,
    ) -> dict[str, Any]:
        assert expected_client_id == "n8n-automation"
        if authorization != f"Bearer {required_scope}":
            from app.security import AuthenticationError

            raise AuthenticationError("invalid n8n token")
        return {
            "azp": "n8n-automation",
            "scope": required_scope,
            "aud": "middleware-api",
            "tenant_id": "tenant-1",
            "sub": "n8n-service-subject",
        }

    async def ready(self) -> bool:
        return True


def _policy() -> CommandPolicyRegistry:
    return CommandPolicyRegistry(
        (
            CommandPolicy(
                prefix="crm.",
                target="odoo-19",
                capability="ODOO_WRITE",
                readback_required=True,
            ),
        ),
        {"ODOO_WRITE": True},
    )


def _body() -> dict[str, Any]:
    return {
        "command_id": str(uuid4()),
        "command_type": "crm.lead.create.v1",
        "command_version": "1.0",
        "target": "odoo-19",
        "tenant_id": "tenant-1",
        "requested_by": "n8n-service-subject",
        "correlation_id": "corr-platform-control-plane",
        "idempotency_key": "idem-platform-control-plane",
        "capability": "ODOO_WRITE",
        "payload": {
            "name": "CODESTRA-INTEGRATION-TEST-Lead",
            "external_id": "lead-platform-control-plane",
            "middleware_id": "mw-platform-control-plane",
        },
    }


def test_n8n_control_plane_submit_and_status_are_tenant_scoped(test_settings) -> None:
    runtime = Runtime(
        settings=test_settings,
        inbox=MemoryInboxStore(),
        replay=MemoryReplayGuard(),
        tokens=N8nTokenVerifier(),
        commands=CommandService(MemoryCommandStore(), _policy()),
    )
    body = _body()
    app = create_app(settings=test_settings, runtime=runtime)
    with TestClient(app) as client:
        submitted = client.post(
            "/v1/integrations/n8n/commands",
            json=body,
            headers={
                "Authorization": "Bearer middleware.request.forward",
                "X-Tenant-ID": body["tenant_id"],
                "X-Correlation-ID": body["correlation_id"],
                "Idempotency-Key": body["idempotency_key"],
            },
        )
        assert submitted.status_code == 202, submitted.text
        assert submitted.headers["location"] == (
            f"/v1/integrations/n8n/operations/{body['command_id']}"
        )
        status = client.get(
            f"/v1/integrations/n8n/operations/{body['command_id']}",
            headers={
                "Authorization": "Bearer middleware.status.read",
                "X-Tenant-ID": "tenant-1",
            },
        )
        assert status.status_code == 200, status.text
        assert status.json()["state"] == "persisted"


def _request(command_type: str = "crm.lead.create.v1") -> CommandExecutionRequest:
    return CommandExecutionRequest(
        command_id="00000000-0000-4000-8000-000000000001",
        command_type=command_type,
        command_version="1.0",
        target="odoo-19",
        tenant_id="tenant-1",
        requested_by="n8n-service-subject",
        correlation_id="corr-platform-control-plane",
        idempotency_key="idem-platform-control-plane",
        capability="ODOO_WRITE",
        payload={
            "name": "CODESTRA-INTEGRATION-TEST-Lead",
            "external_id": "lead-platform-control-plane",
            "middleware_id": "mw-platform-control-plane",
        },
    )


def test_odoo_adapter_fails_closed_when_write_capability_is_off() -> None:
    settings = SimpleNamespace(app_env="test", external_effects={"ODOO_WRITE": False})
    adapter = OdooProviderAdapter(settings, {})
    with pytest.raises(OdooProviderAdapterError, match="ODOO_WRITE is disabled"):
        adapter._require_active(_request())


def test_odoo_adapter_maps_only_reviewed_crm_commands() -> None:
    settings = SimpleNamespace(app_env="test", external_effects={"ODOO_WRITE": True})
    adapter = OdooProviderAdapter(
        settings,
        {
            "ODOO_INTEGRATION_BASE_URL": "http://odoo.test",
            "ODOO_INBOUND_HMAC_SECRET": "test-secret",
        },
    )
    method, path, payload = adapter._write_request(_request())
    assert method == "POST"
    assert path == "/codestra/middleware/v1/crm/leads"
    assert payload["external_id"] == "lead-platform-control-plane"

    with pytest.raises(OdooProviderAdapterError, match="unsupported Odoo command type"):
        adapter._require_active(_request("crm.contact.create.v1"))
