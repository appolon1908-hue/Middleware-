from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol

import asyncpg

from .models import EventEnvelope, IngressResult


class StorageError(RuntimeError):
    pass


class ReplayConflict(StorageError):
    pass


class InboxStore(Protocol):
    async def accept(
        self,
        envelope: EventEnvelope,
        *,
        producer_client_id: str,
        body_sha256: str,
    ) -> IngressResult:
        ...

    async def ready(self) -> bool:
        ...

    async def close(self) -> None:
        ...


class MemoryInboxStore:
    """Test/development-only storage. Settings prohibit it in staging/production."""

    def __init__(self) -> None:
        self._items: dict[tuple[str, str], tuple[str, IngressResult]] = {}

    async def accept(
        self,
        envelope: EventEnvelope,
        *,
        producer_client_id: str,
        body_sha256: str,
    ) -> IngressResult:
        key = (envelope.tenant_id, envelope.id)
        existing = self._items.get(key)
        if existing:
            old_hash, result = existing
            if old_hash != body_sha256:
                raise ReplayConflict("event id was reused with a different payload")
            return result.model_copy(update={"status": "duplicate", "duplicate": True})
        result = IngressResult(
            event_id=envelope.id,
            tenant_id=envelope.tenant_id,
            status="accepted",
            duplicate=False,
            correlation_id=envelope.correlation_id,
        )
        self._items[key] = (body_sha256, result)
        return result

    async def ready(self) -> bool:
        return True

    async def close(self) -> None:
        return None


class PostgresInboxStore:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    @classmethod
    async def connect(cls, database_url: str) -> "PostgresInboxStore":
        pool = await asyncpg.create_pool(
            database_url,
            min_size=1,
            max_size=10,
            command_timeout=10,
        )
        store = cls(pool)
        await store.verify_schema()
        return store

    async def verify_schema(self) -> None:
        async with self.pool.acquire() as conn:
            regclass = await conn.fetchval("SELECT to_regclass('public.middleware_inbox')")
            if regclass is None:
                raise StorageError(
                    "middleware_inbox table is missing; apply migrations/0001_runtime.sql first"
                )

    async def accept(
        self,
        envelope: EventEnvelope,
        *,
        producer_client_id: str,
        body_sha256: str,
    ) -> IngressResult:
        payload = envelope.model_dump(mode="json")
        now = datetime.now(timezone.utc)
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    """
                    INSERT INTO middleware_inbox (
                        event_id, tenant_id, source_client_id, event_type,
                        body_sha256, idempotency_key, correlation_id,
                        payload, received_at, status
                    ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8::jsonb,$9,'accepted')
                    ON CONFLICT DO NOTHING
                    RETURNING event_id
                    """,
                    envelope.id,
                    envelope.tenant_id,
                    producer_client_id,
                    envelope.type,
                    body_sha256,
                    envelope.idempotency_key,
                    envelope.correlation_id,
                    json.dumps(payload, separators=(",", ":"), sort_keys=True),
                    now,
                )
                if row:
                    return IngressResult(
                        event_id=envelope.id,
                        tenant_id=envelope.tenant_id,
                        status="accepted",
                        duplicate=False,
                        correlation_id=envelope.correlation_id,
                    )
                existing = await conn.fetchrow(
                    """
                    SELECT event_id, tenant_id, body_sha256, correlation_id
                    FROM middleware_inbox
                    WHERE (tenant_id=$1 AND event_id=$2)
                       OR (tenant_id=$1 AND idempotency_key=$3)
                    ORDER BY received_at ASC
                    LIMIT 1
                    """,
                    envelope.tenant_id,
                    envelope.id,
                    envelope.idempotency_key,
                )
                if not existing:
                    raise StorageError("inbox conflict could not be reconciled")
                if existing["body_sha256"] != body_sha256:
                    raise ReplayConflict(
                        "event/idempotency key was reused with a different payload"
                    )
                return IngressResult(
                    event_id=existing["event_id"],
                    tenant_id=existing["tenant_id"],
                    status="duplicate",
                    duplicate=True,
                    correlation_id=existing["correlation_id"],
                )

    async def ready(self) -> bool:
        try:
            async with self.pool.acquire() as conn:
                return await conn.fetchval("SELECT 1") == 1
        except Exception:
            return False

    async def close(self) -> None:
        await self.pool.close()


@dataclass(frozen=True)
class OutboxRecord:
    id: int
    tenant_id: str
    destination: str
    event_type: str
    payload: dict[str, Any]
    attempt_count: int


class PostgresOutboxStore:
    """Lease-based outbox with bounded retry and DLQ transitions.

    Dispatch remains disabled by Settings on this branch.
    """

    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    async def claim(self, *, worker_id: str, lease_seconds: int = 60) -> OutboxRecord | None:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    """
                    WITH candidate AS (
                        SELECT id
                        FROM middleware_outbox
                        WHERE completed_at IS NULL
                          AND dead_lettered_at IS NULL
                          AND next_attempt_at <= now()
                          AND (lease_until IS NULL OR lease_until < now())
                        ORDER BY id
                        FOR UPDATE SKIP LOCKED
                        LIMIT 1
                    )
                    UPDATE middleware_outbox o
                    SET lease_owner=$1,
                        lease_until=now() + ($2 * interval '1 second'),
                        attempt_count=o.attempt_count + 1
                    FROM candidate
                    WHERE o.id=candidate.id
                    RETURNING o.id, o.tenant_id, o.destination, o.event_type,
                              o.payload, o.attempt_count
                    """,
                    worker_id,
                    lease_seconds,
                )
        if not row:
            return None
        raw_payload = row["payload"]
        payload = json.loads(raw_payload) if isinstance(raw_payload, str) else dict(raw_payload)
        return OutboxRecord(
            id=row["id"],
            tenant_id=row["tenant_id"],
            destination=row["destination"],
            event_type=row["event_type"],
            payload=payload,
            attempt_count=row["attempt_count"],
        )

    async def complete(self, record_id: int, *, worker_id: str) -> None:
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE middleware_outbox
                SET completed_at=now(), lease_owner=NULL, lease_until=NULL, last_error=NULL
                WHERE id=$1 AND lease_owner=$2
                """,
                record_id,
                worker_id,
            )
            if result != "UPDATE 1":
                raise StorageError("outbox lease ownership lost before completion")

    async def fail(
        self,
        record_id: int,
        *,
        worker_id: str,
        error: str,
        max_attempts: int = 8,
    ) -> None:
        safe_error = error[:2048]
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE middleware_outbox
                SET last_error=$3,
                    lease_owner=NULL,
                    lease_until=NULL,
                    dead_lettered_at=CASE WHEN attempt_count >= $4 THEN now() ELSE NULL END,
                    next_attempt_at=CASE
                        WHEN attempt_count >= $4 THEN next_attempt_at
                        ELSE now() + (
                            LEAST(3600, power(2, LEAST(attempt_count, 10))::int)
                            * interval '1 second'
                        )
                    END
                WHERE id=$1 AND lease_owner=$2
                """,
                record_id,
                worker_id,
                safe_error,
                max_attempts,
            )
            if result != "UPDATE 1":
                raise StorageError("outbox lease ownership lost before retry transition")
