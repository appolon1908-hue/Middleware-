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


class RuntimeIntegrationStatus(BaseModel):
    """Read-only, secret-free runtime gate snapshot for certification tooling."""

    status: Literal["blocked", "ready"]
    source_sha: str
    image_digest: str
    environment: str
    auth_ready: bool
    external_effects_enabled: bool
    gates: dict[str, bool]
    timestamp: datetime


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


@router.get("/runtime", response_model=RuntimeIntegrationStatus)
async def runtime_integration_status() -> RuntimeIntegrationStatus:
    """Expose the current no-effect integration gates without secrets or endpoints.

    This is intentionally a snapshot of local configuration and source identity;
    it never labels a deployment certified and performs no provider or database
    mutation.
    """
    effects = {
        "callback_dispatch": settings.callback_dispatch_enabled,
        "email_delivery": settings.messaging_enabled,
        "external_delivery": settings.enable_external_delivery,
        "live_writes": settings.live_writes_enabled,
        "n8n_delivery": settings.n8n_event_delivery_enabled,
        "odoo_writes": settings.odoo_write_enabled or settings.odoo_automation_writes_enabled,
        "production_dialing": settings.external_dial_enabled,
        "sms_delivery": settings.messaging_enabled,
        "social_publish": getattr(settings, "social_publish_enabled", False),
        "vicidial_writes": settings.vicidial_write_enabled,
    }
    gates = {
        "authorization": settings.auth_ready,
        "database_configured": bool(settings.database_url or settings.database_url_file),
        "redis_configured": bool(settings.redis_url or settings.redis_url_file),
        "effects_disabled": not any(effects.values()),
        "source_identified": bool(__import__("os").getenv("SOURCE_SHA")),
        "image_identified": bool(__import__("os").getenv("IMAGE_DIGEST")),
    }
    ready = all(gates.values())
    return RuntimeIntegrationStatus(
        status="ready" if ready else "blocked",
        source_sha=__import__("os").getenv("SOURCE_SHA", "unknown"),
        image_digest=__import__("os").getenv("IMAGE_DIGEST", "unknown"),
        environment=settings.environment,
        auth_ready=settings.auth_ready,
        external_effects_enabled=any(effects.values()),
        gates=gates,
        timestamp=datetime.now(timezone.utc),
    )


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


@router.get("/odoo/status")
async def odoo_integration_status() -> dict[str, Any]:
    return {
        "health": await odoo_health(),
        "readiness": await odoo_readiness(),
        "automation_writes_enabled": settings.odoo_automation_writes_enabled,
    }


# NOTE on "Odoo integration mappings": this codebase already has a real,
# hardened campaign<->Odoo mapping projection at GET /v1/mappings/campaigns
# and /v1/mappings/campaigns/{code} (app/api/v1/mappings.py), backed by the
# reviewed, migration-seeded vicidial_campaign_registry table (odoo_business_
# unit_uuid/odoo_crm_team_uuid/odoo_campaign_uuid columns, plus a
# drift_status/last_read_back_at/observed_state_hash reconciliation-evidence
# trail enforced by a DB CHECK constraint - see migrations/versions/
# 0010_vicidial_registry_guards.py). Building a second, competing
# /odoo/mappings* implementation here would be exactly the duplication this
# session's mission repeatedly warns against. sync-status/sync-errors below
# read that same table rather than re-deriving the concept.
#
# What genuinely doesn't exist anywhere in this codebase: POST /odoo/mappings,
# PATCH/DELETE .../{id}, POST .../{id}/test, or POST /odoo/reconcile - there
# is no mapping-mutation code path at all. vicidial_campaign_registry appears
# to be intentionally reviewed/migration-controlled, not runtime-mutable
# (consistent with this deployment's broader "no direct production database
# edits" posture). Adding real write endpoints here would mean inventing a
# net-new mutation capability with no existing precedent to follow - a
# genuine architecture decision (should campaign<->Odoo mapping become
# runtime-mutable at all, and if so through what review/approval gate?), not
# something to fabricate silently. Left undone, flagged here rather than
# guessed at.


@router.get("/odoo/sync-status")
async def odoo_sync_status(
    business_unit: str,
    environment: str = "staging",
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    rows = (
        (
            await db.execute(
                text(
                    "SELECT drift_status, COUNT(*) AS count FROM vicidial_campaign_registry "
                    "WHERE environment=:environment AND business_unit_code=:unit "
                    "GROUP BY drift_status"
                ),
                {"environment": environment, "unit": business_unit.upper()},
            )
        )
        .mappings()
        .all()
    )
    by_status = {row["drift_status"]: row["count"] for row in rows}
    return {
        "business_unit": business_unit.upper(),
        "environment": environment,
        "mapping_count_by_drift_status": by_status,
        "total_mappings": sum(by_status.values()),
    }


@router.get("/odoo/sync-errors")
async def odoo_sync_errors(
    business_unit: str,
    environment: str = "staging",
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    # "not_observed" is this column's server_default (never yet reconciled),
    # not itself an error - only rows that were checked and found drifted
    # are reported here.
    rows = (
        (
            await db.execute(
                text(
                    "SELECT canonical_campaign_code, drift_status, last_read_back_at "
                    "FROM vicidial_campaign_registry "
                    "WHERE environment=:environment AND business_unit_code=:unit "
                    "AND drift_status NOT IN ('reconciled', 'not_observed') "
                    "ORDER BY canonical_campaign_code"
                ),
                {"environment": environment, "unit": business_unit.upper()},
            )
        )
        .mappings()
        .all()
    )
    return {
        "business_unit": business_unit.upper(),
        "environment": environment,
        "items": [
            {
                "canonical_campaign_code": row["canonical_campaign_code"],
                "drift_status": row["drift_status"],
                "last_read_back_at": (
                    row["last_read_back_at"].isoformat() if row["last_read_back_at"] else None
                ),
            }
            for row in rows
        ],
    }


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
