"""Explicit Odoo/n8n integration gateway routes.

Existing event and callback routes remain the implementation of record; these
namespaces make the ownership boundary unambiguous. Command execution is
fail-closed until the approved Odoo adapter and live-write flag are enabled.
"""

from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.automation import canonical_hash, redact
from app.core.config import settings
from app.core.jwt_auth import JWTAuthError, KeycloakValidator
from app.db.models import (
    AuditEvent,
    IdempotencyRecord,
    IntegrationEvent,
    OdooResultDelivery,
)
from app.db.session import get_session

router = APIRouter(prefix="/api/v1/integrations", tags=["integrations"])


class CommandRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    command_id: str = Field(min_length=1, max_length=128)
    command_type: str = Field(min_length=1, max_length=128)
    payload: dict[str, Any] = Field(default_factory=dict)
    correlation_id: str = Field(min_length=1, max_length=128)
    trace_id: str = Field(min_length=1, max_length=128)
    idempotency_key: str = Field(min_length=1, max_length=256)


class CallbackResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    command_id: str = Field(min_length=1, max_length=128)
    status: str = Field(min_length=1, max_length=64)
    payload: dict[str, Any] = Field(default_factory=dict)
    correlation_id: str = Field(min_length=1, max_length=128)
    trace_id: str = Field(min_length=1, max_length=128)


class AutomationAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action_type: Literal[
        "CREATE_ACTIVITY", "CREATE_INTERNAL_SUMMARY", "CREATE_DRAFT",
        "SET_NEXT_ACTION", "CHANGE_STATUS", "SEND_EMAIL", "SEND_SMS",
    ]
    entity_type: str = Field(min_length=1, max_length=128)
    entity_id: str = Field(min_length=1, max_length=128)
    values: dict[str, Any] = Field(default_factory=dict)


class AutomationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_id: str = Field(min_length=1, max_length=128)
    correlation_id: str = Field(min_length=1, max_length=128)
    idempotency_key: str = Field(min_length=1, max_length=255)
    workflow_key: str = Field(min_length=1, max_length=128)
    execution_id: str = Field(min_length=1, max_length=128)
    status: Literal["COMPLETED", "FAILED", "RETRY"]
    actions: list[AutomationAction] = Field(default_factory=list, max_length=100)
    completed_at: datetime


ODOO_CAMPAIGN_ACTION_TYPES = frozenset({
    "CREATE_INTERNAL_SUMMARY", "SET_NEXT_ACTION", "CHANGE_STATUS",
})


def _require_replay_headers(timestamp: str | None, nonce: str | None, signature: str | None) -> None:
    if not timestamp or not nonce or not signature:
        raise HTTPException(401, "timestamp, nonce, and signature are required")
    try:
        if abs(datetime.now(timezone.utc).timestamp() - float(timestamp)) > settings.signature_ttl_seconds:
            raise HTTPException(401, "request timestamp expired")
    except ValueError as exc:
        raise HTTPException(401, "request timestamp invalid") from exc


def _scope_values(claims: dict[str, Any], plural: str, singular: str) -> set[str]:
    values = claims.get(plural, claims.get(singular, []))
    if isinstance(values, str):
        return {item for item in values.replace(",", " ").split() if item}
    return {str(item) for item in values or []}


def _authenticate_n8n(authorization: str, required_scope: str) -> dict[str, Any]:
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "bearer token required")
    try:
        return KeycloakValidator(
            issuer=settings.n8n_service_issuer,
            audience=settings.n8n_service_audience,
            jwks_url=settings.n8n_service_jwks_url,
            authorized_parties=frozenset({settings.n8n_campaign_service_client_id}),
            required_scopes=frozenset({required_scope}),
            required_environment="production",
        ).validate(authorization.removeprefix("Bearer ").strip())
    except JWTAuthError as exc:
        raise HTTPException(401, str(exc)) from exc


@router.get("/odoo/health")
async def odoo_health() -> dict[str, str]:
    return {"status": "ok", "gateway": "codestra-middleware", "provider": "odoo"}


@router.get("/odoo/readiness")
async def odoo_readiness() -> dict[str, str]:
    return {"status": "ready" if settings.auth_ready else "not-ready", "provider": "odoo"}


@router.post("/odoo/commands", status_code=202)
async def odoo_command(
    body: CommandRequest,
    x_timestamp: str | None = Header(None, alias="X-Timestamp"),
    x_nonce: str | None = Header(None, alias="X-Nonce"),
    x_signature: str | None = Header(None, alias="X-Signature"),
) -> dict[str, str]:
    _require_replay_headers(x_timestamp, x_nonce, x_signature)
    if not settings.odoo_automation_writes_enabled:
        raise HTTPException(503, "Odoo automation writes are disabled")
    return {"command_id": body.command_id, "status": "queued"}


