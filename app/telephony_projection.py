from __future__ import annotations

import hashlib
import hmac
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal
from urllib.parse import quote, urlsplit

import asyncpg
import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from .models import EventEnvelope
from .storage import (
    DEFAULT_MAX_OUTBOX_ATTEMPTS,
    OutboxRecord,
    PostgresOutboxStore,
)
from .worker import KnownSafeRetryError


ODOO_CALL_EVENT_DESTINATION = "odoo-call-event"
ODOO_CALL_EVENT_OUTBOX_TYPE = "odoo.call-event.project.v1"
ODOO_CALL_EVENT_PATH = "/codestra/api/v1/call-events"

MIDDLEWARE_TO_ODOO_EVENT: dict[str, str] = {
    "codestra.vicidial.call.lifecycle.created": "call.created",
    "codestra.vicidial.call.lifecycle.offered": "call.offered",
    "codestra.vicidial.call.lifecycle.ringing": "call.ringing",
    "codestra.vicidial.call.lifecycle.answered": "call.answered",
    "codestra.vicidial.call.lifecycle.connected": "call.connected",
    "codestra.vicidial.call.lifecycle.held": "call.held",
    "codestra.vicidial.call.lifecycle.resumed": "call.resumed",
    "codestra.vicidial.call.lifecycle.transfer.started": "call.transfer.started",
    "codestra.vicidial.call.lifecycle.transfer.completed": "call.transfer.completed",
    "codestra.vicidial.call.lifecycle.hangup": "call.hangup",
    "codestra.vicidial.call.lifecycle.completed": "call.completed",
    "codestra.vicidial.call.lifecycle.ended": "call.ended",
    "codestra.vicidial.call.lifecycle.failed": "call.failed",
    "codestra.vicidial.call.lifecycle.missed": "call.missed",
    "codestra.vicidial.call.lifecycle.recording.available": "call.recording_available",
    "codestra.vicidial.call.lifecycle.disposition.required": "call.disposition_required",
}
VICIDIAL_LIFECYCLE_EVENT_TYPES = frozenset(MIDDLEWARE_TO_ODOO_EVENT)

ODOO_EVENT_STATE: dict[str, str | None] = {
    "call.created": "new",
    "call.offered": "offered",
    "call.ringing": "ringing",
    "call.answered": "answering",
    "call.connected": "connected",
    "call.held": "held",
    "call.resumed": "connected",
    "call.transfer.started": "transferring",
    "call.transfer.completed": "transferred",
    "call.hangup": "ending",
    "call.completed": "completed",
    "call.ended": "completed",
    "call.failed": "failed",
    "call.missed": "missed",
    "call.recording_available": None,
    "call.disposition_required": None,
}

_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z0-9._:-]+$")
_EVENT_ID = re.compile(r"^[A-Za-z0-9._-]+$")
_E164 = re.compile(r"^\+[1-9][0-9]{7,14}$")
_RECONCILABLE_STATUSES = frozenset({408, 425, 429, 500, 502, 503, 504})


class TelephonyProjectionError(RuntimeError):
    """The accepted VICIdial event cannot be projected safely to Odoo."""


class VicidialLifecyclePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"]
    business_unit_id: str = Field(min_length=1, max_length=255)
    campaign_id: str = Field(min_length=1, max_length=255)
    call_id: str = Field(min_length=1, max_length=255)
    asterisk_uniqueid: str = Field(min_length=1, max_length=255)
    linkedid: str = Field(min_length=1, max_length=255)
    agent_id: str = Field(min_length=1, max_length=255)
    extension: str = Field(min_length=1, max_length=255)
    keycloak_subject: str = Field(min_length=1, max_length=255)
    sequence: int = Field(ge=0)
    direction: Literal["inbound", "outbound"]
    caller_number: str | None = Field(default=None, max_length=32)
    destination_number: str | None = Field(default=None, max_length=32)
    duration: int | None = Field(default=None, ge=0, le=86400)
    talk_duration: int | None = Field(default=None, ge=0, le=86400)
    hangup_cause: str | None = Field(default=None, max_length=128)
    hangup_cause_code: int | None = Field(default=None, ge=0, le=65535)
    transfer_destination: str | None = Field(default=None, max_length=255)
    transfer_type: Literal["blind", "attended"] | None = None
    recording_id: str | None = Field(default=None, max_length=255)
    recording_reference: str | None = Field(default=None, max_length=1024)

    @field_validator(
        "business_unit_id",
        "campaign_id",
        "call_id",
        "asterisk_uniqueid",
        "linkedid",
        "agent_id",
        "extension",
        "keycloak_subject",
    )
    @classmethod
    def identifiers_are_bounded_and_canonical(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized or not _SAFE_IDENTIFIER.fullmatch(normalized):
            raise ValueError("telephony identifiers must use the canonical safe character set")
        return normalized

    @field_validator("caller_number", "destination_number")
    @classmethod
    def phone_numbers_are_e164(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not _E164.fullmatch(normalized):
            raise ValueError("telephony phone numbers must be E.164")
        return normalized

    @field_validator("hangup_cause", "transfer_destination", "recording_id", "recording_reference")
    @classmethod
    def optional_text_is_clean(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized or any(ord(char) < 32 for char in normalized):
            raise ValueError("telephony metadata contains invalid control characters")
        return normalized


class OdooCallEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"]
    event_id: str = Field(min_length=1, max_length=255)
    event_type: str
    timestamp: datetime
    correlation_id: str = Field(min_length=1, max_length=255)
    tenant_id: str = Field(min_length=1, max_length=255)
    business_unit_id: str = Field(min_length=1, max_length=255)
    campaign_id: str = Field(min_length=1, max_length=255)
    call_id: str = Field(min_length=1, max_length=255)
    asterisk_uniqueid: str = Field(min_length=1, max_length=255)
    linkedid: str = Field(min_length=1, max_length=255)
    agent_id: str = Field(min_length=1, max_length=255)
    extension: str = Field(min_length=1, max_length=255)
    sequence: int = Field(ge=0)
    keycloak_subject: str = Field(min_length=1, max_length=255)
    direction: Literal["inbound", "outbound"]
    caller_number: str | None = Field(default=None, max_length=32)
    destination_number: str | None = Field(default=None, max_length=32)
    duration: int | None = Field(default=None, ge=0, le=86400)
    talk_duration: int | None = Field(default=None, ge=0, le=86400)
    hangup_cause: str | None = Field(default=None, max_length=128)
    hangup_cause_code: int | None = Field(default=None, ge=0, le=65535)
    transfer_destination: str | None = Field(default=None, max_length=255)
    transfer_type: Literal["blind", "attended"] | None = None
    recording_id: str | None = Field(default=None, max_length=255)
    recording_reference: str | None = Field(default=None, max_length=1024)
    source: Literal["middleware"] = "middleware"

    @field_validator("event_id")
    @classmethod
    def event_id_is_url_safe(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized or not _EVENT_ID.fullmatch(normalized):
            raise ValueError("Odoo call-event ID must be URL-safe")
        return normalized

    @field_validator(
        "correlation_id",
        "tenant_id",
        "business_unit_id",
        "campaign_id",
        "call_id",
        "asterisk_uniqueid",
        "linkedid",
        "agent_id",
        "extension",
        "keycloak_subject",
    )
    @classmethod
    def identifiers_are_safe(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized or not _SAFE_IDENTIFIER.fullmatch(normalized):
            raise ValueError("Odoo call-event identifiers are not canonical")
        return normalized

    @field_validator("event_type")
    @classmethod
    def event_type_is_supported(cls, value: str) -> str:
        if value not in ODOO_EVENT_STATE:
            raise ValueError("Odoo call-event type is unsupported")
        return value


def build_odoo_call_event(event: EventEnvelope) -> dict[str, Any]:
    if event.source != "vicidial-adapter":
        raise TelephonyProjectionError("telephony lifecycle source must be vicidial-adapter")
    target_type = MIDDLEWARE_TO_ODOO_EVENT.get(event.event_type)
    if target_type is None:
        raise TelephonyProjectionError("event is not a projectable VICIdial lifecycle event")
    try:
        source = VicidialLifecyclePayload.model_validate(event.payload)
    except ValidationError as exc:
        raise TelephonyProjectionError("VICIdial lifecycle payload is invalid") from exc

    if target_type == "call.recording_available" and not source.recording_id:
        raise TelephonyProjectionError("recording availability requires recording_id")
    if target_type == "call.transfer.completed" and not source.transfer_destination:
        raise TelephonyProjectionError("completed transfer requires transfer_destination")
    if target_type == "call.transfer.completed" and not source.transfer_type:
        raise TelephonyProjectionError("completed transfer requires transfer_type")

    payload = source.model_dump(exclude_none=True)
    payload.update(
        {
            "event_id": event.event_id,
            "event_type": target_type,
            "timestamp": event.occurred_at.astimezone(timezone.utc),
            "correlation_id": event.correlation_id,
            "tenant_id": event.tenant_id,
            "source": "middleware",
        }
    )
    try:
        normalized = OdooCallEvent.model_validate(payload)
    except ValidationError as exc:
        raise TelephonyProjectionError("normalized Odoo call event is invalid") from exc
    return normalized.model_dump(mode="json", exclude_none=True)


def odoo_payload_hash(payload: dict[str, Any]) -> str:
    """Match the semantic hash produced by Odoo apply_authoritative_event()."""
    try:
        event = OdooCallEvent.model_validate(payload)
    except ValidationError as exc:
        raise TelephonyProjectionError("Odoo call event cannot be hashed") from exc
    normalized = event.model_dump(mode="json", exclude_none=True)
    timestamp = event.timestamp.astimezone(timezone.utc).replace(
        tzinfo=None,
        microsecond=0,
    )
    normalized["timestamp"] = timestamp.strftime("%Y-%m-%d %H:%M:%S")
    normalized["state"] = ODOO_EVENT_STATE[event.event_type]
    raw = json.dumps(
        normalized,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _json_object(value: object) -> dict[str, Any]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError as exc:
            raise TelephonyProjectionError("persisted telephony payload is invalid JSON") from exc
    if not isinstance(value, dict):
        raise TelephonyProjectionError("persisted telephony payload must be an object")
    return dict(value)


def _safe_error(exc: Exception) -> str:
    return (exc.__class__.__name__ + ": " + str(exc))[:1024]


class PostgresTelephonyProjectionStore:
    """Turn accepted VICIdial lifecycle events into durable Odoo outbox rows."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    async def project_once(self) -> bool:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    """
                    SELECT event_id, tenant_id, event_type, payload
                    FROM middleware_inbox
                    WHERE source_client_id='vicidial-adapter'
                      AND event_type=ANY($1::text[])
                      AND status='accepted'
                      AND quarantined_at IS NULL
                      AND discarded_at IS NULL
                      AND (
                            processed_at IS NULL
                            OR (
                                reprocess_requested_at IS NOT NULL
                                AND reprocess_requested_at > processed_at
                            )
                      )
                    ORDER BY received_at, event_id
                    FOR UPDATE SKIP LOCKED
                    LIMIT 1
                    """,
                    sorted(VICIDIAL_LIFECYCLE_EVENT_TYPES),
                )
                if row is None:
                    return False

                try:
                    envelope = EventEnvelope.model_validate(_json_object(row["payload"]))
                    if envelope.event_id != row["event_id"]:
                        raise TelephonyProjectionError("persisted event identity mismatch")
                    if envelope.tenant_id != row["tenant_id"]:
                        raise TelephonyProjectionError("persisted tenant identity mismatch")
                    if envelope.event_type != row["event_type"]:
                        raise TelephonyProjectionError("persisted event type mismatch")
                    projection = build_odoo_call_event(envelope)
                    projection_json = json.dumps(
                        projection,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                    idempotency_key = "odoo-call-event:" + envelope.event_id
                    inserted = await conn.fetchrow(
                        """
                        INSERT INTO middleware_outbox (
                            tenant_id, destination, event_type, payload,
                            idempotency_key
                        ) VALUES ($1,$2,$3,$4::jsonb,$5)
                        ON CONFLICT (tenant_id, destination, idempotency_key)
                        DO NOTHING
                        RETURNING id
                        """,
                        envelope.tenant_id,
                        ODOO_CALL_EVENT_DESTINATION,
                        ODOO_CALL_EVENT_OUTBOX_TYPE,
                        projection_json,
                        idempotency_key,
                    )
                    if inserted is None:
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
                            idempotency_key,
                        )
                        if existing is None:
                            raise TelephonyProjectionError(
                                "Odoo call-event outbox conflict could not be reconciled"
                            )
                        if (
                            existing["event_type"] != ODOO_CALL_EVENT_OUTBOX_TYPE
                            or _json_object(existing["payload"]) != projection
                        ):
                            raise TelephonyProjectionError(
                                "Odoo call-event idempotency conflict"
                            )
                except Exception as exc:
                    await conn.execute(
                        """
                        UPDATE middleware_inbox
                        SET status='rejected',
                            processed_at=now(),
                            last_error=$3,
                            resource_version=resource_version+1
                        WHERE tenant_id=$1 AND event_id=$2
                        """,
                        row["tenant_id"],
                        row["event_id"],
                        _safe_error(exc),
                    )
                    return True

                await conn.execute(
                    """
                    UPDATE middleware_inbox
                    SET status='validated',
                        processed_at=now(),
                        reprocess_requested_at=NULL,
                        last_error=NULL,
                        resource_version=resource_version+1
                    WHERE tenant_id=$1 AND event_id=$2
                    """,
                    row["tenant_id"],
                    row["event_id"],
                )
                return True


class TelephonyOutboxStore(PostgresOutboxStore):
    """Lease only call-event rows so disabled transports remain untouched."""

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
                    WHERE destination=$2
                      AND completed_at IS NULL
                      AND cancelled_at IS NULL
                      AND dead_lettered_at IS NULL
                      AND reconciliation_required_at IS NULL
                      AND attempt_count >= $1
                      AND (lease_until IS NULL OR lease_until < now())
                    """,
                    max_attempts,
                    ODOO_CALL_EVENT_DESTINATION,
                )
                row = await conn.fetchrow(
                    """
                    WITH candidate AS (
                        SELECT id
                        FROM middleware_outbox
                        WHERE destination=$4
                          AND completed_at IS NULL
                          AND cancelled_at IS NULL
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
                    ODOO_CALL_EVENT_DESTINATION,
                )
                if row:
                    await conn.execute(
                        """
                        INSERT INTO middleware_outbox_attempt_events(
                            outbox_id, tenant_id, attempt_number, event_type, worker_id
                        ) VALUES($1,$2,$3,'claimed',$4)
                        """,
                        row["id"],
                        row["tenant_id"],
                        row["attempt_count"],
                        worker_id,
                    )
        if not row:
            return None
        return OutboxRecord(
            id=row["id"],
            tenant_id=row["tenant_id"],
            destination=row["destination"],
            event_type=row["event_type"],
            idempotency_key=row["idempotency_key"],
            payload=_json_object(row["payload"]),
            attempt_count=row["attempt_count"],
        )


@dataclass(slots=True)
class OdooCallEventDispatcher:
    client: httpx.AsyncClient
    base_url: str
    default_secret: bytes
    tenant_secrets: dict[str, bytes]

    def __post_init__(self) -> None:
        parsed = urlsplit(self.base_url)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("Odoo call-event base URL must be an HTTPS origin")
        self.base_url = self.base_url.rstrip("/")

    def _secret(self, tenant_id: str) -> bytes:
        # The current Odoo call-event receiver uses one deployment-managed
        # secret.  A tenant override is accepted only when no default exists.
        secret = self.default_secret or self.tenant_secrets.get(tenant_id, b"")
        if len(secret) < 32:
            raise TelephonyProjectionError(
                "Odoo call-event HMAC secret must contain at least 32 bytes"
            )
        return secret

    @staticmethod
    def _post_signature(secret: bytes, timestamp: str, body: bytes) -> str:
        return hmac.new(
            secret,
            timestamp.encode("ascii") + b"." + body,
            hashlib.sha256,
        ).hexdigest()

    @staticmethod
    def _readback_signature(
        secret: bytes,
        timestamp: str,
        path: str,
        event_id: str,
        tenant_id: str,
    ) -> str:
        canonical = "\n".join(
            (
                "v2",
                "GET",
                path,
                timestamp,
                event_id,
                tenant_id,
                hashlib.sha256(b"").hexdigest(),
            )
        ).encode("utf-8")
        return "sha256=" + hmac.new(secret, canonical, hashlib.sha256).hexdigest()

    async def __call__(self, record: OutboxRecord) -> None:
        if record.destination != ODOO_CALL_EVENT_DESTINATION:
            raise TelephonyProjectionError("outbox destination is not Odoo call events")
        if record.event_type != ODOO_CALL_EVENT_OUTBOX_TYPE:
            raise TelephonyProjectionError("outbox type is not an Odoo call event")
        try:
            event = OdooCallEvent.model_validate(record.payload)
        except ValidationError as exc:
            raise TelephonyProjectionError("outbox call-event payload is invalid") from exc
        if event.tenant_id != record.tenant_id:
            raise TelephonyProjectionError("outbox and call-event tenant mismatch")
        if record.idempotency_key != "odoo-call-event:" + event.event_id:
            raise TelephonyProjectionError("outbox call-event idempotency mismatch")

        payload = event.model_dump(mode="json", exclude_none=True)
        body = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        timestamp = str(int(datetime.now(timezone.utc).timestamp()))
        secret = self._secret(record.tenant_id)
        headers = {
            "Content-Type": "application/json",
            "X-Codestra-Timestamp": timestamp,
            "X-Codestra-Signature": self._post_signature(secret, timestamp, body),
            "X-Codestra-Event-ID": event.event_id,
            "X-Codestra-Tenant-ID": event.tenant_id,
            "X-Correlation-ID": event.correlation_id,
        }

        try:
            response = await self.client.post(
                self.base_url + ODOO_CALL_EVENT_PATH,
                content=body,
                headers=headers,
            )
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            raise KnownSafeRetryError(
                "Odoo call-event connection was not established"
            ) from exc
        except httpx.RequestError:
            await self._readback(event, payload, secret)
            return

        if response.status_code in {200, 202}:
            self._validate_post_response(response, event)
            return
        if response.status_code in _RECONCILABLE_STATUSES:
            await self._readback(event, payload, secret)
            return
        raise TelephonyProjectionError(
            f"Odoo call-event delivery failed with HTTP {response.status_code}"
        )

    @staticmethod
    def _validate_post_response(
        response: httpx.Response,
        event: OdooCallEvent,
    ) -> None:
        try:
            value = response.json()
        except ValueError as exc:
            raise TelephonyProjectionError(
                "Odoo call-event response is not JSON"
            ) from exc
        if not isinstance(value, dict):
            raise TelephonyProjectionError("Odoo call-event response must be an object")
        if value.get("call_id") != event.call_id:
            raise TelephonyProjectionError("Odoo call-event response identity mismatch")
        if value.get("state") not in set(ODOO_EVENT_STATE.values()):
            raise TelephonyProjectionError("Odoo call-event response state is invalid")
        if value.get("duplicate") not in {True, False}:
            raise TelephonyProjectionError(
                "Odoo call-event response duplicate marker is missing"
            )

    async def _readback(
        self,
        event: OdooCallEvent,
        payload: dict[str, Any],
        secret: bytes,
    ) -> None:
        encoded_event_id = quote(event.event_id, safe="")
        path = ODOO_CALL_EVENT_PATH + "/" + encoded_event_id
        timestamp = str(int(datetime.now(timezone.utc).timestamp()))
        headers = {
            "X-Codestra-Timestamp": timestamp,
            "X-Codestra-Signature": self._readback_signature(
                secret,
                timestamp,
                path,
                event.event_id,
                event.tenant_id,
            ),
            "X-Codestra-Signature-Version": "v2",
            "X-Codestra-Event-ID": event.event_id,
            "X-Codestra-Tenant-ID": event.tenant_id,
            "X-Correlation-ID": event.correlation_id,
        }
        try:
            response = await self.client.get(self.base_url + path, headers=headers)
        except httpx.RequestError as exc:
            raise TelephonyProjectionError(
                "Odoo call-event outcome remains unknown"
            ) from exc
        if response.status_code == 404:
            raise KnownSafeRetryError(
                "Odoo readback proves the call event was not persisted"
            )
        if response.status_code != 200:
            raise TelephonyProjectionError(
                f"Odoo call-event readback failed with HTTP {response.status_code}"
            )
        try:
            evidence = response.json()
        except ValueError as exc:
            raise TelephonyProjectionError(
                "Odoo call-event readback is not JSON"
            ) from exc
        expected = {
            "event_id": event.event_id,
            "tenant_id": event.tenant_id,
            "call_id": event.call_id,
            "event_type": event.event_type,
            "sequence": event.sequence,
            "processing_state": "processed",
            "payload_hash": odoo_payload_hash(payload),
        }
        if not isinstance(evidence, dict) or any(
            evidence.get(key) != value for key, value in expected.items()
        ):
            raise TelephonyProjectionError(
                "Odoo call-event readback does not match the durable intent"
            )
