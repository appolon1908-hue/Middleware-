from __future__ import annotations

import hashlib
import os
from datetime import datetime, timezone
from pathlib import Path

import asyncpg
import pytest
import pytest_asyncio

from app.models import EventEnvelope
from app.storage import PostgresInboxStore, canonical_payload_sha256
from app.telephony_projection import (
    ODOO_CALL_EVENT_DESTINATION,
    ODOO_CALL_EVENT_OUTBOX_TYPE,
    PostgresTelephonyProjectionStore,
    TelephonyOutboxStore,
)


DATABASE_URL = os.getenv("TEST_DATABASE_URL") or os.getenv("DATABASE_URL")
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not DATABASE_URL, reason="PostgreSQL is required"),
]


def event(payload=None, event_id="evt-telephony-postgres-0001"):
    return EventEnvelope.model_validate(
        {
            "event_id": event_id,
            "event_type": "codestra.vicidial.call.lifecycle.created",
            "event_version": "1.0",
            "occurred_at": datetime(2026, 9, 4, 12, 0, tzinfo=timezone.utc),
            "received_at": datetime(2026, 9, 4, 12, 0, 1, tzinfo=timezone.utc),
            "source": "vicidial-adapter",
            "tenant_id": "tenant-telephony",
            "correlation_id": "corr-telephony-postgres-0001",
            "causation_id": "ami-telephony-postgres-0001",
            "idempotency_key": event_id,
            "payload": payload
            or {
                "schema_version": "1.0",
                "business_unit_id": "BU-1",
                "campaign_id": "CAMPAIGN-1",
                "call_id": "call-postgres-0001",
                "asterisk_uniqueid": "1710000000.1",
                "linkedid": "1710000000.1",
                "agent_id": "AGENT-6101",
                "extension": "6101",
                "keycloak_subject": "11111111-1111-4111-8111-111111111111",
                "sequence": 1,
                "direction": "inbound",
                "caller_number": "+18095550100",
                "destination_number": "+18095550101",
            },
            "metadata": {},
        }
    )


@pytest_asyncio.fixture
async def pool():
    assert DATABASE_URL
    value = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=4)
    migrations = sorted(Path("migrations").glob("[0-9][0-9][0-9][0-9]_*.sql"))
    async with value.acquire() as conn:
        for migration in migrations:
            await conn.execute(migration.read_text(encoding="utf-8"))
        await conn.execute(
            """
            TRUNCATE TABLE
                middleware_outbox_attempt_events,
                middleware_reconciliation_audit,
                middleware_outbox,
                middleware_event_ledger,
                middleware_inbox
            RESTART IDENTITY CASCADE
            """
        )
    try:
        yield value
    finally:
        await value.close()


async def accept(pool, envelope):
    body = envelope.model_dump_json().encode()
    result = await PostgresInboxStore(pool).accept(
        envelope,
        producer_client_id="vicidial-adapter",
        body_sha256=hashlib.sha256(body).hexdigest(),
        semantic_sha256=canonical_payload_sha256(
            envelope.model_dump(mode="json")
        ),
    )
    assert result.status == "accepted"


@pytest.mark.asyncio
async def test_projection_is_atomic_idempotent_and_destination_filtered(pool):
    envelope = event()
    await accept(pool, envelope)

    projection = PostgresTelephonyProjectionStore(pool)
    assert await projection.project_once() is True
    assert await projection.project_once() is False

    async with pool.acquire() as conn:
        inbox = await conn.fetchrow(
            """
            SELECT status, processed_at, last_error
            FROM middleware_inbox
            WHERE tenant_id=$1 AND event_id=$2
            """,
            envelope.tenant_id,
            envelope.event_id,
        )
        rows = await conn.fetch(
            """
            SELECT destination, event_type, idempotency_key, attempt_count, payload
            FROM middleware_outbox
            WHERE tenant_id=$1
            ORDER BY destination
            """,
            envelope.tenant_id,
        )

    assert inbox["status"] == "validated"
    assert inbox["processed_at"] is not None
    assert inbox["last_error"] is None
    assert {row["destination"] for row in rows} == {
        "nats-jetstream",
        ODOO_CALL_EVENT_DESTINATION,
    }
    call_event = next(
        row for row in rows if row["destination"] == ODOO_CALL_EVENT_DESTINATION
    )
    assert call_event["event_type"] == ODOO_CALL_EVENT_OUTBOX_TYPE
    assert call_event["idempotency_key"] == "odoo-call-event:" + envelope.event_id
    assert call_event["payload"]["call_id"] == "call-postgres-0001"

    outbox = TelephonyOutboxStore(pool)
    claimed = await outbox.claim(worker_id="telephony-worker-1")
    assert claimed is not None
    assert claimed.destination == ODOO_CALL_EVENT_DESTINATION
    assert claimed.idempotency_key == call_event["idempotency_key"]

    async with pool.acquire() as conn:
        nats_attempts = await conn.fetchval(
            """
            SELECT attempt_count
            FROM middleware_outbox
            WHERE tenant_id=$1 AND destination='nats-jetstream'
            """,
            envelope.tenant_id,
        )
    assert nats_attempts == 0
    await outbox.complete(claimed.id, worker_id="telephony-worker-1")


@pytest.mark.asyncio
async def test_projection_rejects_malformed_persisted_lifecycle_event(pool):
    envelope = event(
        payload={"schema_version": "1.0", "unexpected": True},
        event_id="evt-telephony-postgres-invalid",
    )
    await accept(pool, envelope)

    projection = PostgresTelephonyProjectionStore(pool)
    assert await projection.project_once() is True

    async with pool.acquire() as conn:
        inbox = await conn.fetchrow(
            """
            SELECT status, processed_at, last_error
            FROM middleware_inbox
            WHERE tenant_id=$1 AND event_id=$2
            """,
            envelope.tenant_id,
            envelope.event_id,
        )
        odoo_count = await conn.fetchval(
            """
            SELECT count(*)
            FROM middleware_outbox
            WHERE tenant_id=$1 AND destination=$2
            """,
            envelope.tenant_id,
            ODOO_CALL_EVENT_DESTINATION,
        )

    assert inbox["status"] == "rejected"
    assert inbox["processed_at"] is not None
    assert "TelephonyProjectionError" in inbox["last_error"]
    assert odoo_count == 0
