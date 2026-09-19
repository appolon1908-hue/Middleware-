from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import webhook_api
from app.entrypoints import integration_api


def test_exact_odoo_event_dispatches_to_durable_webhook_intake(monkeypatch) -> None:
    verified: list[tuple[str, str, str]] = []
    accepted: list[tuple[object, str, bytes, dict[str, str]]] = []

    class Tokens:
        async def verify(
            self,
            authorization: str,
            *,
            expected_client_id: str,
            required_scope: str,
        ) -> dict[str, str]:
            verified.append(
                (authorization, expected_client_id, required_scope)
            )
            return {"sub": "odoo-integration"}

    async def fake_accept(
        runtime,
        route,
        *,
        claims,
        method: str,
        path: str,
        raw_body: bytes,
        headers: dict[str, str],
    ):
        accepted.append((route, path, raw_body, headers))
        assert runtime.tokens.__class__ is Tokens
        assert claims == {"sub": "odoo-integration"}
        assert method == "POST"
        return (
            SimpleNamespace(
                correlation_id="correlation-test-syn",
                model_dump=lambda **_kwargs: {
                    "status": "accepted",
                    "correlation_id": "correlation-test-syn",
                },
            ),
            202,
        )

    monkeypatch.setattr(webhook_api, "accept_webhook", fake_accept)
    app = FastAPI()
    app.state.runtime = SimpleNamespace(
        tokens=Tokens(),
        settings=SimpleNamespace(max_request_body_bytes=1024),
    )
    app.include_router(webhook_api.odoo_event_router)

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/odoo/events",
            content=b'{"event_id":"TEST_SYN_EVENT_001"}',
            headers={"Authorization": "Bearer synthetic"},
        )

    assert response.status_code == 202
    assert response.json()["status"] == "accepted"
    assert response.headers["X-Correlation-ID"] == "correlation-test-syn"
    assert verified == [
        (
            "Bearer synthetic",
            "odoo-integration",
            "odoo.events.publish",
        )
    ]
    assert len(accepted) == 1
    route, path, raw_body, headers = accepted[0]
    assert route.path == "/api/v1/odoo/events"
    assert path == "/api/v1/odoo/events"
    assert raw_body == b'{"event_id":"TEST_SYN_EVENT_001"}'
    assert headers["authorization"] == "Bearer synthetic"
    assert headers["content-length"] == str(len(raw_body))


@pytest.mark.asyncio
async def test_integration_entrypoint_owns_canonical_runtime_lifecycle(
    monkeypatch,
) -> None:
    configured = object()

    class Runtime:
        closed = False

        async def close(self) -> None:
            self.closed = True

    runtime = Runtime()

    def fake_settings_from_env():
        return configured

    async def fake_build_runtime(settings):
        assert settings is configured
        return runtime

    monkeypatch.setattr(
        integration_api.DomainSettings,
        "from_env",
        fake_settings_from_env,
    )
    monkeypatch.setattr(
        integration_api,
        "build_domain_runtime",
        fake_build_runtime,
    )

    async with integration_api.app.router.lifespan_context(
        integration_api.app
    ):
        assert integration_api.app.state.runtime is runtime
        assert runtime.closed is False

    assert runtime.closed is True
