"""Contacts/opportunities/tickets routers: auth, tenant scoping, and error
mapping against a fake ``OdooCrmBridgeClient`` -- no real Odoo or database
involved, since these routers hold no state of their own and are pure
passthrough over ``app.adapters.odoo.crm_bridge_client``.
"""

from __future__ import annotations

import time
from types import SimpleNamespace
from uuid import uuid4

import jwt
import pytest
import pytest_asyncio
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

from app.adapters.odoo.crm_bridge_client import (
    BridgeResponse,
    CrmBridgeNotConfigured,
    CrmBridgeNotFound,
    CrmBridgeUnavailable,
    get_crm_bridge_client,
)
from app.adapters.odoo import crm_bridge_client as crm_bridge_module
from app.api.v1 import contacts as contacts_module
from app.api.v1 import opportunities as opportunities_module
from app.api.v1 import tickets as tickets_module
from app.core.config import settings

ISSUER = "https://identity.example.invalid/realms/crm-bridge-test"
AUDIENCE = "middleware-api-test"


class FakeBridgeClient:
    def __init__(self):
        self.calls: list[tuple] = []
        self.raise_error: Exception | None = None
        self.next_response = BridgeResponse(status_code=200, body={"ok": True})

    async def _record(self, name, *args, **kwargs):
        self.calls.append((name, args, kwargs))
        if self.raise_error:
            raise self.raise_error
        return self.next_response

    def __getattr__(self, name):
        async def method(*args, **kwargs):
            return await self._record(name, *args, **kwargs)
        return method


@pytest.fixture
def authority(monkeypatch):
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    class Keys:
        def __init__(self, *_args, **_kwargs):
            pass

        def get_signing_key_from_jwt(self, _token):
            return SimpleNamespace(key=private.public_key())

    monkeypatch.setattr(jwt, "PyJWKClient", Keys)
    for key, value in {
        "keycloak_issuer": ISSUER,
        "keycloak_audience": AUDIENCE,
        "keycloak_jwks_url": ISSUER + "/certs",
        "agent_provisioning_authorized_parties": "provisioning-service",
    }.items():
        monkeypatch.setattr(settings, key, value)

    def token(
        scope="identity.request integration.configure tenant.provision",
        subject="provisioning-service-subject",
        azp="provisioning-service",
        tenant_ids=("COD",),
        **overrides,
    ):
        current = int(time.time())
        claims = {
            "iss": ISSUER, "aud": AUDIENCE, "azp": azp,
            "sub": subject, "iat": current, "exp": current + 300,
            "jti": str(uuid4()), "scope": scope, "tenant_ids": list(tenant_ids),
            **overrides,
        }
        return jwt.encode(claims, private, algorithm="RS256")

    return token


@pytest_asyncio.fixture
async def bridge_client():
    return FakeBridgeClient()


@pytest_asyncio.fixture
async def client(bridge_client):
    app = FastAPI()
    app.include_router(contacts_module.router)
    app.include_router(opportunities_module.router)
    app.include_router(tickets_module.router)
    app.dependency_overrides[get_crm_bridge_client] = lambda: bridge_client

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as http_client:
        yield http_client

    app.dependency_overrides.clear()


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_crm_bridge_dependency_uses_active_runtime_settings(monkeypatch):
    configured = object()
    created_with = []

    class FakeClient:
        def __init__(self, value):
            created_with.append(value)

    monkeypatch.setattr(crm_bridge_module, "OdooCrmBridgeClient", FakeClient)
    app = FastAPI()
    app.state.runtime = SimpleNamespace(settings=configured)

    @app.get("/dependency-check")
    async def dependency_check(client=Depends(get_crm_bridge_client)):
        return {"created": client is not None}

    with TestClient(app) as test_client:
        assert test_client.get("/dependency-check").json() == {"created": True}
    assert created_with == [configured]


