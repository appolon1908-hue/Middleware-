"""Real-database regressions for GET /platform/v1/tenants/* and
/platform/v1/campaigns/*.

Same convention as tests/test_calls_and_activity.py and
tests/test_presence_and_queues.py: skipped unless a disposable PostgreSQL is
available. Reuses tests/test_presence_and_queues.py's `_seed_queue` helper
to create a real, constraint-valid campaign_registry row rather than
re-deriving the retry-safe extension-allocation seeding logic it already
solved.

Tenant-resolution tests stub FoundationClient at the module level rather
than requiring a live codestra-foundation instance in CI - these tests are
proving tenants.py's own routing/aggregation logic, not re-testing
FoundationClient's HTTP behavior (which is that adapter's own concern).
"""

from __future__ import annotations

import os
import time
from types import SimpleNamespace
from uuid import uuid4

import jwt
import pytest
import pytest_asyncio
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.adapters.foundation.client import FoundationTenantNotFound
from app.api.v1 import campaigns as campaigns_module
from app.api.v1 import tenants as tenants_module
from app.core.config import settings
from tests.test_presence_and_queues import _seed_queue

ISSUER = "https://identity.example.invalid/realms/tenants-campaigns-test"
AUDIENCE = "middleware-api-test"

pytestmark = pytest.mark.skipif(
    "DATABASE_URL" not in os.environ, reason="disposable PostgreSQL required"
)


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
        "agent_provisioning_policy_revision": "7",
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


class _StubFoundation:
    """Replaces FoundationClient.get_tenant with an in-memory answer.

    Resolves any tenant_id EXCEPT "ZZZ" (reserved by
    test_get_tenant_unknown_in_foundation_is_404) - campaign_registry's
    campaign_code has a hard, permanent unique constraint shared across this
    whole test session, so each test seeds its own randomly-generated code
    via _seed_queue rather than reusing a fixed literal.
    """

    async def get_tenant(self, http, tenant_id):
        if tenant_id == "ZZZ":
            raise FoundationTenantNotFound(tenant_id)
        return SimpleNamespace(id=tenant_id, slug=tenant_id.lower(), name="Codestra", status="ACTIVE")


@pytest_asyncio.fixture
async def client(monkeypatch):
    monkeypatch.setattr(tenants_module, "FoundationClient", lambda settings: _StubFoundation())

    engine = create_async_engine(os.environ["DATABASE_URL"], poolclass=NullPool)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def isolated_session():
        async with session_factory() as session:
            yield session

    app = FastAPI()
    app.include_router(tenants_module.router)
    app.include_router(campaigns_module.router)
    app.dependency_overrides[tenants_module.get_session] = isolated_session
    app.dependency_overrides[campaigns_module.get_session] = isolated_session

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as http_client:
        yield http_client

    app.dependency_overrides.clear()
    await engine.dispose()


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_list_tenants_requires_bearer_token(client):
    response = await client.get("/platform/v1/tenants")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_tenant_wrong_tenant_claim_is_denied(client, authority):
    token = authority(tenant_ids=("OTHER",))
    response = await client.get("/platform/v1/tenants/COD", headers=_headers(token))
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_get_tenant_reflects_foundation_record(client, authority):
    response = await client.get("/platform/v1/tenants/COD", headers=_headers(authority()))
    assert response.status_code == 200
    assert response.json()["name"] == "Codestra"


@pytest.mark.asyncio
async def test_get_tenant_unknown_in_foundation_is_404(client, authority):
    token = authority(tenant_ids=("ZZZ",))
    response = await client.get("/platform/v1/tenants/ZZZ", headers=_headers(token))
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_tenant_campaigns_reflects_seeded_registry_row(client, authority):
    session_factory = async_sessionmaker(
        create_async_engine(os.environ["DATABASE_URL"], poolclass=NullPool),
        expire_on_commit=False,
    )
    vicidial_campaign_id, campaign_code = await _seed_queue(session_factory)

    response = await client.get(
        f"/platform/v1/tenants/{campaign_code}/campaigns",
        headers=_headers(authority(tenant_ids=(campaign_code,))),
    )
    assert response.status_code == 200
    ids = {item["campaign_id"] for item in response.json()["items"]}
    assert vicidial_campaign_id in ids


@pytest.mark.asyncio
async def test_get_campaign_requires_bearer_token(client):
    response = await client.get("/platform/v1/campaigns/6101?tenant_id=COD")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_campaign_wrong_tenant_is_404_not_leaked(client, authority):
    session_factory = async_sessionmaker(
        create_async_engine(os.environ["DATABASE_URL"], poolclass=NullPool),
        expire_on_commit=False,
    )
    vicidial_campaign_id, campaign_code = await _seed_queue(session_factory)

    other_token = authority(tenant_ids=("OTHER_TENANT",))
    response = await client.get(
        f"/platform/v1/campaigns/{vicidial_campaign_id}?tenant_id=OTHER_TENANT",
        headers=_headers(other_token),
    )
    # The token's own tenant claim matches its query param (so
    # require_tenant_match passes), but the campaign actually belongs to a
    # different tenant - fail-closed 404, not a 403, matching calls.py's
    # established test_get_call_by_id_wrong_tenant_is_404_not_leaked.
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_campaign_reflects_seeded_registry_row(client, authority):
    session_factory = async_sessionmaker(
        create_async_engine(os.environ["DATABASE_URL"], poolclass=NullPool),
        expire_on_commit=False,
    )
    vicidial_campaign_id, campaign_code = await _seed_queue(session_factory)

    response = await client.get(
        f"/platform/v1/campaigns/{vicidial_campaign_id}?tenant_id={campaign_code}",
        headers=_headers(authority(tenant_ids=(campaign_code,))),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["campaign_id"] == vicidial_campaign_id
    assert body["campaign_code"] == campaign_code


@pytest.mark.asyncio
async def test_campaign_channels_reports_zero_when_no_requests_reference_it(client, authority):
    session_factory = async_sessionmaker(
        create_async_engine(os.environ["DATABASE_URL"], poolclass=NullPool),
        expire_on_commit=False,
    )
    vicidial_campaign_id, campaign_code = await _seed_queue(session_factory)

    response = await client.get(
        f"/platform/v1/campaigns/{vicidial_campaign_id}/channels?tenant_id={campaign_code}",
        headers=_headers(authority(tenant_ids=(campaign_code,))),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["provisioning_requests_referencing_campaign"] == 0
    assert body["desired_channel_counts"] == {}
