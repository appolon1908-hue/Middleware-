"""Signed VICIdial and Telnexa compatibility webhook ingress."""

from __future__ import annotations

import hashlib
import hmac
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.odoo.webhooks import OdooWebhookAdapter
from app.core.config import settings
from app.db.models import (
    AuditEvent,
    IdempotencyRecord,
    IntegrationDelivery,
    IntegrationEvent,
    OdooResultDelivery,
    OutboxEvent,
)
from app.db.session import get_session


router = APIRouter(prefix="/webhooks", tags=["provider-webhooks"])

DISPOSITION_MAP = {
    "ANSWER": "answered",
    "NOANSWER": "no_answer",
    "BUSY": "busy",
    "SVUNREACH": "failed",
    "DONTCALL": "dnc",
    "CALLBK": "callback_requested",
    "VOICEMAIL": "voicemail",
    "SALE": "sale_completed",
    "DROP": "dropped",
    "NI": "not_interested",
}


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class VicidialCallResult(StrictModel):
    call_id: str = Field(min_length=1, max_length=128)
    phone_number: str = Field(pattern=r"^\+[1-9][0-9]{7,14}$")
    disposition: str
    call_time: int = Field(ge=0, le=86400)
    campaign_id: str = Field(min_length=1, max_length=128)
    comments: str | None = Field(default=None, max_length=2000)


class TelnexaInboundSms(StrictModel):
    message_id: str = Field(min_length=1, max_length=128)
    sender: str = Field(alias="from", pattern=r"^\+[1-9][0-9]{7,14}$")
    body: str = Field(min_length=1, max_length=10000)
    received_at: datetime


def _verify_signature(body: bytes, supplied: str | None, secret: str) -> None:
    if not secret:
        raise HTTPException(503, "webhook authentication is unavailable")
    candidate = (supplied or "").removeprefix("sha256=").lower()
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    if len(candidate) != 64 or not hmac.compare_digest(candidate, expected):
        raise HTTPException(403, "webhook signature is invalid")


def _parse(model: type[BaseModel], body: bytes) -> BaseModel:
    try:
        return model.model_validate_json(body)
    except (ValidationError, ValueError) as exc:
        raise HTTPException(400, "webhook payload is invalid") from exc


async def _persist(
    *,
    db: AsyncSession,
    response: Response,
    provider: str,
    external_id: str,
    event_type: str,
    entity_key: str,
    normalized: dict[str, Any],
    odoo_intent: dict[str, Any],
    body: bytes,
) -> dict[str, Any]:
    staging = getattr(settings, "environment", "") == "staging"
    write_enabled = settings.odoo_write_enabled or (
        staging and getattr(settings, "odoo_staging_writes_enabled", False)
    )
    original_event_id = f"{provider}:{external_id}"
    key_hash = hashlib.sha256(external_id.encode()).hexdigest()
    request_hash = hashlib.sha256(body).hexdigest()
    scope = f"provider-webhook:{provider}"
    correlation_id = original_event_id
    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:value, 0))"),
        {"value": f"{scope}:{key_hash}"},
    )
    existing = await db.scalar(
        select(IdempotencyRecord).where(
            IdempotencyRecord.scope == scope,
            IdempotencyRecord.key_hash == key_hash,
        )
    )
    if existing:
        if existing.request_hash != request_hash:
            await db.rollback()
            raise HTTPException(409, "idempotency key conflict")
        await db.commit()
        response.headers["X-Idempotent-Replay"] = "true"
        return dict(existing.response)

    incoming = IntegrationEvent(
        idempotency_key=key_hash,
        event_type=event_type,
        schema_version="1.0",
        original_event_id=original_event_id,
        entity_key=entity_key,
        source_system=provider,
        correlation_id=correlation_id,
        payload_json=normalized,
        payload_hash=request_hash,
        state="accepted",
    )
    db.add(incoming)
    await db.flush()
    db.add(
        IntegrationDelivery(
            event_id=incoming.id,
            target="odoo",
            status="pending" if write_enabled else "disabled",
            max_attempts=settings.outbox_max_attempts,
            result_json=odoo_intent,
        )
    )
    if write_enabled:
        db.add(
            OdooResultDelivery(
                integration_event_id=incoming.id,
                originating_outbox_public_id=original_event_id,
                request_hash=request_hash,
                status="PENDING",
                standard_result_json=odoo_intent,
            )
        )
    db.add(
        OutboxEvent(
            topic=event_type,
            payload={
                "event_id": original_event_id,
                "event_type": event_type,
                "source": provider,
                "data": normalized,
            },
            correlation_id=correlation_id,
            status="pending",
        )
    )
    result = {
        "accepted": True,
        "event_id": original_event_id,
        "duplicate": False,
        "odoo_write": "pending" if write_enabled else "disabled",
    }
    db.add(
        IdempotencyRecord(
            scope=scope,
            key_hash=key_hash,
            request_hash=request_hash,
            response=result,
            status_code=200,
            event_id=incoming.id,
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        )
    )
    db.add(
        AuditEvent(
            action=f"{provider}.webhook.accepted",
            subject=original_event_id,
            correlation_id=correlation_id,
            decision="accepted",
            redacted_payload={"event_type": event_type},
        )
    )
    try:
        await db.commit()
    except Exception as exc:
        await db.rollback()
        raise HTTPException(503, "durable persistence unavailable") from exc
    response.headers["X-Idempotent-Replay"] = "false"
    return result


@router.post("/vicidial/call-result/")
async def vicidial_call_result(
    request: Request,
    response: Response,
    signature: str | None = Header(default=None, alias="X-VICIdial-Signature"),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    body = await request.body()
    _verify_signature(body, signature, settings.vicidial_webhook_secret)
    value = _parse(VicidialCallResult, body)
    assert isinstance(value, VicidialCallResult)
    disposition = DISPOSITION_MAP.get(value.disposition.upper())
    if disposition is None:
        raise HTTPException(400, "VICIdial disposition is unsupported")
    payload = value.model_dump(mode="json")
    payload["disposition"] = disposition
    return await _persist(
        db=db,
        response=response,
        provider="vicidial",
        external_id=value.call_id,
        event_type="call_disposition_updated",
        entity_key=f"call_id:{value.call_id}",
        normalized=payload,
        odoo_intent=OdooWebhookAdapter.log_call_result(payload, disposition),
        body=body,
    )


@router.post("/sms/inbound/")
async def telnexa_inbound_sms(
    request: Request,
    response: Response,
    signature: str | None = Header(default=None, alias="X-Telnexa-Signature"),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    body = await request.body()
    _verify_signature(body, signature, settings.telnexa_webhook_secret)
    value = _parse(TelnexaInboundSms, body)
    assert isinstance(value, TelnexaInboundSms)
    payload = value.model_dump(mode="json", by_alias=True)
    return await _persist(
        db=db,
        response=response,
        provider="telnexa",
        external_id=value.message_id,
        event_type="sms_received",
        entity_key=f"phone:{value.sender}",
        normalized=payload,
        odoo_intent=OdooWebhookAdapter.log_inbound_sms(payload),
        body=body,
    )
