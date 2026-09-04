"""Durable VICIdial call-lifecycle projection to the Odoo agent workspace.

The VICIdial adapter publishes one canonical Codestra event envelope. Middleware
accepts and stores that envelope first, then this module deterministically derives
the Odoo call-event body. The derived row uses the same tenant/event identity, so
a duplicate webhook replay repairs a missing projection without creating a second
Odoo mutation.

Projection is deliberately gated by ``Settings.odoo_delivery_enabled``. Merely
merging this source does not register an Odoo call-event handler or enable a write.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

import asyncpg
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .models import EventEnvelope, IngressResult
from .storage import (
    InboxStore,
    PostgresInboxStore,
    StorageError,
    canonical_payload_sha256,
)

VICIDIAL_SOURCE = "vicidial-adapter"
VICIDIAL_LIFECYCLE_PREFIX = "codestra.vicidial.call.lifecycle."
ODOO_CALL_EVENT_DESTINATION = "odoo-call-event"
ODOO_CALL_EVENT_OUTBOX_TYPE = "odoo.call.event.apply.v1"

EVENT_TYPE_MAP = {
    f"{VICIDIAL_LIFECYCLE_PREFIX}created": "call.created",
    f"{VICIDIAL_LIFECYCLE_PREFIX}offered": "call.offered",
    f"{VICIDIAL_LIFECYCLE_PREFIX}ringing": "call.ringing",
    f"{VICIDIAL_LIFECYCLE_PREFIX}answered": "call.answered",
    f"{VICIDIAL_LIFECYCLE_PREFIX}connected": "call.connected",
    f"{VICIDIAL_LIFECYCLE_PREFIX}held": "call.held",
    f"{VICIDIAL_LIFECYCLE_PREFIX}resumed": "call.resumed",
    f"{VICIDIAL_LIFECYCLE_PREFIX}transfer.started": "call.transfer.started",
    f"{VICIDIAL_LIFECYCLE_PREFIX}transfer.completed": "call.transfer.completed",
    f"{VICIDIAL_LIFECYCLE_PREFIX}hangup": "call.hangup",
    f"{VICIDIAL_LIFECYCLE_PREFIX}completed": "call.completed",
    f"{VICIDIAL_LIFECYCLE_PREFIX}failed": "call.failed",
    f"{VICIDIAL_LIFECYCLE_PREFIX}missed": "call.missed",
}
VICIDIAL_LIFECYCLE_EVENT_TYPES = frozenset(EVENT_TYPE_MAP)


class CallProjectionError(StorageError):
    code = "vicidial_call_projection_failed"


class OdooCallEvent(BaseModel):
    """Exact body accepted by ``codestra_vicidial_crm`` in Odoo 19."""

    model_config = ConfigDict(extra="allow")

    schema_version: str
    event_id: str = Field(min_length=1, max_length=128)
    event_type: str = Field(min_length=1, max_length=96)
    timestamp: datetime
    correlation_id: str = Field(min_length=1, max_length=180)
    tenant_id: str = Field(min_length=1, max_length=128)
    business_unit_id: str = Field(min_length=1, max_length=255)
    campaign_id: str = Field(min_length=1, max_length=255)
    call_id: str = Field(min_length=1, max_length=255)
    asterisk_uniqueid: str = Field(min_length=1, max_length=255)
    linkedid: str = Field(min_length=1, max_length=255)
    agent_id: str = Field(min_length=1, max_length=255)
    extension: str = Field(min_length=1, max_length=255)
    sequence: int = Field(ge=0)
    keycloak_subject: str = Field(min_length=1, max_length=255)
    direction: str | None = None
    caller_number: str | None = None
    destination_number: str | None = None
    duration: int | None = Field(default=None, ge=0)
    talk_duration: int | None = Field(default=None, ge=0)

    @field_validator("schema_version")
    @classmethod
    def require_schema_version(cls, value: str) -> str:
        if value != "1.0":
            raise ValueError("unsupported Odoo call-event schema version")
        return value

    @field_validator("event_type")
    @classmethod
    def require_supported_event_type(cls, value: str) -> str:
        if value not in EVENT_TYPE_MAP.values():
            raise ValueError("unsupported Odoo call-event type")
        return value

    @field_validator("timestamp")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("call-event timestamp must include a timezone")
        return value

    @field_validator("direction")
    @classmethod
    def require_direction(cls, value: str | None) -> str | None:
        if value is not None and value not in {"inbound", "outbound"}:
            raise ValueError("call direction must be inbound or outbound")
        return value

    @model_validator(mode="after")
    def require_bounded_payload(self) -> "OdooCallEvent":
        encoded = json.dumps(
            self.model_dump(mode="json", exclude_none=True),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        if len(encoded) > 262_144:
            raise ValueError("Odoo call event exceeds the 256 KiB contract")
        return self


def is_vicidial_lifecycle_event(event_type: str) -> bool:
    return event_type in VICIDIAL_LIFECYCLE_EVENT_TYPES


def build_odoo_call_event(envelope: EventEnvelope) -> dict[str, Any]:
    """Validate and flatten one canonical event for the Odoo call endpoint."""

    if envelope.source != VICIDIAL_SOURCE:
        raise CallProjectionError("call lifecycle event source is not vicidial-adapter")
    mapped_type = EVENT_TYPE_MAP.get(envelope.event_type)
    if mapped_type is None:
        raise CallProjectionError("event type is not an approved VICIdial lifecycle event")
    if envelope.idempotency_key != envelope.event_id:
        raise CallProjectionError("call lifecycle idempotency must equal event identity")

    body: dict[str, Any] = dict(envelope.payload)
    protected = {
        "event_id": envelope.event_id,
        "event_type": mapped_type,
        "timestamp": envelope.occurred_at,
        "correlation_id": envelope.correlation_id,
        "tenant_id": envelope.tenant_id,
    }
    for key, expected in protected.items():
        existing = body.get(key)
        if existing is not None and existing != expected:
            raise CallProjectionError(
                f"call lifecycle payload attempts to override canonical {key}"
            )
        body[key] = expected

    try:
        event = OdooCallEvent.model_validate(body)
    except Exception as exc:
        raise CallProjectionError(
            "call lifecycle payload does not match the Odoo call-event contract"
        ) from exc
    return event.model_dump(mode="json", exclude_none=True)


class CallProjectionStore(Protocol):
    async def ensure_projection(self, envelope: EventEnvelope) -> None:
        ...

    async def ready(self) -> bool:
        ...


@dataclass
class MemoryCallProjectionStore:
    """Deterministic test store matching the durable outbox identity contract."""

    rows: dict[tuple[str, str], dict[str, Any]]

    def __init__(self) -> None:
        self.rows = {}

    async def ensure_projection(self, envelope: EventEnvelope) -> None:
        body = build_odoo_call_event(envelope)
        key = (envelope.tenant_id, envelope.event_id)
        existing = self.rows.get(key)
        if existing is not None:
            if canonical_payload_sha256(existing) != canonical_payload_sha256(body):
                raise CallProjectionError(
                    "Odoo call-event projection identity conflicts with another payload"
                )
            return
        self.rows[key] = body

    async def ready(self) -> bool:
        return True


class PostgresCallProjectionStore:
    """Insert the derived Odoo event into the existing durable Middleware outbox."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    async def ensure_projection(self, envelope: EventEnvelope) -> None:
        body = build_odoo_call_event(envelope)
        body_json = json.dumps(
            body,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                accepted = await conn.fetchrow(
                    """
                    SELECT source_client_id, event_type
                    FROM middleware_inbox
                    WHERE tenant_id=$1 AND event_id=$2
                    FOR SHARE
                    """,
                    envelope.tenant_id,
                    envelope.event_id,
                )
                if accepted is None:
                    raise CallProjectionError(
                        "accepted VICIdial event disappeared before projection"
                    )
                if (
                    accepted["source_client_id"] != VICIDIAL_SOURCE
                    or accepted["event_type"] != envelope.event_type
                ):
                    raise CallProjectionError(
                        "accepted inbox identity does not match the call projection"
                    )

                await conn.execute(
                    """
                    INSERT INTO middleware_outbox (
                        tenant_id, destination, event_type, payload, idempotency_key
                    ) VALUES ($1,$2,$3,$4::jsonb,$5)
                    ON CONFLICT (tenant_id, destination, idempotency_key)
                    DO NOTHING
                    """,
                    envelope.tenant_id,
                    ODOO_CALL_EVENT_DESTINATION,
                    ODOO_CALL_EVENT_OUTBOX_TYPE,
                    body_json,
                    envelope.event_id,
                )
                existing = await conn.fetchrow(
                    """
                    SELECT event_type, payload
                    FROM middleware_outbox
                    WHERE tenant_id=$1
                      AND destination=$2
                      AND idempotency_key=$3
                    """,
                    envelope.tenant_id,
                    ODOO_CALL_EVENT_DESTINATION,
                    envelope.event_id,
                )
                if existing is None:
                    raise CallProjectionError(
                        "Odoo call-event outbox row was not persisted"
                    )
                raw = existing["payload"]
                persisted = json.loads(raw) if isinstance(raw, str) else dict(raw)
                if (
                    existing["event_type"] != ODOO_CALL_EVENT_OUTBOX_TYPE
                    or canonical_payload_sha256(persisted)
                    != canonical_payload_sha256(body)
                ):
                    raise CallProjectionError(
                        "Odoo call-event outbox identity conflicts with another payload"
                    )

    async def repair_pending(self, *, limit: int = 1_000) -> int:
        if not 1 <= limit <= 10_000:
            raise ValueError("repair limit must be between 1 and 10000")
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT i.payload
                FROM middleware_inbox i
                WHERE i.source_client_id=$1
                  AND i.event_type=ANY($2::text[])
                  AND i.discarded_at IS NULL
                  AND NOT EXISTS (
                      SELECT 1
                      FROM middleware_outbox o
                      WHERE o.tenant_id=i.tenant_id
                        AND o.destination=$3
                        AND o.idempotency_key=i.event_id
                  )
                ORDER BY i.received_at, i.event_id
                LIMIT $4
                """,
                VICIDIAL_SOURCE,
                sorted(VICIDIAL_LIFECYCLE_EVENT_TYPES),
                ODOO_CALL_EVENT_DESTINATION,
                limit,
            )
        repaired = 0
        for row in rows:
            raw = row["payload"]
            value = json.loads(raw) if isinstance(raw, str) else dict(raw)
            try:
                envelope = EventEnvelope.model_validate(value)
            except Exception as exc:
                raise CallProjectionError(
                    "stored VICIdial event no longer matches the canonical envelope"
                ) from exc
            await self.ensure_projection(envelope)
            repaired += 1
        return repaired

    async def ready(self) -> bool:
        try:
            async with self.pool.acquire() as conn:
                return bool(
                    await conn.fetchval(
                        """
                        SELECT to_regclass('public.middleware_inbox') IS NOT NULL
                           AND to_regclass('public.middleware_outbox') IS NOT NULL
                        """
                    )
                )
        except Exception:
            return False


@dataclass
class ProjectingInboxStore:
    """Inbox decorator that projects only after durable acceptance succeeds."""

    delegate: InboxStore
    projector: CallProjectionStore
    enabled: bool

    async def accept(
        self,
        envelope: EventEnvelope,
        *,
        producer_client_id: str,
        body_sha256: str,
        semantic_sha256: str,
    ) -> IngressResult:
        result = await self.delegate.accept(
            envelope,
            producer_client_id=producer_client_id,
            body_sha256=body_sha256,
            semantic_sha256=semantic_sha256,
        )
        if self.enabled and is_vicidial_lifecycle_event(envelope.event_type):
            # Run on both first acceptance and duplicate replay. If a process
            # stopped between durable inbox acceptance and projection, the
            # source's same-ID retry repairs the missing outbox row.
            await self.projector.ensure_projection(envelope)
        return result

    async def ready(self) -> bool:
        return await self.delegate.ready() and await self.projector.ready()

    async def close(self) -> None:
        await self.delegate.close()

    def __getattr__(self, name: str) -> Any:
        return getattr(self.delegate, name)


def wrap_postgres_inbox(
    inbox: PostgresInboxStore,
    *,
    enabled: bool,
) -> tuple[ProjectingInboxStore, PostgresCallProjectionStore]:
    projector = PostgresCallProjectionStore(inbox.pool)
    return ProjectingInboxStore(inbox, projector, enabled), projector
