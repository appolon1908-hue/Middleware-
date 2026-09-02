from __future__ import annotations

from dataclasses import replace
from typing import Any
from uuid import uuid4

import pytest
from temporalio.common import WorkflowIDConflictPolicy, WorkflowIDReusePolicy

from app.commands import TEMPORAL_COMMAND_DESTINATION
from app.storage import OutboxRecord
from app.temporal_transport import (
    TemporalCommandDispatcher,
    TemporalTransportError,
    command_workflow_id,
)


def command_record() -> OutboxRecord:
    command_id = str(uuid4())
    payload = {
        "command_id": command_id,
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
    return OutboxRecord(
        id=1,
        tenant_id="tenant-1",
        destination=TEMPORAL_COMMAND_DESTINATION,
        event_type="crm.contact.create.v1",
        idempotency_key="idempotency-123",
        payload=payload,
        attempt_count=1,
    )


class RecordingTemporalClient:
    def __init__(self) -> None:
        self.calls: list[tuple[Any, Any, dict[str, Any]]] = []

    async def start_workflow(self, workflow, request, **options):
        self.calls.append((workflow, request, options))
        return object()


@pytest.mark.asyncio
async def test_command_dispatch_uses_deterministic_exactly_once_workflow_identity() -> None:
    client = RecordingTemporalClient()
    dispatcher = TemporalCommandDispatcher(client, "codestra-test-critical")  # type: ignore[arg-type]
    record = command_record()

    await dispatcher.dispatch(record)
    assert len(client.calls) == 1
    _, request, options = client.calls[0]
    assert request.tenant_id == record.tenant_id
    assert options["id"] == command_workflow_id(
        record.tenant_id,
        record.payload["command_id"],
        record.idempotency_key,
    )
    assert options["id_reuse_policy"] is WorkflowIDReusePolicy.REJECT_DUPLICATE
    assert options["id_conflict_policy"] is WorkflowIDConflictPolicy.USE_EXISTING


@pytest.mark.asyncio
async def test_command_dispatch_rejects_cross_tenant_outbox_payload() -> None:
    client = RecordingTemporalClient()
    dispatcher = TemporalCommandDispatcher(client, "codestra-test-critical")  # type: ignore[arg-type]
    record = command_record()
    record.payload["tenant_id"] = "different-tenant"
    with pytest.raises(TemporalTransportError):
        await dispatcher.dispatch(record)
    assert client.calls == []


@pytest.mark.asyncio
async def test_retry_dispatch_resumes_from_durable_queued_state() -> None:
    client = RecordingTemporalClient()
    dispatcher = TemporalCommandDispatcher(client, "codestra-test-critical")  # type: ignore[arg-type]
    record = command_record()
    retry_key = "operation-retry:" + "a" * 64
    payload = {**record.payload, "idempotency_key": retry_key}
    record = replace(record, idempotency_key=retry_key, payload=payload)

    await dispatcher.dispatch(record)

    assert client.calls[0][1].resume_from_queued is True
