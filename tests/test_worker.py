from __future__ import annotations

import asyncio

import pytest

from app.storage import OutboxRecord
from app.worker import OutboxWorker


class FakeStore:
    def __init__(self, record: OutboxRecord | None) -> None:
        self.record = record
        self.claim_args = None
        self.failed = []
        self.completed = []

    async def claim(self, **kwargs):
        self.claim_args = kwargs
        record, self.record = self.record, None
        return record

    async def fail(self, record_id: int, **kwargs):
        self.failed.append((record_id, kwargs))

    async def complete(self, record_id: int, **kwargs):
        self.completed.append((record_id, kwargs))


def record() -> OutboxRecord:
    return OutboxRecord(
        id=1,
        tenant_id="tenant-1",
        destination="provider",
        event_type="codestra.test.event",
        idempotency_key="idem-12345678",
        payload={"ok": True},
        attempt_count=1,
    )


@pytest.mark.asyncio
async def test_worker_passes_authoritative_idempotency_key_to_handler() -> None:
    store = FakeStore(record())
    observed = []

    async def handler(item: OutboxRecord) -> None:
        observed.append(item.idempotency_key)

    worker = OutboxWorker(store, {"provider": handler})  # type: ignore[arg-type]
    assert await worker.run_once() is True
    assert observed == ["idem-12345678"]
    assert store.completed


@pytest.mark.asyncio
async def test_handler_timeout_occurs_before_lease_expiry() -> None:
    store = FakeStore(record())

    async def slow_handler(item: OutboxRecord) -> None:
        await asyncio.sleep(0.05)

    worker = OutboxWorker(
        store,  # type: ignore[arg-type]
        {"provider": slow_handler},
        lease_seconds=0.1,
        handler_timeout_seconds=0.01,
        max_attempts=8,
    )
    assert await worker.run_once() is True
    assert store.failed
    assert not store.completed
    assert store.claim_args["max_attempts"] == 8
    assert store.claim_args["lease_seconds"] == 0.1
