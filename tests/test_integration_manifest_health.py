import asyncio

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.entrypoints import integration_api, runtime


@pytest.mark.parametrize("dependency", ["postgres", "redis", "keycloak"])
@pytest.mark.parametrize("state", ["unavailable", "not_configured"])
@pytest.mark.parametrize("path", ["/health/ready", "/ready", "/readyz"])
def test_each_required_dependency_blocks_readiness(monkeypatch, dependency, state, path):
    states = {"postgres": "online", "redis": "online", "keycloak": "online", dependency: state}
    async def probe():
        return states
    monkeypatch.setattr(runtime, "integration_dependency_states", probe)
    monkeypatch.setattr(settings, "health_require_database", False)
    client = TestClient(integration_api.app)
    response = client.get(path)
    assert response.status_code == 503
    assert response.json()["dependencies"][dependency] == state
    assert client.get("/health/live").status_code == 200
    assert client.get("/health/dependencies").json()[dependency if dependency != "postgres" else "database"] == state


def test_all_required_dependencies_online(monkeypatch):
    async def probe():
        return {"postgres": "online", "redis": "online", "keycloak": "online"}
    monkeypatch.setattr(runtime, "integration_dependency_states", probe)
    assert TestClient(integration_api.app).get("/health/ready").status_code == 200


def test_probes_reject_missing_keycloak_and_unavailable_database_and_redis(monkeypatch):
    class Unavailable:
        def connect(self):
            raise RuntimeError("SECRET_MUST_NOT_BE_EXPOSED")
    monkeypatch.setattr(runtime, "engine", Unavailable())
    monkeypatch.setattr(settings, "redis_url", "")
    monkeypatch.setattr(settings, "keycloak_issuer", "")
    states = asyncio.run(runtime.integration_dependency_states())
    assert states == {"postgres": "unavailable", "redis": "not_configured", "keycloak": "not_configured"}

@pytest.mark.parametrize("failed", [None, "postgres", "redis", "keycloak"])
def test_actual_probe_logic_checks_all_dependency_clients(monkeypatch, failed):
    import json
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    import jwt
    from cryptography.hazmat.primitives.asymmetric import rsa

    database_context = AsyncMock()
    database_connection = AsyncMock()
    database_context.__aenter__.return_value = database_connection
    if failed == "postgres":
        database_connection.execute.side_effect = RuntimeError("private database detail")
    monkeypatch.setattr(runtime, "engine", SimpleNamespace(connect=lambda: database_context))
    redis_context = AsyncMock()
    redis_context.__aenter__.return_value = redis_context
    redis_context.ping.return_value = failed != "redis"
    monkeypatch.setattr(runtime, "Redis", SimpleNamespace(from_url=lambda *_args, **_kwargs: redis_context))
    monkeypatch.setattr(settings, "redis_url", "redis://127.0.0.1:6379/15")
    for name, value in {
        "keycloak_issuer": "https://identity.example.invalid/realm",
        "keycloak_audience": "test-audience", "keycloak_authorized_parties": "test-client",
        "keycloak_jwks_url": "https://identity.example.invalid/certs",
    }.items():
        monkeypatch.setattr(settings, name, value)
    public = rsa.generate_private_key(public_exponent=65537, key_size=2048).public_key()
    jwks = {"keys": [json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(public))]}
    response = SimpleNamespace(json=lambda: jwks, raise_for_status=lambda: None)
    http = AsyncMock()
    http.__aenter__.return_value = http
    http.get.return_value = response
    if failed == "keycloak":
        http.get.side_effect = RuntimeError("private signing endpoint detail")
    monkeypatch.setattr(runtime.httpx, "AsyncClient", lambda **_kwargs: http)
    states = asyncio.run(runtime.integration_dependency_states())
    assert states == {name: "unavailable" if name == failed else "online" for name in ("postgres", "redis", "keycloak")}
    database_connection.execute.assert_awaited_once()
    redis_context.ping.assert_awaited_once()
    redis_context.__aexit__.assert_awaited_once()
    http.get.assert_awaited_once()
