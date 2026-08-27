from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal, Protocol

import asyncpg

from .models import EventEnvelope, IngressResult


RUNTIME_SCHEMA_VERSION = 1
DEFAULT_MAX_OUTBOX_ATTEMPTS = 8
ReconciliationAction = Literal["retry", "complete", "dead_letter"]


class StorageError(RuntimeError):
    code = "dependency_unavailable"
    retryable = True


class ReplayConflict(StorageError):
    code = "idempotency_conflict"
    retryable = False


class ReconciliationError(StorageError):
    code = "reconciliation_invalid"
    retryable = False


class InboxStore(Protocol):
    async def accept(
        self,
        envelope: EventEnvelope,
        *,
        producer_client_id: str,
        body_sha256: str,
        semantic_sha256: str,
    ) -> IngressResult:
        ...

    async def ready(self) -> bool:
        ...

    async def close(self) -> None:
        ...


class MemoryInboxStore:
    """Test/development-only storage matching PostgreSQL identity constraints."""

    def __init__(self) -> None:
        self._event_items: dict[tuple[str, str], tuple[str, IngressResult]] = {}
        self._idempotency_items: dict[tuple[str, str], tuple[str, IngressResult]] = {}

    async def accept(
        self,
        envelope: EventEnvelope,
        *,
        producer_client_id: str,
        body_sha256: str,
        semantic_sha256: str,
    ) -> IngressResult:
        event_key = (envelope.tenant_id, envelope.id)
        idempotency_key = (envelope.tenant_id, envelope.idempotency_key)
        event_existing = self._event_items.get(event_key)
        idem_existing = self._idempotency_items.get(idempotency_key)

        if event_existing and idem_existing and event_existing[1].event_id != idem_existing[1].event_id:
            raise ReplayConflict("event and idempotency identities refer to different accepted events")

        existing = event_existing or idem_existing
        if existing:
            old_semantic_hash, result = existing
            if old_semantic_hash != semantic_sha256:
                raise ReplayConflict("event/idempotency identity was reused with a different semantic payload")
            return result.model_copy(update={"status": "duplicate", "duplicate": True})

        result = IngressResult(
            event_id=envelope.id,
            tenant_id=envelope.tenant_id,
            status="accepted",
            duplicate=False,
            correlation_id=envelope.correlation_id,
        )
        item = (semantic_sha256, result)
        self._event_items[event_key] = item
        self._idempotency_items[idempotency_key] = item
        return result

    async def ready(self) -> bool:
        return True

    async def close(self) -> None:
        return None


