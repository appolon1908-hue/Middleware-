"""``GET /platform/v1/campaigns``, ``/campaigns/{campaign_id}``,
``/campaigns/{campaign_id}/members``, ``/campaigns/{campaign_id}/channels``,
``/campaigns/{campaign_id}/health``.

Campaigns are genuinely Middleware/VICIdial-domain data (unlike tenants,
which ``tenants.py`` resolves through ``codestra-foundation``). This module
reads the same ``campaign_registry`` table ``queues.py`` already reads -
note that in this deployment a VICIdial "queue" and a "campaign" are the
same underlying ``campaign_registry`` row (``vicidial_campaign_id``); this
router exposes campaign-shaped fields (channels, membership) that
``queues.py`` does not, rather than duplicating its queue/hopper-backlog
view.

``/members`` follows the exact same honesty convention ``queues.py``
established: there is no durable campaign-membership roster in this
codebase (that is Odoo-side, ``cc.campaign.membership``) - this reports
agents recently *active* in the campaign, explicitly labelled as such.

``/channels`` has no durable campaign-level channel-state table either. It
uses each agent's latest provisioning request and reports how many current
desired-state records include each channel. Historical requests and revoked,
suspended, or failed latest requests are excluded, so retries do not inflate
the result. This is still desired intent, not live effective provider state.

``/health`` reuses ``calls.py``'s ``telephony_call_lifecycle`` +
``audit_event`` business-unit join for a basic call-volume signal - no
health-scoring model exists anywhere in this codebase to draw from. Stated
limitation: the audit payload's ``campaign`` field (a ``TEST_SYN``-style
code from ``OriginateCallRequest.campaign``) was not confirmed this pass to
map cleanly onto ``campaign_registry.vicidial_campaign_id``/
``campaign_number``, so this endpoint scopes by tenant (business_unit) only,
not by the specific campaign - it reports the whole tenant's call volume,
not this campaign's alone. Narrowing this needs that mapping confirmed
first, not guessed at.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.calls import _business_unit_column
from app.core.provisioning_auth import (
    ProvisioningPrincipal,
    require_provisioning_scope,
    require_tenant_match,
)
from app.db.models import (
    AgentCallState,
    AgentProvisioningRequest,
    AuditEvent,
    CampaignRegistry,
    TelephonyCallLifecycle,
)
from app.db.session import get_session

router = APIRouter(prefix="/platform/v1/campaigns", tags=["campaigns"])

RECENT_ACTIVE_WINDOW = timedelta(minutes=30)
RECENT_HEALTH_WINDOW = timedelta(hours=1)


async def _registry_row(
    session: AsyncSession,
    campaign_id: str,
    tenant_id: str,
) -> CampaignRegistry:
    registry = await session.scalar(
        select(CampaignRegistry).where(
            CampaignRegistry.vicidial_campaign_id == campaign_id,
            CampaignRegistry.campaign_code == tenant_id,
        )
    )
    if registry is None:
        raise HTTPException(404, "campaign not found for this tenant")
    return registry


def _campaign_out(registry: CampaignRegistry) -> dict[str, Any]:
    return {
        "campaign_id": registry.vicidial_campaign_id,
        "campaign_number": registry.campaign_number,
        "campaign_code": registry.campaign_code,
        "name": registry.name,
        "registry_status": registry.registry_status,
    }


@router.get("")
async def list_campaigns(
    tenant_id: str = Query(..., description="campaign_code to scope results to"),
    principal: ProvisioningPrincipal = Depends(
        require_provisioning_scope("identity.request")
    ),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    require_tenant_match(principal, tenant_id)
    stmt = (
        select(CampaignRegistry)
        .where(CampaignRegistry.campaign_code == tenant_id)
        .order_by(CampaignRegistry.campaign_number)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return {"items": [_campaign_out(row) for row in rows]}


@router.get("/{campaign_id}")
async def get_campaign(
    campaign_id: str,
    tenant_id: str = Query(
        ..., description="campaign_code expected to own this campaign"
    ),
    principal: ProvisioningPrincipal = Depends(
        require_provisioning_scope("identity.request")
    ),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    require_tenant_match(principal, tenant_id)
    registry = await _registry_row(session, campaign_id, tenant_id)
    return _campaign_out(registry)


@router.get("/{campaign_id}/members")
async def list_campaign_members(
    campaign_id: str,
    tenant_id: str = Query(
        ..., description="campaign_code expected to own this campaign"
    ),
    principal: ProvisioningPrincipal = Depends(
        require_provisioning_scope("identity.request")
    ),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    require_tenant_match(principal, tenant_id)
    await _registry_row(session, campaign_id, tenant_id)

    since = datetime.now(UTC) - RECENT_ACTIVE_WINDOW
    stmt = (
        select(AgentCallState.agent_id)
        .where(
            AgentCallState.campaign_id == campaign_id,
            AgentCallState.updated_at >= since,
        )
        .distinct()
        .order_by(AgentCallState.agent_id)
    )
    agent_ids = (await session.execute(stmt)).scalars().all()
    return {"recently_active_agents": sorted(agent_ids)}


@router.get("/{campaign_id}/channels")
async def get_campaign_channels(
    campaign_id: str,
    tenant_id: str = Query(
        ..., description="campaign_code expected to own this campaign"
    ),
    principal: ProvisioningPrincipal = Depends(
        require_provisioning_scope("identity.request")
    ),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    require_tenant_match(principal, tenant_id)
    await _registry_row(session, campaign_id, tenant_id)

    latest = (
        select(
            AgentProvisioningRequest.employee_id,
            AgentProvisioningRequest.campaigns_json,
            AgentProvisioningRequest.channels_json,
            AgentProvisioningRequest.state,
            func.row_number()
            .over(
                partition_by=AgentProvisioningRequest.employee_id,
                order_by=(
                    AgentProvisioningRequest.created_at.desc(),
                    AgentProvisioningRequest.id.desc(),
                ),
            )
            .label("request_rank"),
        )
        .where(AgentProvisioningRequest.tenant_id == tenant_id)
        .subquery()
    )
    requests = (
        await session.execute(
            select(
                latest.c.campaigns_json,
                latest.c.channels_json,
                latest.c.state,
            ).where(latest.c.request_rank == 1)
        )
    ).all()

    counts: dict[str, int] = {}
    matched_requests = 0
    for campaigns_json, channels_json, state in requests:
        if state in {"FAILED", "SUSPENDED", "REVOKED"}:
            continue
        campaigns = campaigns_json or []
        if not any(
            isinstance(entry, dict) and entry.get("campaign_id") == campaign_id
            for entry in campaigns
        ):
            continue
        matched_requests += 1
        for channel, desired in (channels_json or {}).items():
            if desired:
                counts[channel] = counts.get(channel, 0) + 1

    return {
        "campaign_id": campaign_id,
        "provisioning_requests_referencing_campaign": matched_requests,
        "desired_channel_counts": counts,
        "projection": "latest_desired_request_per_agent",
    }


@router.get("/{campaign_id}/health")
async def get_campaign_health(
    campaign_id: str,
    tenant_id: str = Query(
        ..., description="campaign_code expected to own this campaign"
    ),
    principal: ProvisioningPrincipal = Depends(
        require_provisioning_scope("identity.request")
    ),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    require_tenant_match(principal, tenant_id)
    await _registry_row(session, campaign_id, tenant_id)

    since = datetime.now(UTC) - RECENT_HEALTH_WINDOW
    stmt = (
        select(TelephonyCallLifecycle)
        .join(
            AuditEvent,
            AuditEvent.correlation_id == TelephonyCallLifecycle.correlation_id,
        )
        .where(
            AuditEvent.action == "telephony.calls.originate",
            _business_unit_column() == tenant_id,
            TelephonyCallLifecycle.created_at >= since,
        )
    )
    calls = (await session.execute(stmt)).scalars().unique().all()
    ended = sum(1 for c in calls if c.lifecycle_state == "ENDED")

    return {
        "campaign_id": campaign_id,
        "scope": "tenant",
        "calls_last_hour": len(calls),
        "ended_last_hour": ended,
    }
