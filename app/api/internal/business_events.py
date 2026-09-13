"""Durable tenant-bound ingress for normalized Klyrow business facts."""
from datetime import date, datetime, timezone
import hashlib
import json
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import DateTime, JSON, String
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.core.config import settings
from app.core.jwt_auth import JWTAuthError, KeycloakValidator
from app.db.models import Base
from app.db.session import get_session

router = APIRouter(tags=["business-events"])


class BusinessEventInbox(Base):
    __tablename__ = "codestra_business_event_inbox"
    source: Mapped[str] = mapped_column(String(32), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(200), primary_key=True)
    event_id: Mapped[str] = mapped_column(String(200), primary_key=True)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    state: Mapped[str] = mapped_column(String(24), nullable=False, default="PENDING")
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class BusinessEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=200)
    type: Literal["klyrow.tenant.created", "klyrow.subscription.changed", "klyrow.email.accepted",
                  "klyrow.email.delivered", "klyrow.email.bounced", "klyrow.email.complained",
                  "klyrow.campaign.summary", "klyrow.usage.daily", "klyrow.kpi.daily",
                  "klyrow.domain.status", "klyrow.provider.health", "klyrow.account.held"]
    version: Literal[1]
    source: Literal["klyrow"]
    tenant_id: str = Field(min_length=1, max_length=200)
    correlation_id: str = Field(min_length=1, max_length=200)
    causation_id: str = Field(min_length=1, max_length=200)
    occurred_at: AwareDatetime
    data: dict


class DailyUsage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    date: date
    unit: Literal["accepted_message"]
    quantity: int = Field(ge=0)
    snapshot_at: AwareDatetime


class AcceptedEvent(BaseModel):
    operation_id: str
    status: Literal["ACCEPTED"] = "ACCEPTED"


def business_identity(authorization: str = Header(default="")) -> dict:
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "service_bearer_required")
    try:
        return KeycloakValidator(
            issuer=settings.keycloak_issuer, audience=settings.keycloak_audience,
            jwks_url=settings.keycloak_jwks_url,
            authorized_parties=frozenset({"klyrow-business-events"}),
            required_scopes=frozenset({"klyrow.events.write"}),
            required_environment=settings.environment,
        ).validate(authorization.removeprefix("Bearer "))
    except JWTAuthError as exc:
        raise HTTPException(401, "service_identity_rejected") from exc


async def persist_event(db: AsyncSession, event: BusinessEvent) -> AcceptedEvent:
    payload = event.model_dump(mode="json")
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    identity = {"source": event.source, "tenant_id": event.tenant_id, "event_id": event.id}
    existing = await db.get(BusinessEventInbox, identity)
    if existing is None:
        try:
            async with db.begin_nested():
                db.add(BusinessEventInbox(**identity, payload_hash=digest, payload=payload))
                await db.flush()
        except IntegrityError:
            existing = await db.get(BusinessEventInbox, identity)
            if existing is None:
                raise
    if existing is not None and existing.payload_hash != digest:
        raise HTTPException(409, "event_idempotency_conflict")
    await db.commit()
    # Include tenant/source in the operation ID: event IDs are tenant-scoped.
    key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    return AcceptedEvent(operation_id="op_"+key)


@router.post("/internal/v1/events/klyrow", status_code=202, response_model=AcceptedEvent,
             openapi_extra={"requestBody": {"required": True, "content": {
                 "application/json": {"schema": BusinessEvent.model_json_schema()}}}},
             responses={401: {"description": "Invalid workload identity"},
                        403: {"description": "Tenant scope denied"},
                        409: {"description": "Event content conflicts with prior ID"},
                        413: {"description": "Event exceeds 64 KiB"},
                        415: {"description": "JSON required"},
                        422: {"description": "Invalid normalized event"},
                        503: {"description": "Durable store unavailable"}})
async def receive_business_event(request: Request, claims: dict=Depends(business_identity),
                                 db: AsyncSession=Depends(get_session),
                                 idempotency_key: str = Header(default="", alias="Idempotency-Key", max_length=200),
                                 correlation_id: str = Header(default="", alias="X-Correlation-Id", max_length=200)) -> AcceptedEvent:
    if request.headers.get("content-type", "").split(";", 1)[0].lower() != "application/json":
        raise HTTPException(415, "application_json_required")
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > 65536:
            raise HTTPException(413, "business_event_too_large")
    try:
        event = BusinessEvent.model_validate_json(body)
        if event.type == "klyrow.usage.daily":
            DailyUsage.model_validate(event.data)
    except ValidationError as exc:
        raise HTTPException(422, "invalid_business_event") from exc
    scopes = set(str(claims.get("scope", "")).split())
    if claims.get("tenant_id") != event.tenant_id and "klyrow.events.write:any-tenant" not in scopes:
        raise HTTPException(403, "event_tenant_denied")
    if idempotency_key != event.id or correlation_id != event.correlation_id:
        raise HTTPException(409, "event_header_binding_mismatch")
    from sqlalchemy.exc import SQLAlchemyError
    try:
        return await persist_event(db, event)
    except SQLAlchemyError as exc:
        await db.rollback()
        raise HTTPException(503, "business_event_store_unavailable") from exc
