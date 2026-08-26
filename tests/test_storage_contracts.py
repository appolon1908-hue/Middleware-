from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

import pytest

from app.models import EventEnvelope
from app.storage import MemoryInboxStore, PostgresInboxStore, ReplayConflict


def envelope(*, event_id: str, idempotency_key: str, value: int = 1) -> EventEnvelope:
    return EventEnvelope(
        specversion="1.0",
        id=event_id,
        type="codestra.test.event",
        source="urn:codestra:test-source",
        subject="subject/1",
        time=datetime.now(timezone.utc),
        tenant_id="tenant-test",
        correlation_id="corr-1",
        causation_id="cause-1",
        idempotency_key=idempotency_key,
        schema_version=1,
        data={"value": value},
    )


def semantic_digest(item: EventEnvelope) -> str:
    return hashlib.sha256(
        json.dumps(
            item.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


@pytest.mark.asyncio
async def test_memory_store_enforces_tenant_idempotency_uniqueness() -> None:
    store = MemoryInboxStore()
    first = envelope(event_id="evt-1", idempotency_key="idem-shared")
    second = envelope(event_id="evt-2", idempotency_key="idem-shared")

    accepted = await store.accept(
        first,
        producer_client_id="test-source",
        body_sha256="a" * 64,
        semantic_sha256=semantic_digest(first),
    )
    assert accepted.status == "accepted"

    with pytest.raises(ReplayConflict):
        await store.accept(
            second,
            producer_client_id="test-source",
            body_sha256="b" * 64,
            semantic_sha256=semantic_digest(second),
        )


@pytest.mark.asyncio
async def test_memory_store_same_idempotency_same_semantics_is_duplicate() -> None:
    store = MemoryInboxStore()
    first = envelope(event_id="evt-1", idempotency_key="idem-shared")

    accepted = await store.accept(
        first,
        producer_client_id="test-source",
        body_sha256="a" * 64,
        semantic_sha256=semantic_digest(first),
    )
    duplicate = await store.accept(
        first,
        producer_client_id="test-source",
        body_sha256="b" * 64,
        semantic_sha256=semantic_digest(first),
    )

    assert accepted.status == "accepted"
    assert duplicate.status == "duplicate"
    assert duplicate.duplicate is True


def test_readiness_declares_type_for_every_required_column() -> None:
    required = {
        (table, column)
        for table, columns in PostgresInboxStore.REQUIRED_COLUMNS.items()
        for column in columns
    }
    assert set(PostgresInboxStore.REQUIRED_UDT_TYPES) == required
