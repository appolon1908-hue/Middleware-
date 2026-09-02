from __future__ import annotations

import asyncio
import json
from typing import Any
from uuid import uuid4

from fastapi.testclient import TestClient

from app.commands import CommandPolicyRegistry, CommandService, MemoryCommandStore
from app.main import create_app
from app.provider_control_api import PROVIDER_CONTROL_SPECS
from app.replay import MemoryReplayGuard
from app.runtime import Runtime
from app.security import AuthenticationError
from app.storage import MemoryInboxStore


class ProviderControlTokenVerifier:
    async def verify(
        self,
        authorization: str,
        *,
        expected_client_id: str,
        required_scope: str,
    ) -> dict[str, Any]:
        expected = f"Bearer {expected_client_id}:{required_scope}"
        if authorization != expected:
            raise AuthenticationError("invalid provider-control token")
        return {
            "azp": expected_client_id,
            "aud": "middleware-api",
            "scope": required_scope,
            "tenant_id": "tenant-1",
            "sub": expected_client_id,
            "iat": 1_788_000_000,
            "exp": 1_788_000_300,
        }

    async def ready(self) -> bool:
        return True


def _runtime(test_settings, *, capabilities_enabled: bool) -> Runtime:
    loaded = CommandPolicyRegistry.load()
    capabilities = {
        name: capabilities_enabled for name in loaded.capabilities
    }
    commands = CommandService(
        MemoryCommandStore(),
        CommandPolicyRegistry(loaded.policies, capabilities),
    )
    return Runtime(
        settings=test_settings,
        inbox=MemoryInboxStore(),
        replay=MemoryReplayGuard(),
        tokens=ProviderControlTokenVerifier(),
        commands=commands,
    )


def _headers(spec, *, idempotency_key: str = "provider-control-idempotency"):
    return {
        "Authorization": (
            f"Bearer {spec.caller_client_id}:{spec.required_scope}"
        ),
        "X-Tenant-ID": "tenant-1",
        "X-Correlation-ID": "provider-control-correlation",
        "Idempotency-Key": idempotency_key,
    }


def test_provider_policy_external_routes_are_registered_exactly(test_settings) -> None:
    app = create_app(
        settings=test_settings,
        runtime=_runtime(test_settings, capabilities_enabled=False),
    )
    policy = json.loads(
        open("config/provider-operation-policy.json", encoding="utf-8").read()
    )
    expected = {
        operation["route"]
        for operation in policy["operations"]
        if operation["externalEffect"] is True
    }
    assert expected == {spec.route for spec in PROVIDER_CONTROL_SPECS}
    assert expected <= set(app.openapi()["paths"])
    for route in expected:
        responses = app.openapi()["paths"][route]["post"]["responses"]
        assert {"200", "202"} <= set(responses)


def test_exact_provider_control_routes_reuse_the_durable_operation_engine(
    test_settings,
) -> None:
    runtime = _runtime(test_settings, capabilities_enabled=True)
    app = create_app(settings=test_settings, runtime=runtime)

    with TestClient(app) as client:
        for index, spec in enumerate(PROVIDER_CONTROL_SPECS, start=1):
            operation_id = uuid4()
            headers = _headers(
                spec,
                idempotency_key=f"provider-control-idempotency-{index}",
            )
            body = {
                "operation_id": str(operation_id),
                "payload": {"resource_reference": f"reference-{index}"},
            }
            first = client.post(spec.route, headers=headers, json=body)
            assert first.status_code == 202, first.text
            assert first.headers["location"] == f"/v1/operations/{operation_id}"
            assert first.json()["control_operation"] == spec.operation_id
            assert first.json()["external_effect_dispatched"] is False

            stored = asyncio.run(
                runtime.commands.get("tenant-1", operation_id)  # type: ignore[union-attr]
            )
            assert stored.command_type == spec.command_type
            assert stored.target == spec.target
            assert stored.capability == spec.capability
            assert stored.requested_by == spec.caller_client_id

            replay = client.post(spec.route, headers=headers, json=body)
            assert replay.status_code == 200, replay.text
            assert replay.json()["duplicate"] is True

            changed = client.post(
                spec.route,
                headers=headers,
                json={
                    **body,
                    "payload": {"resource_reference": "changed"},
                },
            )
            assert changed.status_code == 409, changed.text


def test_provider_control_routes_require_exact_caller_scope_and_tenant(
    test_settings,
) -> None:
    spec = PROVIDER_CONTROL_SPECS[0]
    app = create_app(
        settings=test_settings,
        runtime=_runtime(test_settings, capabilities_enabled=True),
    )
    body = {"operation_id": str(uuid4()), "payload": {"reference": "safe"}}

    with TestClient(app) as client:
        wrong_scope = {
            **_headers(spec),
            "Authorization": f"Bearer {spec.caller_client_id}:wrong.scope",
        }
        assert client.post(spec.route, headers=wrong_scope, json=body).status_code == 401

        wrong_tenant = {**_headers(spec), "X-Tenant-ID": "tenant-2"}
        assert client.post(spec.route, headers=wrong_tenant, json=body).status_code == 403


def test_provider_control_routes_fail_closed_when_capability_is_disabled(
    test_settings,
) -> None:
    spec = PROVIDER_CONTROL_SPECS[0]
    app = create_app(
        settings=test_settings,
        runtime=_runtime(test_settings, capabilities_enabled=False),
    )
    with TestClient(app) as client:
        response = client.post(
            spec.route,
            headers=_headers(spec),
            json={"operation_id": str(uuid4()), "payload": {"reference": "safe"}},
        )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "capability_disabled"


def test_provider_control_payload_cannot_carry_provider_credentials(
    test_settings,
) -> None:
    spec = PROVIDER_CONTROL_SPECS[0]
    app = create_app(
        settings=test_settings,
        runtime=_runtime(test_settings, capabilities_enabled=True),
    )
    with TestClient(app) as client:
        response = client.post(
            spec.route,
            headers=_headers(spec),
            json={
                "operation_id": str(uuid4()),
                "payload": {"nested": {"provider_token": "must-not-enter-ledger"}},
            },
        )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_request"


def test_ai_provider_control_allows_governance_token_budget(
    test_settings,
) -> None:
    spec = next(
        item for item in PROVIDER_CONTROL_SPECS
        if item.operation_id == "ai.inference.request"
    )
    app = create_app(
        settings=test_settings,
        runtime=_runtime(test_settings, capabilities_enabled=True),
    )
    with TestClient(app) as client:
        response = client.post(
            spec.route,
            headers=_headers(spec),
            json={
                "operation_id": str(uuid4()),
                "payload": {
                    "resource_reference": "ai-request-1",
                    "task_type": "document.summary",
                    "schema_version": "1.0",
                    "token_budget": 2_000,
                    "max_tokens": 500,
                },
            },
        )
    assert response.status_code == 202, response.text
    assert response.json()["external_effect_dispatched"] is False
