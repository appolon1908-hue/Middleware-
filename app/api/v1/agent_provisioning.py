"""Mission 3: the agent provisioning saga orchestrator.

Odoo sends exactly one command to ``POST .../requests``; this module owns
every subsequent step. Odoo never calls Keycloak, VICIdial, Klyrow, or
Telnexa directly, and never receives Keycloak admin credentials - it only
ever sees this API's saga state and step history.

Path note: this deliberately does NOT live under the existing
``/platform/v1/provisioning/requests`` path (``app.api.v1.platform``). That
path is already a real, tested, and migrated feature - the canonical
service/infrastructure catalog's review-gated provisioning workflow
(``platform_services`` / ``platform_provisioning_requests`` /
``ProvisioningCreate`` with ``manifest_sha256``/``git_sha``/
``requested_components``) - an entirely different domain (onboarding
*microservices* into the platform, not provisioning *people*). Reusing that
path for this schema would collide with a live feature, so this router is
mounted at ``/platform/v1/agent-provisioning`` instead.

Every mutating saga step is fail-closed behind
``settings.live_identity_provisioning_enabled`` (Keycloak) and
``settings.vicidial_write_enabled``/``settings.live_writes_enabled``
(VICIdial channel adapter), matching this codebase's existing
default-closed posture (see ``app.api.v1.telephony._fail_closed_action``
for the same idiom).

CHANNEL_PROVISIONING now provisions phone/webrtc for real through
``app.adapters.vicidial.mtls_client`` (sync_agent -> reserve or adopt an
extension -> provision_webrtc if requested). sms/email still have no
account-provisioning adapter anywhere in this repository - only message
sending exists (``app.telnexa_provider_adapter``,
``app.klyrow_email_adapter``) - so those two channels are still recorded
as blocked, and the saga reports PARTIAL rather than claiming a channel
is live when it is not.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.keycloak.lifecycle_client import (
    KeycloakLifecycleAdapter,
    KeycloakLifecycleDisabled,
    KeycloakLifecycleError,
)
from app.adapters.vicidial.mtls_client import VicidialMtlsClient, VicidialMtlsError
from app.core.config import settings
from app.core.provisioning_auth import (
    ProvisioningPrincipal,
    require_current_policy_revision,
    require_provisioning_scope,
    require_tenant_match,
)
from app.db.models import (
    AgentProvisioningAudit,
    AgentProvisioningRequest,
    AgentProvisioningStep,
    IdempotencyRecord,
    OutboxEvent,
)
from app.db.session import get_session

router = APIRouter(prefix="/platform/v1/agent-provisioning", tags=["agent-provisioning"])

IDEMPOTENCY_SCOPE = "agent_provisioning"
TERMINAL_STATES = frozenset({"EFFECTIVE", "PARTIAL", "FAILED", "SUSPENDED", "REVOKED"})
TERMINAL_REVOKED_STATES = frozenset({"REVOKED"})


class CampaignAssignment(BaseModel):
    campaign_id: str = Field(min_length=1, max_length=64)
    role: str = Field(min_length=1, max_length=64)
    # Vicidialer-Codestra's own AgentSpec requires exactly these two
    # fields (user_id ^[A-Z]{3}[0-9]{4,12}$, user_group) and binds an
    # agent to exactly one campaign - so they only make sense on the
    # single campaign the phone/webrtc channels will actually use. Optional
    # because odoo/sms/email-only requests never need a VICIdial agent.
    vicidial_user_id: str | None = Field(default=None, pattern=r"^[A-Z]{3}[0-9]{4,12}$")
    vicidial_user_group: str | None = Field(default=None, pattern=r"^[A-Z0-9_]{2,20}$")
    # Vicidialer-Codestra requires every phone/webrtc mutation's context to
    # exactly match a pre-registered campaign_authority row (tenant_id,
    # business_unit, supervisor_subject) - it does not trust the caller's
    # bare say-so. This campaign must already have been provisioned there
    # (a separate, earlier flow); this field is not itself a provisioning
    # request for it.
    vicidial_supervisor_subject: str | None = Field(default=None, max_length=128)


class ChannelSelection(BaseModel):
    odoo: bool = False
    phone: bool = False
    webrtc: bool = False
    sms: bool = False
    email: bool = False


class TelephonySelection(BaseModel):
    existing_extension: str | None = Field(default=None, max_length=16)
    incoming_allowed: bool = True
    outgoing_allowed: bool = True
    max_webrtc_sessions: int = Field(default=1, ge=1, le=1)
    # One of Vicidialer-Codestra's six named campaign-type pools
    # (transportation/moneybee/web_ai/senior_products/student_repayment/
    # supervisor_qa). Required only when reserving a NEW extension
    # (existing_extension unset) - there is no confirmed mapping from this
    # codebase's campaign/business-unit identifiers onto those pool names,
    # so the caller must state it explicitly rather than have it guessed.
    extension_pool: str | None = Field(default=None, max_length=32)


class IdentitySelection(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    first_name: str = Field(default="", max_length=128)
    last_name: str = Field(default="", max_length=128)


class ProvisioningCreate(BaseModel):
    request_id: str = Field(min_length=1, max_length=128)
    tenant_id: str = Field(min_length=1, max_length=64)
    employee_id: str = Field(min_length=1, max_length=128)
    identity: IdentitySelection
    campaigns: list[CampaignAssignment] = Field(default_factory=list, max_length=32)
    channels: ChannelSelection
    telephony: TelephonySelection = Field(default_factory=TelephonySelection)


class TransitionRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=1000)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _record_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


async def _get_request(
    request_id: UUID, session: AsyncSession, *, for_update: bool = False,
) -> AgentProvisioningRequest:
    stmt = select(AgentProvisioningRequest).where(AgentProvisioningRequest.id == request_id)
    if for_update:
        stmt = stmt.with_for_update()
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "provisioning request not found")
    return row


async def _append_audit(
    session: AsyncSession, request: AgentProvisioningRequest, *,
    from_state: str, to_state: str, action: str, principal: ProvisioningPrincipal,
) -> None:
    session.add(AgentProvisioningAudit(
        id=uuid4(), request_id=request.id, from_state=from_state, to_state=to_state,
        action=action, actor_subject=principal.subject, correlation_id=request.correlation_id,
        record_hash=_record_hash({
            "request_id": str(request.id), "from": from_state, "to": to_state,
            "action": action, "actor": principal.subject, "at": _now().isoformat(),
        }),
    ))


async def _add_step(
    session: AsyncSession, request: AgentProvisioningRequest, *,
    system: str, operation: str, state: str,
    external_reference: str | None = None, readback_state: str | None = None,
    error_code: str | None = None, error_summary: str | None = None,
) -> None:
    session.add(AgentProvisioningStep(
        id=uuid4(), request_id=request.id, system=system, operation=operation,
        attempt=1, state=state, external_reference=external_reference,
        started_at=_now(), completed_at=_now(), readback_state=readback_state,
        error_code=error_code, error_summary=error_summary,
    ))


async def _emit_platform_event(
    session: AsyncSession, request: AgentProvisioningRequest, topic: str,
) -> None:
    """Notify n8n (Mission 4E) - and nothing more.

    n8n reacts only after this event lands; it never decides whether a
    user exists or is provisioned - that determination is made entirely
    above, by the saga itself. This reuses the existing generic outbox
    dispatch worker (the same "pending" row + worker pattern every other
    topic in this codebase already uses) rather than calling n8n directly
    from the request path.
    """
    session.add(OutboxEvent(
        id=uuid4(), topic=topic, correlation_id=request.correlation_id,
        status="pending",
        payload={
            "request_id": request.request_id,
            "tenant_id": request.tenant_id,
            "employee_id": request.employee_id,
            "primary_email": request.primary_email,
            "state": request.state,
            "last_error_code": request.last_error_code,
            "last_error_summary": request.last_error_summary,
        },
    ))


StepOutcome = Literal["ok", "gated", "failed"]


async def _run_identity_step(
    session: AsyncSession, request: AgentProvisioningRequest,
) -> StepOutcome:
    """IDENTITY: query-then-create the Keycloak user.

    "gated" (kill switch closed) is deliberately not the same outcome as
    "failed" (a real adapter/API error) - the saga's terminal state must
    tell an operator whether something is broken or simply not yet
    switched on.
    """
    if not settings.live_identity_provisioning_enabled:
        await _add_step(
            session, request, system="keycloak", operation="create_user",
            state="skipped", error_code="KILL_SWITCH_CLOSED",
            error_summary="live_identity_provisioning_enabled is false",
        )
        return "gated"
    adapter = KeycloakLifecycleAdapter(settings)
    identity = request.channels_json.get("_identity", {})
    try:
        existing = await adapter.query_user_by_email(request.primary_email)
        if existing is None:
            record = await adapter.create_user(
                request.primary_email,
                identity.get("first_name", ""), identity.get("last_name", ""),
            )
        else:
            record = existing
        request.keycloak_subject = record.keycloak_subject
        await _add_step(
            session, request, system="keycloak", operation="create_user",
            state="succeeded", external_reference=record.keycloak_subject,
            readback_state="enabled" if record.enabled else "disabled",
        )
        return "ok"
    except (KeycloakLifecycleError, KeycloakLifecycleDisabled) as exc:
        await _add_step(
            session, request, system="keycloak", operation="create_user",
            state="failed", error_code="KEYCLOAK_ADAPTER_ERROR", error_summary=str(exc),
        )
        return "failed"


async def _run_entitlements_step(
    session: AsyncSession, request: AgentProvisioningRequest,
) -> StepOutcome:
    """ENTITLEMENTS: assign the approved realm role(s) for the requested campaigns."""
    if not request.campaigns_json:
        return "ok"
    if not settings.live_identity_provisioning_enabled or not request.keycloak_subject:
        await _add_step(
            session, request, system="keycloak", operation="assign_approved_roles",
            state="skipped", error_code="KILL_SWITCH_CLOSED",
            error_summary="live_identity_provisioning_enabled is false or no keycloak_subject",
        )
        return "gated"
    adapter = KeycloakLifecycleAdapter(settings)
    role_names = sorted({entry["role"] for entry in request.campaigns_json})
    try:
        await adapter.assign_approved_roles(request.keycloak_subject, role_names)
        await _add_step(
            session, request, system="keycloak", operation="assign_approved_roles",
            state="succeeded", external_reference=",".join(role_names),
        )
        return "ok"
    except KeycloakLifecycleError as exc:
        await _add_step(
            session, request, system="keycloak", operation="assign_approved_roles",
            state="failed", error_code="KEYCLOAK_ADAPTER_ERROR", error_summary=str(exc),
        )
        return "failed"


async def _run_channel_provisioning_step(
    session: AsyncSession, request: AgentProvisioningRequest,
) -> StepOutcome:
    """CHANNEL_PROVISIONING: phone/webrtc now provision for real through
    the Vicidialer-Codestra adapter (Mission 6: sync_agent -> reserve or
    adopt an extension -> provision_webrtc if requested). sms/email still
    have no account-provisioning adapter anywhere in this codebase (only
    message-sending exists via app.telnexa_provider_adapter and
    app.klyrow_email_adapter), so those two remain recorded honestly as
    blocked rather than pretending they went live.

    Known limitation: a /reconcile re-run of this step after a prior
    PARTIAL/FAILED phone or webrtc attempt does not yet retry correctly -
    Vicidialer-Codestra's resource_versions optimistic-concurrency claim
    for "agent:<id>"/"extension:<id>"/"webrtc:<id>" starts each request at
    expected_version=0, and this saga does not track the version a prior
    partial attempt may have already advanced it to. The IDENTITY step
    does not have this problem (Keycloak's adapter is naturally
    idempotent via query-then-create); this one currently is not. Flagged
    as explicit follow-up, not silently swallowed.
    """
    channels = request.channels_json
    outcomes: list[StepOutcome] = []

    for name, system in (("sms", "telnexa"), ("email", "klyrow")):
        if channels.get(name):
            await _add_step(
                session, request, system=system, operation=f"provision_{name}",
                state="blocked", error_code="CHANNEL_ADAPTER_NOT_IMPLEMENTED",
                error_summary=(
                    f"No {system} account-provisioning adapter exists in this "
                    "codebase yet; only message-sending is implemented."
                ),
            )
            outcomes.append("gated")

    if not (channels.get("phone") or channels.get("webrtc")):
        return "ok" if not outcomes else "gated"

    if not (settings.vicidial_write_enabled and settings.live_writes_enabled):
        for name in ("phone", "webrtc"):
            if channels.get(name):
                await _add_step(
                    session, request, system="vicidial", operation=f"provision_{name}",
                    state="skipped", error_code="KILL_SWITCH_CLOSED",
                    error_summary="vicidial_write_enabled/live_writes_enabled is false",
                )
        outcomes.append("gated")
        return "gated" if "failed" not in outcomes else "failed"

    campaign = request.campaigns_json[0] if request.campaigns_json else {}
    telephony = channels.get("_telephony", {})
    identity = channels.get("_identity", {})
    vicidial_user_id = campaign.get("vicidial_user_id")
    vicidial_user_group = campaign.get("vicidial_user_group")
    vicidial_supervisor_subject = campaign.get("vicidial_supervisor_subject")
    business_unit = vicidial_user_id[:3] if vicidial_user_id else None

    if (
        not campaign or not vicidial_user_id or not vicidial_user_group
        or not vicidial_supervisor_subject
        or business_unit not in {
            "MOY", "COD", "SCP", "MBL", "RLP", "FTP", "TRX", "CAL", "TEST",
        }
    ):
        await _add_step(
            session, request, system="vicidial", operation="provision_phone",
            state="blocked", error_code="CHANNEL_CONFIGURATION_INCOMPLETE",
            error_summary=(
                "phone/webrtc requested but campaigns[0].vicidial_user_id/"
                "vicidial_user_group/vicidial_supervisor_subject were not "
                "supplied, or vicidial_user_id's business-unit prefix is "
                "not a recognized code"
            ),
        )
        outcomes.append("gated")
        return "failed" if "failed" in outcomes else "gated"

    context_payload = {
        "correlation_id": request.correlation_id, "actor": request.requested_by,
        "tenant_id": request.tenant_id, "business_unit": business_unit,
        "campaign_id": campaign["campaign_id"],
        "supervisor_subject": vicidial_supervisor_subject,
        "expected_version": 0, "reason": "agent provisioning saga",
        "requested_at": _now().isoformat(),
    }
    adapter = VicidialMtlsClient(settings)
    try:
        try:
            adapter.sync_agent({
                "context": context_payload,
                "agent": {
                    "user_id": vicidial_user_id,
                    "full_name": (
                        f"{identity.get('first_name', '')} {identity.get('last_name', '')}"
                    ).strip() or vicidial_user_id,
                    "user_group": vicidial_user_group,
                    "campaigns": [campaign["campaign_id"]],
                    "inbound_groups": [], "active": False,
                },
            })
            await _add_step(
                session, request, system="vicidial", operation="sync_agent",
                state="succeeded", external_reference=vicidial_user_id,
            )
        except VicidialMtlsError as exc:
            await _add_step(
                session, request, system="vicidial", operation="sync_agent",
                state="failed", error_code="VICIDIAL_ADAPTER_ERROR", error_summary=str(exc),
            )
            return "failed"

        extension = None
        try:
            if telephony.get("existing_extension"):
                result = adapter.adopt_extension({
                    "context": context_payload,
                    "adoption": {
                        "user_id": vicidial_user_id,
                        "extension": telephony["existing_extension"],
                        "webrtc_enabled": bool(channels.get("webrtc")),
                        "incoming_allowed": telephony.get("incoming_allowed", True),
                        "outgoing_allowed": telephony.get("outgoing_allowed", True),
                    },
                })
                operation = "adopt_extension"
            elif telephony.get("extension_pool"):
                result = adapter.reserve_extension({
                    "context": context_payload,
                    "reservation": {
                        "user_id": vicidial_user_id, "pool": telephony["extension_pool"],
                        "webrtc_enabled": bool(channels.get("webrtc")),
                        "incoming_allowed": telephony.get("incoming_allowed", True),
                        "outgoing_allowed": telephony.get("outgoing_allowed", True),
                    },
                })
                operation = "reserve_extension"
            else:
                await _add_step(
                    session, request, system="vicidial", operation="provision_phone",
                    state="blocked", error_code="CHANNEL_CONFIGURATION_INCOMPLETE",
                    error_summary="neither existing_extension nor extension_pool was supplied",
                )
                return "gated"
            extension = (result.get("actual") or {}).get("extension")
            await _add_step(
                session, request, system="vicidial", operation=operation,
                state="succeeded", external_reference=extension,
                readback_state="phone_active",
            )
        except VicidialMtlsError as exc:
            await _add_step(
                session, request, system="vicidial", operation="provision_phone",
                state="failed", error_code="VICIDIAL_ADAPTER_ERROR", error_summary=str(exc),
            )
            return "failed"

        if channels.get("webrtc"):
            try:
                adapter.provision_webrtc({
                    "context": context_payload, "webrtc": {"user_id": vicidial_user_id},
                })
                await _add_step(
                    session, request, system="vicidial", operation="provision_webrtc",
                    state="succeeded", external_reference=extension,
                    readback_state="webrtc_session_issued",
                )
            except VicidialMtlsError as exc:
                await _add_step(
                    session, request, system="vicidial", operation="provision_webrtc",
                    state="failed", error_code="VICIDIAL_ADAPTER_ERROR", error_summary=str(exc),
                )
                return "failed"
    finally:
        adapter.close()

    return "gated" if outcomes else "ok"


async def _run_readback_step(
    session: AsyncSession, request: AgentProvisioningRequest, identity_outcome: StepOutcome,
) -> StepOutcome:
    if identity_outcome != "ok" or not request.keycloak_subject:
        return "gated"
    if not settings.live_identity_provisioning_enabled:
        await _add_step(
            session, request, system="keycloak", operation="readback",
            state="skipped", error_code="KILL_SWITCH_CLOSED",
        )
        return "gated"
    adapter = KeycloakLifecycleAdapter(settings)
    try:
        record = await adapter.query_user_by_email(request.primary_email)
        ok = record is not None and record.enabled
        await _add_step(
            session, request, system="keycloak", operation="readback",
            state="succeeded" if ok else "failed",
            readback_state="enabled" if ok else "not_confirmed",
        )
        return "ok" if ok else "failed"
    except KeycloakLifecycleError as exc:
        await _add_step(
            session, request, system="keycloak", operation="readback",
            state="failed", error_code="KEYCLOAK_ADAPTER_ERROR", error_summary=str(exc),
        )
        return "failed"


async def _advance_saga(
    session: AsyncSession, request: AgentProvisioningRequest, principal: ProvisioningPrincipal,
) -> None:
    """Run REQUESTED -> VALIDATING -> IDENTITY -> ENTITLEMENTS ->
    CHANNEL_PROVISIONING -> READBACK -> {EFFECTIVE, PARTIAL, FAILED}
    synchronously within the request that created or is reconciling the
    saga. Every external effect inside each step is itself fail-closed
    (see the step functions above), so running this synchronously never
    risks a slow or unbounded external call by default.

    The terminal state distinguishes a real error from a designed gate:
    any step outcome of "failed" (an adapter/API genuinely errored) makes
    the whole saga FAILED; if nothing failed but something was "gated"
    (a kill switch closed, or a channel adapter that does not exist yet)
    the saga is PARTIAL; only when every step reports "ok" is it EFFECTIVE.
    """
    from_state = request.state
    request.state = "VALIDATING"
    request.state = "IDENTITY"
    identity_outcome = await _run_identity_step(session, request)
    request.state = "ENTITLEMENTS"
    entitlements_outcome = await _run_entitlements_step(session, request)
    request.state = "CHANNEL_PROVISIONING"
    channels_outcome = await _run_channel_provisioning_step(session, request)
    request.state = "READBACK"
    readback_outcome = await _run_readback_step(session, request, identity_outcome)

    outcomes = (identity_outcome, entitlements_outcome, channels_outcome, readback_outcome)
    if "failed" in outcomes:
        request.state = "FAILED"
        request.last_error_code = "SAGA_STEP_FAILED"
        request.last_error_summary = "At least one provisioning step returned a real adapter error."
        await _emit_platform_event(session, request, "platform.user.provision_failed")
    elif all(outcome == "ok" for outcome in outcomes):
        request.state = "EFFECTIVE"
        await _emit_platform_event(session, request, "platform.user.provisioned")
    else:
        request.state = "PARTIAL"

    request.version += 1
    await _append_audit(
        session, request, from_state=from_state, to_state=request.state,
        action="advance", principal=principal,
    )


def _public_view(request: AgentProvisioningRequest, steps: list[AgentProvisioningStep]) -> dict:
    return {
        "request_id": request.request_id,
        "tenant_id": request.tenant_id,
        "employee_id": request.employee_id,
        "state": request.state,
        "correlation_id": request.correlation_id,
        "keycloak_subject": request.keycloak_subject,
        "last_error_code": request.last_error_code,
        "last_error_summary": request.last_error_summary,
        "version": request.version,
        "steps": [
            {
                "system": step.system, "operation": step.operation, "attempt": step.attempt,
                "state": step.state, "external_reference": step.external_reference,
                "readback_state": step.readback_state, "error_code": step.error_code,
                "error_summary": step.error_summary,
                "started_at": step.started_at, "completed_at": step.completed_at,
            }
            for step in steps
        ],
    }


async def _steps_for(session: AsyncSession, request: AgentProvisioningRequest) -> list[AgentProvisioningStep]:
    rows = (
        await session.execute(
            select(AgentProvisioningStep)
            .where(AgentProvisioningStep.request_id == request.id)
            .order_by(AgentProvisioningStep.created_at)
        )
    ).scalars().all()
    return list(rows)


@router.post("/requests", status_code=status.HTTP_202_ACCEPTED)
async def create_provisioning_request(
    body: ProvisioningCreate,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=16, max_length=256),
    x_correlation_id: str = Header("", alias="X-Correlation-ID"),
    x_policy_revision: str = Header(..., alias="X-Policy-Revision"),
    principal: ProvisioningPrincipal = Depends(require_provisioning_scope("identity.request")),
    session: AsyncSession = Depends(get_session),
):
    require_tenant_match(principal, body.tenant_id)
    require_current_policy_revision(x_policy_revision)

    correlation_id = x_correlation_id or str(uuid4())
    request_payload = body.model_dump(mode="json")
    request_hash = _hash(json.dumps(request_payload, sort_keys=True))
    key_hash = _hash(f"{IDEMPOTENCY_SCOPE}:{idempotency_key}")

    existing_idempotency = (
        await session.execute(
            select(IdempotencyRecord).where(
                IdempotencyRecord.scope == IDEMPOTENCY_SCOPE,
                IdempotencyRecord.key_hash == key_hash,
            )
        )
    ).scalar_one_or_none()
    if existing_idempotency is not None:
        if existing_idempotency.request_hash != request_hash:
            raise HTTPException(409, "Idempotency-Key reused with a different request body")
        return existing_idempotency.response

    row = AgentProvisioningRequest(
        id=uuid4(), request_id=body.request_id, tenant_id=body.tenant_id,
        employee_id=body.employee_id, primary_email=body.identity.email,
        campaigns_json=[c.model_dump() for c in body.campaigns],
        channels_json={
            **body.channels.model_dump(),
            "_identity": body.identity.model_dump(),
            "_telephony": body.telephony.model_dump(),
        },
        telephony_json=body.telephony.model_dump(),
        state="REQUESTED", policy_revision=x_policy_revision,
        idempotency_hash=key_hash, request_hash=request_hash,
        correlation_id=correlation_id, requested_by=principal.subject,
    )
    session.add(row)
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(409, "request_id already exists") from exc

    await _append_audit(
        session, row, from_state="", to_state="REQUESTED", action="create", principal=principal,
    )
    await _advance_saga(session, row, principal)

    steps = await _steps_for(session, row)
    response = jsonable_encoder(_public_view(row, steps))
    session.add(IdempotencyRecord(
        id=uuid4(), scope=IDEMPOTENCY_SCOPE, key_hash=key_hash, request_hash=request_hash,
        response=response, status_code=202,
    ))
    await session.commit()
    return response


@router.get("/requests/{request_id}")
async def get_provisioning_request(
    request_id: UUID,
    principal: ProvisioningPrincipal = Depends(require_provisioning_scope("identity.request")),
    session: AsyncSession = Depends(get_session),
):
    request = await _get_request(request_id, session)
    require_tenant_match(principal, request.tenant_id)
    steps = await _steps_for(session, request)
    return _public_view(request, steps)


async def _transition(
    request_id: UUID, body: TransitionRequest, action: Literal["reconcile", "suspend", "reactivate", "revoke"],
    principal: ProvisioningPrincipal, session: AsyncSession,
) -> dict:
    request = await _get_request(request_id, session, for_update=True)
    require_tenant_match(principal, request.tenant_id)
    if request.state in TERMINAL_REVOKED_STATES:
        raise HTTPException(409, f"cannot {action} a revoked request")
    from_state = request.state

    if action == "reconcile":
        request.state = "RECONCILING"
        await _advance_saga(session, request, principal)
    elif action == "suspend":
        if settings.live_identity_provisioning_enabled and request.keycloak_subject:
            adapter = KeycloakLifecycleAdapter(settings)
            try:
                await adapter.disable_user(request.keycloak_subject)
                await _add_step(
                    session, request, system="keycloak", operation="disable_user",
                    state="succeeded", external_reference=request.keycloak_subject,
                )
            except KeycloakLifecycleError as exc:
                await _add_step(
                    session, request, system="keycloak", operation="disable_user",
                    state="failed", error_code="KEYCLOAK_ADAPTER_ERROR", error_summary=str(exc),
                )
        request.state = "SUSPENDED"
        request.version += 1
        await _append_audit(session, request, from_state=from_state, to_state="SUSPENDED", action=action, principal=principal)
    elif action == "reactivate":
        if request.state != "SUSPENDED":
            raise HTTPException(409, "only a suspended request may be reactivated")
        if settings.live_identity_provisioning_enabled and request.keycloak_subject:
            adapter = KeycloakLifecycleAdapter(settings)
            try:
                await adapter.enable_user(request.keycloak_subject)
                await _add_step(
                    session, request, system="keycloak", operation="enable_user",
                    state="succeeded", external_reference=request.keycloak_subject,
                )
            except KeycloakLifecycleError as exc:
                await _add_step(
                    session, request, system="keycloak", operation="enable_user",
                    state="failed", error_code="KEYCLOAK_ADAPTER_ERROR", error_summary=str(exc),
                )
        request.state = "PARTIAL"
        request.version += 1
        await _append_audit(session, request, from_state=from_state, to_state="PARTIAL", action=action, principal=principal)
    elif action == "revoke":
        if settings.live_identity_provisioning_enabled and request.keycloak_subject:
            adapter = KeycloakLifecycleAdapter(settings)
            try:
                await adapter.disable_user(request.keycloak_subject)
                await _add_step(
                    session, request, system="keycloak", operation="disable_user",
                    state="succeeded", external_reference=request.keycloak_subject,
                )
            except KeycloakLifecycleError as exc:
                await _add_step(
                    session, request, system="keycloak", operation="disable_user",
                    state="failed", error_code="KEYCLOAK_ADAPTER_ERROR", error_summary=str(exc),
                )
        request.state = "REVOKED"
        request.version += 1
        await _append_audit(session, request, from_state=from_state, to_state="REVOKED", action=action, principal=principal)

    await session.commit()
    steps = await _steps_for(session, request)
    return _public_view(request, steps)


@router.post("/requests/{request_id}/reconcile")
async def reconcile_provisioning_request(
    request_id: UUID, body: TransitionRequest,
    principal: ProvisioningPrincipal = Depends(require_provisioning_scope("identity.request")),
    session: AsyncSession = Depends(get_session),
):
    return await _transition(request_id, body, "reconcile", principal, session)


@router.post("/requests/{request_id}/suspend")
async def suspend_provisioning_request(
    request_id: UUID, body: TransitionRequest,
    principal: ProvisioningPrincipal = Depends(require_provisioning_scope("identity.request")),
    session: AsyncSession = Depends(get_session),
):
    return await _transition(request_id, body, "suspend", principal, session)


@router.post("/requests/{request_id}/reactivate")
async def reactivate_provisioning_request(
    request_id: UUID, body: TransitionRequest,
    principal: ProvisioningPrincipal = Depends(require_provisioning_scope("identity.request")),
    session: AsyncSession = Depends(get_session),
):
    return await _transition(request_id, body, "reactivate", principal, session)


@router.post("/requests/{request_id}/revoke")
async def revoke_provisioning_request(
    request_id: UUID, body: TransitionRequest,
    principal: ProvisioningPrincipal = Depends(require_provisioning_scope("identity.request")),
    session: AsyncSession = Depends(get_session),
):
    return await _transition(request_id, body, "revoke", principal, session)
