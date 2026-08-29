from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.commands import (
    CommandCapabilityDisabled,
    CommandConflict,
    CommandEnvelope,
    CommandPolicy,
    CommandPolicyRegistry,
    CommandService,
    MemoryCommandStore,
)
from app.main import create_app
from app.replay import MemoryReplayGuard
from app.runtime import Runtime
from app.storage import MemoryInboxStore


def command_payload(**updates: Any) -> dict[str, Any]:
    value: dict[str, Any] = {
        "command_id": str(uuid4()),
        "command_type": "crm.contact.create.v1",
        "command_version": "1.0",
        "target": "odoo-19",
        "tenant_id": "tenant-1",
        "requested_by": "user-123",
        "correlation_id": "correlation-123",
        "idempotency_key": "idempotency-123",
        "capability": "ODOO_WRITE",
        "payload": {"contact_id": "contact-1"},
    }
    value.update(updates)
    return value


def enabled_policy() -> CommandPolicyRegistry:
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


@pytest.mark.asyncio
async def test_memory_command_ledger_is_idempotent_and_state_guarded() -> None:
    store = MemoryCommandStore()
    command = CommandEnvelope.model_validate(command_payload())

    first = await store.submit(command)
    duplicate = await store.submit(command)
    assert first.state == "persisted"
    assert duplicate.duplicate is True

    conflicting = command.model_copy(update={"payload": {"contact_id": "changed"}})
    with pytest.raises(CommandConflict):
        await store.submit(conflicting)

    queued = await store.transition(
        command.tenant_id,
        command.command_id,
        new_state="queued",
        actor_id="temporal:test",
        reason="workflow accepted intent",
    )
    assert queued.state == "queued"
    with pytest.raises(CommandConflict):
        await store.transition(
            command.tenant_id,
            command.command_id,
            new_state="completed",
            actor_id="temporal:test",
            reason="completion cannot skip read-back",
        )


@pytest.mark.asyncio
async def test_command_policy_fails_closed() -> None:
    command = CommandEnvelope.model_validate(command_payload())
    service = CommandService(MemoryCommandStore(), enabled_policy())

    with pytest.raises(CommandCapabilityDisabled):
        await service.submit(command, authenticated_subject="different-user")
    with pytest.raises(CommandCapabilityDisabled):
        await CommandService(
            MemoryCommandStore(),
            CommandPolicyRegistry(enabled_policy().policies, {"ODOO_WRITE": False}),
        ).submit(command, authenticated_subject="user-123")
    with pytest.raises(CommandCapabilityDisabled):
        await service.submit(
            command.model_copy(update={"target": "another-adapter"}),
            authenticated_subject="user-123",
        )


class CommandTokenVerifier:
    async def verify(
        self,
        authorization: str,
        *,
        expected_client_id: str,
        required_scope: str,
    ) -> dict[str, Any]:
        if authorization != f"Bearer {required_scope}":
            from app.security import AuthenticationError

            raise AuthenticationError("invalid command token")
        return {
            "azp": expected_client_id,
            "scope": required_scope,
            "aud": "middleware-api",
            "tenant_id": "tenant-1",
            "sub": "user-123",
        }

    async def ready(self) -> bool:
        return True


def test_command_api_accepts_duplicate_and_serves_tenant_scoped_status(
    test_settings,
) -> None:
    command_store = MemoryCommandStore()
    runtime = Runtime(
        settings=test_settings,
        inbox=MemoryInboxStore(),
        replay=MemoryReplayGuard(),
        tokens=CommandTokenVerifier(),
        commands=CommandService(command_store, enabled_policy()),
    )
    body = command_payload()
    headers = {
        "Authorization": "Bearer moneybee.middleware.command.write",
        "X-Tenant-ID": body["tenant_id"],
        "X-Correlation-ID": body["correlation_id"],
        "Idempotency-Key": body["idempotency_key"],
        "X-Codestra-Consumer-Id": "moneybee-backend",
    }
    app = create_app(settings=test_settings, runtime=runtime)
    with TestClient(app) as client:
        first = client.post("/v1/commands", json=body, headers=headers)
        assert first.status_code == 202, first.text
        assert first.headers["location"] == f"/v1/operations/{body['command_id']}"
        assert first.json()["state"] == "persisted"

        duplicate = client.post("/v1/commands", json=body, headers=headers)
        assert duplicate.status_code == 200, duplicate.text
        assert duplicate.json()["duplicate"] is True

        status = client.get(
            f"/v1/operations/{body['command_id']}",
            headers={
                "Authorization": "Bearer moneybee.middleware.command.write",
                "X-Tenant-ID": "tenant-1",
                "X-Codestra-Consumer-Id": "moneybee-backend",
            },
        )
        assert status.status_code == 200, status.text
        assert status.json()["state"] == "persisted"

        wrong_tenant = client.get(
            f"/v1/operations/{body['command_id']}",
            headers={
                "Authorization": "Bearer moneybee.middleware.command.write",
                "X-Tenant-ID": "tenant-2",
                "X-Codestra-Consumer-Id": "moneybee-backend",
            },
        )
        assert wrong_tenant.status_code == 403

        invalid = client.post(
            "/v1/commands",
            json={**body, "unexpected": True},
            headers=headers,
        )
        assert invalid.status_code == 400
        assert invalid.json()["error"]["code"] == "invalid_request"


def test_command_api_requires_registered_product_consumer(
    test_settings,
) -> None:
    body = command_payload()
    app = create_app(
        settings=test_settings,
        runtime=Runtime(
            settings=test_settings,
            inbox=MemoryInboxStore(),
            replay=MemoryReplayGuard(),
            tokens=CommandTokenVerifier(),
            commands=CommandService(MemoryCommandStore(), enabled_policy()),
        ),
    )
    headers = {
        "Authorization": "Bearer moneybee.middleware.command.write",
        "X-Tenant-ID": body["tenant_id"],
        "X-Correlation-ID": body["correlation_id"],
        "Idempotency-Key": body["idempotency_key"],
    }
    with TestClient(app) as client:
        missing = client.post("/v1/commands", json=body, headers=headers)
        assert missing.status_code == 400
        assert missing.json()["error"]["code"] == "invalid_request"

        forbidden = client.post(
            "/v1/commands",
            json=body,
            headers={
                **headers,
                "X-Codestra-Consumer-Id": "social-codestra",
                "Authorization": "Bearer social.middleware.command.write",
            },
        )
        assert forbidden.status_code == 403
        assert forbidden.json()["error"]["code"] == "authorization_denied"
