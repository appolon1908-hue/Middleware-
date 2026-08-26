from __future__ import annotations

import asyncio
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import asyncpg
import pytest
import pytest_asyncio
from redis.asyncio import Redis

from app.models import EventEnvelope
from app.replay import RedisReplayGuard, ReplayBusy
from app.storage import PostgresInboxStore, PostgresOutboxStore, ReplayConflict


DATABASE_URL = os.getenv("DATABASE_URL", "")
REDIS_URL = os.getenv("REDIS_URL", "")
RUN = os.getenv("RUNTIME_INTEGRATION_TESTS") == "1"

pytestmark = pytest.mark.skipif(
    not RUN,
    reason="set RUNTIME_INTEGRATION_TESTS=1 against disposable PostgreSQL/Redis",
)


def envelope(
    *,
    event_id: str = "evt-1",
    idempotency_key: str = "idem-0001",
    value: int = 1,
) -> EventEnvelope:
    return EventEnvelope(
        specversion="1.0",
        id=event_id,
        type="codestra.odoo.contact_updated",
        source="urn:codestra:odoo-integration",
        subject="contact/1",
        time=datetime.now(timezone.utc),
        tenant_id="tenant-test",
        correlation_id="corr-1",
        causation_id="cause-1",
        idempotency_key=idempotency_key,
        schema_version=1,
        data={"value": value},
    )


def semantic_digest(item: EventEnvelope) -> str:
    payload = item.model_dump(mode="json")
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


@pytest_asyncio.fixture
async def pool() -> asyncpg.Pool:
    assert DATABASE_URL, "DATABASE_URL is required"
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=8)
    migration = Path("migrations/0001_runtime.sql").read_text(encoding="utf-8")
    async with pool.acquire() as conn:
        await conn.execute("DROP TABLE IF EXISTS middleware_outbox CASCADE")
        await conn.execute("DROP TABLE IF EXISTS middleware_inbox CASCADE")
        await conn.execute("DROP TABLE IF EXISTS middleware_schema_migrations CASCADE")
        await conn.execute(migration)
    try:
        yield pool
    finally:
        await pool.close()


@pytest_asyncio.fixture
async def redis_client() -> Redis:
    assert REDIS_URL, "REDIS_URL is required"
    client = Redis.from_url(REDIS_URL, encoding="utf-8", decode_responses=True)
    await client.flushdb()
    try:
        yield client
    finally:
        await client.flushdb()
        await client.aclose()


@pytest.mark.asyncio
async def test_postgres_schema_and_duplicate_reconciliation(pool: asyncpg.Pool) -> None:
    store = PostgresInboxStore(pool)
    await store.verify_schema()

    item = envelope()
    digest = semantic_digest(item)
    first = await store.accept(
        item,
        producer_client_id="odoo-integration",
        body_sha256="a" * 64,
        semantic_sha256=digest,
    )
    second = await store.accept(
        item,
        producer_client_id="odoo-integration",
        body_sha256="b" * 64,
        semantic_sha256=digest,
    )

    assert first.status == "accepted"
    assert second.status == "duplicate"
    assert second.duplicate is True


@pytest.mark.asyncio
async def test_postgres_concurrent_same_event_is_single_accept(pool: asyncpg.Pool) -> None:
    store = PostgresInboxStore(pool)
    item = envelope(event_id="evt-concurrent", idempotency_key="idem-concurrent")
    digest = semantic_digest(item)

    async def accept_once() -> str:
        result = await store.accept(
            item,
            producer_client_id="odoo-integration",
            body_sha256="c" * 64,
            semantic_sha256=digest,
        )
        return result.status

    statuses = await asyncio.gather(accept_once(), accept_once())
    assert sorted(statuses) == ["accepted", "duplicate"]

    async with pool.acquire() as conn:
        count = await conn.fetchval(
            "SELECT count(*) FROM middleware_inbox WHERE tenant_id=$1 AND event_id=$2",
            item.tenant_id,
            item.id,
        )
    assert count == 1


@pytest.mark.asyncio
async def test_postgres_semantic_collision_fails_closed(pool: asyncpg.Pool) -> None:
    store = PostgresInboxStore(pool)
    first = envelope(event_id="evt-semantic", idempotency_key="idem-semantic", value=1)
    second = envelope(event_id="evt-semantic", idempotency_key="idem-semantic", value=2)

    await store.accept(
        first,
        producer_client_id="odoo-integration",
        body_sha256="d" * 64,
        semantic_sha256=semantic_digest(first),
    )
    with pytest.raises(ReplayConflict):
        await store.accept(
            second,
            producer_client_id="odoo-integration",
            body_sha256="e" * 64,
            semantic_sha256=semantic_digest(second),
        )


@pytest.mark.asyncio
async def test_outbox_claim_carries_idempotency_and_skip_locked(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO middleware_outbox
              (tenant_id, destination, event_type, payload, idempotency_key)
            VALUES ($1,$2,$3,$4::jsonb,$5)
            """,
            "tenant-test",
            "sandbox-provider",
            "codestra.test.delivery",
            json.dumps({"hello": "world"}),
            "delivery-idem-1",
        )

    store = PostgresOutboxStore(pool)
    one, two = await asyncio.gather(
        store.claim(worker_id="worker-a", lease_seconds=30, max_attempts=3),
        store.claim(worker_id="worker-b", lease_seconds=30, max_attempts=3),
    )
    claimed = [record for record in (one, two) if record is not None]
    assert len(claimed) == 1
    assert claimed[0].idempotency_key == "delivery-idem-1"
    assert claimed[0].attempt_count == 1


@pytest.mark.asyncio
async def test_outbox_expired_max_attempts_moves_to_dlq(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as conn:
        row_id = await conn.fetchval(
            """
            INSERT INTO middleware_outbox
              (tenant_id, destination, event_type, payload, idempotency_key,
               attempt_count, lease_owner, lease_until)
            VALUES ($1,$2,$3,$4::jsonb,$5,3,'dead-worker',now() - interval '1 second')
            RETURNING id
            """,
            "tenant-test",
            "sandbox-provider",
            "codestra.test.delivery",
            json.dumps({"hello": "world"}),
            "delivery-idem-exhausted",
        )

    store = PostgresOutboxStore(pool)
    record = await store.claim(worker_id="worker-new", lease_seconds=30, max_attempts=3)
    assert record is None

    async with pool.acquire() as conn:
        dead_lettered = await conn.fetchval(
            "SELECT dead_lettered_at IS NOT NULL FROM middleware_outbox WHERE id=$1",
            row_id,
        )
    assert dead_lettered is True


@pytest.mark.asyncio
async def test_redis_replay_lock_owner_and_tuple_isolation(redis_client: Redis) -> None:
    guard = RedisReplayGuard(redis_client, lock_seconds=30)

    token = await guard.acquire("tenant:a", "event:b")
    with pytest.raises(ReplayBusy):
        await guard.acquire("tenant:a", "event:b")

    await guard.release("tenant:a", "event:b", "wrong-token")
    with pytest.raises(ReplayBusy):
        await guard.acquire("tenant:a", "event:b")

    # These delimiter-containing tuples must map to different Redis keys.
    other = await guard.acquire("tenant", "a:event:b")
    await guard.release("tenant", "a:event:b", other)

    await guard.release("tenant:a", "event:b", token)
    token2 = await guard.acquire("tenant:a", "event:b")
    await guard.release("tenant:a", "event:b", token2)