@router.get("/odoo/commands/{command_id}")
async def odoo_command_status(command_id: str) -> dict[str, str]:
    return {"command_id": command_id, "status": "not_configured"}


@router.post("/n8n/dispatch", status_code=202)
async def n8n_dispatch(
    body: CommandRequest,
    x_timestamp: str | None = Header(None, alias="X-Timestamp"),
    x_nonce: str | None = Header(None, alias="X-Nonce"),
    x_signature: str | None = Header(None, alias="X-Signature"),
) -> dict[str, str]:
    _require_replay_headers(x_timestamp, x_nonce, x_signature)
    if not settings.n8n_event_delivery_enabled:
        raise HTTPException(503, "n8n delivery is disabled")
    return {"command_id": body.command_id, "status": "queued"}


@router.post("/n8n/results", status_code=202)
async def n8n_result(
    body: dict[str, Any],
    authorization: str = Header(alias="Authorization"),
    idempotency_key: str = Header(alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    if "event_id" in body:
        result = AutomationResult.model_validate(body)
        claims = _authenticate_n8n(authorization, "n8n.results.submit")
        if idempotency_key != result.idempotency_key:
            raise HTTPException(409, "idempotency binding conflict")
        event = await db.scalar(
            select(IntegrationEvent).where(
                IntegrationEvent.original_event_id == result.event_id
            )
        )
        envelope = event.payload_json if event else {}
        if (
            event is None
            or event.correlation_id != result.correlation_id
            or event.idempotency_key != result.idempotency_key
            or envelope.get("event_id") != result.event_id
            or envelope.get("campaign_id") not in _scope_values(claims, "campaigns", "campaign_scope")
            or envelope.get("business_unit_id") not in _scope_values(claims, "business_units", "business_unit_scope")
        ):
            raise HTTPException(409, "automation result source binding mismatch")
        if result.actions:
            unavailable = sorted({
                action.action_type for action in result.actions
                if action.action_type not in ODOO_CAMPAIGN_ACTION_TYPES
            })
            if unavailable:
                raise HTTPException(
                    503,
                    "automation action adapter is not production enabled: "
                    + ",".join(unavailable),
                )
            if not settings.odoo_automation_writes_enabled:
                raise HTTPException(503, "Odoo automation writes are disabled")
        scope = "n8n-standard-result"
        key_hash = canonical_hash({"idempotency_key": result.idempotency_key})
        request_hash = canonical_hash(redact(result.model_dump(mode="json")))
        await db.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:scope, 0))"),
            {"scope": f"{scope}:{key_hash}"},
        )
        prior = await db.scalar(select(IdempotencyRecord).where(
            IdempotencyRecord.scope == scope,
            IdempotencyRecord.key_hash == key_hash,
        ))
        response = {"accepted": "true", "event_id": result.event_id, "status": result.status}
        if prior:
            if prior.request_hash != request_hash:
                await db.rollback()
                raise HTTPException(409, "automation result idempotency conflict")
            await db.commit()
            return response
        db.add(IdempotencyRecord(
            scope=scope, key_hash=key_hash, request_hash=request_hash,
            response=response, status_code=202, event_id=event.id,
        ))
        if result.actions:
            db.add(OdooResultDelivery(
                integration_event_id=event.id,
                originating_outbox_public_id=result.event_id,
                request_hash=request_hash,
                status="PENDING",
                standard_result_json=result.model_dump(mode="json"),
            ))
        db.add(AuditEvent(
            action="n8n.standard_result.accepted", subject=result.event_id,
            correlation_id=result.correlation_id, decision=result.status,
            redacted_payload={"workflow_key": result.workflow_key, "execution_id": result.execution_id},
        ))
        await db.commit()
        return response
    CallbackResult.model_validate(body)
    raise HTTPException(410, "legacy unauthenticated callbacks are retired")


@router.post("/n8n/progress", status_code=202)
async def n8n_progress(body: CallbackResult) -> dict[str, str]:
    return {"accepted": "true", "command_id": body.command_id, "status": body.status}


@router.post("/n8n/dead-letter", status_code=202)
async def n8n_dead_letter(body: CallbackResult) -> dict[str, str]:
    return {"accepted": "true", "command_id": body.command_id, "status": body.status}


@router.post("/n8n/errors", status_code=202)
async def n8n_error(body: CallbackResult) -> dict[str, str]:
    return {"accepted": "true", "command_id": body.command_id, "status": body.status}


@router.post("/n8n/reconciliation", status_code=202)
async def n8n_reconciliation(body: CommandRequest) -> dict[str, str]:
    return {"accepted": "true", "command_id": body.command_id, "status": "recorded"}