@pytest.mark.asyncio
async def test_list_contacts_requires_auth(client):
    response = await client.get("/platform/v1/contacts", params={"tenant_id": "COD"})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_list_contacts_rejects_tenant_mismatch(client, authority):
    response = await client.get(
        "/platform/v1/contacts",
        params={"tenant_id": "OTHER"},
        headers=_headers(authority(tenant_ids=("COD",))),
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_bridge_tenant_binding_fails_closed(client, authority, bridge_client):
    bridge_client.configured_tenant_id = "OTHER"
    response = await client.get(
        "/platform/v1/contacts",
        params={"tenant_id": "COD"},
        headers=_headers(authority(tenant_ids=("COD",))),
    )
    assert response.status_code == 503


@pytest.mark.asyncio
async def test_list_contacts_forwards_bridge_response(client, authority, bridge_client):
    bridge_client.next_response = BridgeResponse(200, {"items": [{"profile_id": 1}]})
    response = await client.get(
        "/platform/v1/contacts",
        params={"tenant_id": "COD"},
        headers=_headers(authority(tenant_ids=("COD",))),
    )
    assert response.status_code == 200
    assert response.json() == {"items": [{"profile_id": 1}]}
    assert bridge_client.calls[0][0] == "list_contacts"


@pytest.mark.asyncio
async def test_create_contact_passes_payload_and_idempotency(client, authority, bridge_client):
    bridge_client.next_response = BridgeResponse(201, {"profile_id": 5})
    response = await client.post(
        "/platform/v1/contacts",
        params={"tenant_id": "COD"},
        headers={**_headers(authority(tenant_ids=("COD",))), "Idempotency-Key": "abc-123"},
        json={"name": "Jane Doe", "partner_id": 1, "campaign_id": 2, "integration_key": "k"},
    )
    assert response.status_code == 201
    name, args, kwargs = bridge_client.calls[0]
    assert name == "create_contact"
    assert args[0] == {"name": "Jane Doe", "partner_id": 1, "campaign_id": 2, "integration_key": "k"}
    assert kwargs["idempotency_key"] == "abc-123"


@pytest.mark.asyncio
async def test_get_contact_not_found_maps_to_404(client, authority, bridge_client):
    bridge_client.raise_error = CrmBridgeNotFound("/customer-profiles/9")
    response = await client.get(
        "/platform/v1/contacts/9",
        params={"tenant_id": "COD"},
        headers=_headers(authority(tenant_ids=("COD",))),
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_bridge_unavailable_maps_to_502(client, authority, bridge_client):
    bridge_client.raise_error = CrmBridgeUnavailable("connection refused")
    response = await client.get(
        "/platform/v1/opportunities/ext-1",
        params={"tenant_id": "COD"},
        headers=_headers(authority(tenant_ids=("COD",))),
    )
    assert response.status_code == 502


@pytest.mark.asyncio
async def test_bridge_not_configured_maps_to_503(client, authority, bridge_client):
    bridge_client.raise_error = CrmBridgeNotConfigured("odoo_crm_bridge_base_url must be set")
    response = await client.get(
        "/platform/v1/tickets",
        params={"tenant_id": "COD"},
        headers=_headers(authority(tenant_ids=("COD",))),
    )
    assert response.status_code == 503


@pytest.mark.asyncio
async def test_complete_task_forwards(client, authority, bridge_client):
    bridge_client.next_response = BridgeResponse(200, {"task_id": 3, "status": "completed"})
    response = await client.post(
        "/platform/v1/tasks/3/complete",
        params={"tenant_id": "COD"},
        headers=_headers(authority(tenant_ids=("COD",))),
    )
    assert response.status_code == 200
    assert response.json()["status"] == "completed"
    assert bridge_client.calls[0][0] == "complete_task"


@pytest.mark.asyncio
async def test_update_ticket_forwards_payload(client, authority, bridge_client):
    bridge_client.next_response = BridgeResponse(200, {"ticket_id": 7, "resolution": "fixed"})
    response = await client.patch(
        "/platform/v1/tickets/7",
        params={"tenant_id": "COD"},
        headers=_headers(authority(tenant_ids=("COD",))),
        json={"resolution": "fixed"},
    )
    assert response.status_code == 200
    name, args, kwargs = bridge_client.calls[0]
    assert name == "update_ticket"
    assert args[0] == 7
    assert args[1] == {"resolution": "fixed"}