class PostgresInboxStore:
    REQUIRED_COLUMNS = {
        "middleware_schema_migrations": {"version", "name", "applied_at"},
        "middleware_inbox": {
            "event_id",
            "tenant_id",
            "source_client_id",
            "event_type",
            "body_sha256",
            "semantic_sha256",
            "idempotency_key",
            "correlation_id",
            "payload",
            "received_at",
            "status",
            "processed_at",
            "last_error",
        },
        "middleware_outbox": {
            "id",
            "tenant_id",
            "destination",
            "event_type",
            "payload",
            "idempotency_key",
            "created_at",
            "next_attempt_at",
            "attempt_count",
            "lease_owner",
            "lease_until",
            "completed_at",
            "dead_lettered_at",
            "reconciliation_required_at",
            "last_error",
        },
        "middleware_reconciliation_audit": {
            "id",
            "outbox_id",
            "tenant_id",
            "action",
            "operator_id",
            "reason",
            "attempt_count",
            "created_at",
        },
    }
    REQUIRED_UDT_TYPES = {
        ("middleware_schema_migrations", "version"): "int4",
        ("middleware_schema_migrations", "name"): "text",
        ("middleware_schema_migrations", "applied_at"): "timestamptz",
        ("middleware_inbox", "event_id"): "text",
        ("middleware_inbox", "tenant_id"): "text",
        ("middleware_inbox", "source_client_id"): "text",
        ("middleware_inbox", "event_type"): "text",
        ("middleware_inbox", "body_sha256"): "bpchar",
        ("middleware_inbox", "semantic_sha256"): "bpchar",
        ("middleware_inbox", "idempotency_key"): "text",
        ("middleware_inbox", "correlation_id"): "text",
        ("middleware_inbox", "payload"): "jsonb",
        ("middleware_inbox", "received_at"): "timestamptz",
        ("middleware_inbox", "status"): "text",
        ("middleware_inbox", "processed_at"): "timestamptz",
        ("middleware_inbox", "last_error"): "text",
        ("middleware_outbox", "id"): "int8",
        ("middleware_outbox", "tenant_id"): "text",
        ("middleware_outbox", "destination"): "text",
        ("middleware_outbox", "event_type"): "text",
        ("middleware_outbox", "payload"): "jsonb",
        ("middleware_outbox", "idempotency_key"): "text",
        ("middleware_outbox", "created_at"): "timestamptz",
        ("middleware_outbox", "next_attempt_at"): "timestamptz",
        ("middleware_outbox", "attempt_count"): "int4",
        ("middleware_outbox", "lease_owner"): "text",
        ("middleware_outbox", "lease_until"): "timestamptz",
        ("middleware_outbox", "completed_at"): "timestamptz",
        ("middleware_outbox", "dead_lettered_at"): "timestamptz",
        ("middleware_outbox", "reconciliation_required_at"): "timestamptz",
        ("middleware_outbox", "last_error"): "text",
        ("middleware_reconciliation_audit", "id"): "int8",
        ("middleware_reconciliation_audit", "outbox_id"): "int8",
        ("middleware_reconciliation_audit", "tenant_id"): "text",
        ("middleware_reconciliation_audit", "action"): "text",
        ("middleware_reconciliation_audit", "operator_id"): "text",
        ("middleware_reconciliation_audit", "reason"): "text",
        ("middleware_reconciliation_audit", "attempt_count"): "int4",
        ("middleware_reconciliation_audit", "created_at"): "timestamptz",
    }
    REQUIRED_KEYS = {
        ("middleware_schema_migrations", "PRIMARY KEY", ("version",)),
        ("middleware_inbox", "PRIMARY KEY", ("tenant_id", "event_id")),
        ("middleware_inbox", "UNIQUE", ("tenant_id", "idempotency_key")),
        ("middleware_outbox", "PRIMARY KEY", ("id",)),
        (
            "middleware_outbox",
            "UNIQUE",
            ("tenant_id", "destination", "idempotency_key"),
        ),
        ("middleware_reconciliation_audit", "PRIMARY KEY", ("id",)),
    }

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
        try:
            await store.verify_schema()
        except Exception:
            await pool.close()
            raise
        return store

    async def verify_schema(self) -> None:
        async with self.pool.acquire() as conn:
            head = await conn.fetchval(
                "SELECT max(version) FROM middleware_schema_migrations"
            )
            if head != RUNTIME_SCHEMA_VERSION:
                raise StorageError(
                    f"runtime schema head mismatch: expected {RUNTIME_SCHEMA_VERSION}, got {head!r}"
                )
            rows = await conn.fetch(
                """
                SELECT table_name, column_name, udt_name
                FROM information_schema.columns
                WHERE table_schema='public'
                  AND table_name = ANY($1::text[])
                """,
                list(self.REQUIRED_COLUMNS),
            )
            columns: dict[str, set[str]] = {
                table: set() for table in self.REQUIRED_COLUMNS
            }
            types: dict[tuple[str, str], str] = {}
            for row in rows:
                columns[row["table_name"]].add(row["column_name"])
                types[(row["table_name"], row["column_name"])] = row["udt_name"]
            for table, required in self.REQUIRED_COLUMNS.items():
                missing = required - columns.get(table, set())
                if missing:
                    raise StorageError(
                        f"runtime schema table {table} is missing columns: {sorted(missing)}"
                    )
            for key, expected_type in self.REQUIRED_UDT_TYPES.items():
                if types.get(key) != expected_type:
                    raise StorageError(
                        f"runtime schema type mismatch for {key[0]}.{key[1]}: "
                        f"expected {expected_type}, got {types.get(key)!r}"
                    )
            key_rows = await conn.fetch(
                """
                SELECT tc.table_name,
                       tc.constraint_type,
                       array_agg(kcu.column_name ORDER BY kcu.ordinal_position) AS columns
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu
                  ON tc.constraint_schema = kcu.constraint_schema
                 AND tc.constraint_name = kcu.constraint_name
                 AND tc.table_name = kcu.table_name
                WHERE tc.table_schema='public'
                  AND tc.table_name = ANY($1::text[])
                  AND tc.constraint_type IN ('PRIMARY KEY', 'UNIQUE')
                GROUP BY tc.table_name, tc.constraint_type, tc.constraint_name
                """,
                list(self.REQUIRED_COLUMNS),
            )
            found_keys = {
                (
                    row["table_name"],
                    row["constraint_type"],
                    tuple(row["columns"]),
                )
                for row in key_rows
            }
            missing_keys = self.REQUIRED_KEYS - found_keys
            if missing_keys:
                raise StorageError(
                    f"runtime schema is missing key constraints: {sorted(missing_keys)}"
                )

    async def accept(
        self,
        envelope: EventEnvelope,
        *,
        producer_client_id: str,
        body_sha256: str,
        semantic_sha256: str,
    ) -> IngressResult:
        payload = envelope.model_dump(mode="json")
        now = datetime.now(timezone.utc)
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    """
                    INSERT INTO middleware_inbox (
                        event_id, tenant_id, source_client_id, event_type,
                        body_sha256, semantic_sha256, idempotency_key, correlation_id,
                        payload, received_at, status
                    ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9::jsonb,$10,'accepted')
                    ON CONFLICT DO NOTHING
                    RETURNING event_id
                    """,
                    envelope.id,
                    envelope.tenant_id,
                    producer_client_id,
                    envelope.type,
                    body_sha256,
                    semantic_sha256,
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
                existing_rows = await conn.fetch(
                    """
                    SELECT event_id, tenant_id, idempotency_key, semantic_sha256, correlation_id
                    FROM middleware_inbox
                    WHERE (tenant_id=$1 AND event_id=$2)
                       OR (tenant_id=$1 AND idempotency_key=$3)
                    ORDER BY received_at ASC
                    """,
                    envelope.tenant_id,
                    envelope.id,
                    envelope.idempotency_key,
                )
                if not existing_rows:
                    raise StorageError("inbox conflict could not be reconciled")
                identities = {(row["event_id"], row["idempotency_key"]) for row in existing_rows}
                if len(identities) > 1:
                    raise ReplayConflict(
                        "event and idempotency identities refer to different accepted events"
                    )
                existing = existing_rows[0]
                if existing["semantic_sha256"] != semantic_sha256:
                    raise ReplayConflict(
                        "event/idempotency identity was reused with a different semantic payload"
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
                if await conn.fetchval("SELECT 1") != 1:
                    return False
            await self.verify_schema()
            return True
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
    idempotency_key: str
    payload: dict[str, Any]
    attempt_count: int


class PostgresOutboxStore:
    """Lease-based outbox with bounded retry, reconciliation, and DLQ states."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    async def claim(
        self,
        *,
        worker_id: str,
        lease_seconds: float = 60,
        max_attempts: int = DEFAULT_MAX_OUTBOX_ATTEMPTS,
    ) -> OutboxRecord | None:
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        if max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    """
                    UPDATE middleware_outbox
                    SET dead_lettered_at=now(),
                        lease_owner=NULL,
                        lease_until=NULL,
                        last_error=COALESCE(
                            last_error,
                            'maximum attempts exhausted after worker lease expiry'
                        )
                    WHERE completed_at IS NULL
                      AND dead_lettered_at IS NULL
                      AND reconciliation_required_at IS NULL
                      AND attempt_count >= $1
                      AND (lease_until IS NULL OR lease_until < now())
                    """,
                    max_attempts,
                )
                row = await conn.fetchrow(
                    """
                    WITH candidate AS (
                        SELECT id
                        FROM middleware_outbox
                        WHERE completed_at IS NULL
                          AND dead_lettered_at IS NULL
                          AND reconciliation_required_at IS NULL
                          AND attempt_count < $3
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
                              o.idempotency_key, o.payload, o.attempt_count
                    """,
                    worker_id,
                    lease_seconds,
                    max_attempts,
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
            idempotency_key=row["idempotency_key"],
            payload=payload,
            attempt_count=row["attempt_count"],
        )

    async def complete(self, record_id: int, *, worker_id: str) -> None:
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE middleware_outbox
                SET completed_at=now(), lease_owner=NULL, lease_until=NULL, last_error=NULL
                WHERE id=$1 AND lease_owner=$2 AND reconciliation_required_at IS NULL
                """,
                record_id,
                worker_id,
            )
            if result != "UPDATE 1":
                raise StorageError("outbox lease ownership lost before completion")

    async def quarantine_unknown_outcome(
        self,
        record_id: int,
        *,
        worker_id: str,
        error: str,
        lease_seconds: float = 60,
    ) -> None:
        """Persist unknown-on-crash state and refresh active dispatch ownership.

        This is the final pre-provider state transition. It both marks the row as
        reconciliation-required and refreshes the owning worker's lease from the
        database transaction time, guaranteeing a full lease window before the
        provider handler begins.
        """

        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        safe_error = error[:2048]
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE middleware_outbox
                SET last_error=$3,
                    reconciliation_required_at=now(),
                    lease_until=now() + ($4 * interval '1 second')
                WHERE id=$1
                  AND lease_owner=$2
                  AND lease_until IS NOT NULL
                  AND lease_until > now()
                  AND completed_at IS NULL
                  AND dead_lettered_at IS NULL
                  AND reconciliation_required_at IS NULL
                """,
                record_id,
                worker_id,
                safe_error,
                lease_seconds,
            )
            if result != "UPDATE 1":
                raise StorageError("outbox lease ownership lost before reconciliation quarantine")

    async def resolve_reconciliation(
        self,
        record_id: int,
        *,
        operator_id: str,
        action: ReconciliationAction,
        reason: str,
        max_attempts: int = DEFAULT_MAX_OUTBOX_ATTEMPTS,
        worker_id: str | None = None,
    ) -> None:
        if action not in {"retry", "complete", "dead_letter"}:
            raise ValueError("unsupported reconciliation action")
        if max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        safe_operator = operator_id.strip()
        safe_reason = reason.strip()
        safe_worker = worker_id.strip() if worker_id is not None else None
        if not safe_operator or len(safe_operator) > 160:
            raise ValueError("operator_id must contain 1..160 characters")
        if not safe_reason or len(safe_reason) > 2048:
            raise ValueError("reason must contain 1..2048 characters")
        if worker_id is not None and (not safe_worker or len(safe_worker) > 256):
            raise ValueError("worker_id must contain 1..256 characters")

        async with self.pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    """
                    SELECT id, tenant_id, attempt_count,
                           reconciliation_required_at, completed_at, dead_lettered_at,
                           lease_owner, lease_until,
                           (lease_until IS NOT NULL AND lease_until > now()) AS lease_active
                    FROM middleware_outbox
                    WHERE id=$1
                    FOR UPDATE
                    """,
                    record_id,
                )
                if row is None:
                    raise ReconciliationError("outbox record does not exist")
                if row["completed_at"] is not None or row["dead_lettered_at"] is not None:
                    raise ReconciliationError("outbox record is already terminal")
                if row["reconciliation_required_at"] is None:
                    raise ReconciliationError("outbox record is not awaiting reconciliation")

                lease_active = bool(row["lease_active"])
                if lease_active:
                    if safe_worker is None:
                        raise ReconciliationError(
                            "active dispatch cannot be manually reconciled before lease expiry"
                        )
                    if row["lease_owner"] != safe_worker:
                        raise ReconciliationError("active dispatch is owned by another worker")
                    if action == "dead_letter":
                        raise ReconciliationError(
                            "active worker may resolve only complete or known-safe retry"
                        )
                elif safe_worker is not None:
                    raise ReconciliationError(
                        "worker dispatch lease expired; manual reconciliation is required"
                    )

                if action == "retry" and row["attempt_count"] >= max_attempts:
                    raise ReconciliationError(
                        "attempt limit is exhausted; choose complete or dead_letter"
                    )

                await conn.execute(
                    """
                    INSERT INTO middleware_reconciliation_audit
                      (outbox_id, tenant_id, action, operator_id, reason, attempt_count)
                    VALUES ($1,$2,$3,$4,$5,$6)
                    """,
                    record_id,
                    row["tenant_id"],
                    action,
                    safe_operator,
                    safe_reason,
                    row["attempt_count"],
                )

                if action == "retry":
                    await conn.execute(
                        """
                        UPDATE middleware_outbox
                        SET reconciliation_required_at=NULL,
                            lease_owner=NULL,
                            lease_until=NULL,
                            next_attempt_at=now(),
                            last_error='reconciliation approved retry: ' || $2
                        WHERE id=$1
                        """,
                        record_id,
                        safe_reason,
                    )
                elif action == "complete":
                    await conn.execute(
                        """
                        UPDATE middleware_outbox
                        SET reconciliation_required_at=NULL,
                            lease_owner=NULL,
                            lease_until=NULL,
                            completed_at=now(),
                            last_error='reconciliation confirmed delivery: ' || $2
                        WHERE id=$1
                        """,
                        record_id,
                        safe_reason,
                    )
                else:
                    await conn.execute(
                        """
                        UPDATE middleware_outbox
                        SET reconciliation_required_at=NULL,
                            lease_owner=NULL,
                            lease_until=NULL,
                            dead_lettered_at=now(),
                            last_error='reconciliation dead-lettered: ' || $2
                        WHERE id=$1
                        """,
                        record_id,
                        safe_reason,
                    )

    async def fail(
        self,
        record_id: int,
        *,
        worker_id: str,
        error: str,
        max_attempts: int = DEFAULT_MAX_OUTBOX_ATTEMPTS,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be positive")
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
                WHERE id=$1
                  AND lease_owner=$2
                  AND reconciliation_required_at IS NULL
                """,
                record_id,
                worker_id,
                safe_error,
                max_attempts,
            )
            if result != "UPDATE 1":
                raise StorageError("outbox lease ownership lost before retry transition")
