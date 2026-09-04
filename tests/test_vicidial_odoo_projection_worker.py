from __future__ import annotations

import asyncio
from contextlib import suppress
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.models import EventEnvelope
from app.vicidial_odoo_projection import ProjectionState
from workers.run_vicidial_odoo_projection import process_batch, progress_heartbeat


class FakeMessage:
    def __init__(self, data: bytes) -> None:
        self.data = data
        self.acks = 0
        self.terms = 0
        self.naks: list[float] = []
        self.progress = 0

    async def ack(self) -> None:
        self.acks += 1

    async def term(self) -> None:
        self.terms += 1

    async def nak(self, *, delay: float) -> None:
        self.naks.append(delay)

    async def in_progress(self) -> None:
        self.progress += 1


class ConcurrentDispatcher:
    def __init__(self) -> None:
        self.active = 0
        self.maximum_active = 0

    async def submit(self, event) -> None:
        self.active += 1
        self.maximum_active = max(self.maximum_active, self.active)
        try:
            await asyncio.sleep(0.02)
        finally:
            self.active -= 1

    async def reconcile(self, event, *, reason: str) -> None:
        raise AssertionError(f"unexpected read-back: {reason}")


def envelope(index: int) -> EventEnvelope:
    now = datetime.now(timezone.utc)
    token = f"{index:08d}"
    return EventEnvelope(
        event_id=f"vici-evt-worker-{token}",
        event_type="codestra.vicidial.call.lifecycle.created",
        event_version="1.0",
        occurred_at=now,
        received_at=now,
        source="vicidial-adapter",
        tenant_id="COD",
        correlation_id=f"vici-call-worker-{token}",
        causation_id=f"ami-worker-{token}",
        idempotency_key=f"vici-evt-worker-{token}",
        payload={
            "schema_version": "1.0",
            "business_unit_id": "COD",
            "campaign_id": "TEST_SYN",
            "call_id": f"vici-call-worker-{token}",
            "asterisk_uniqueid": f"1710000000.{index}",
            "linkedid": f"1710000000.{index}",
            "agent_id": "SYN6101",
            "extension": "6101",
            "keycloak_subject": "00000000-0000-0000-0000-000000006101",
            "sequence": 1,
            "direction": "inbound",
            "caller_number": "+18095550100",
        },
        metadata={"transport": "ami"},
    )


@pytest.mark.asyncio
async def test_progress_heartbeat_extends_a_long_delivery() -> None:
    message = FakeMessage(envelope(1).model_dump_json().encode())
    task = asyncio.create_task(
        progress_heartbeat(message, interval_seconds=0.001)
    )
    await asyncio.sleep(0.01)
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task
    assert message.progress > 0


@pytest.mark.asyncio
async def test_fetched_batch_starts_all_messages_without_ack_wait_queueing(
    tmp_path: Path,
) -> None:
    messages = [
        FakeMessage(envelope(index).model_dump_json().encode())
        for index in range(1, 5)
    ]
    dispatcher = ConcurrentDispatcher()
    await process_batch(
        messages,
        settings=SimpleNamespace(synthetic_only=True),
        state=ProjectionState(tmp_path / "projection.sqlite3"),
        dispatcher=dispatcher,
    )
    assert dispatcher.maximum_active == 4
    assert [message.acks for message in messages] == [1, 1, 1, 1]
    assert [message.terms for message in messages] == [0, 0, 0, 0]
    assert [message.naks for message in messages] == [[], [], [], []]
