"""``GET /platform/v1/tenants``, ``/tenants/{tenant_id}``,
``/tenants/{tenant_id}/campaigns``, ``/tenants/{tenant_id}/health``.

``codestra-foundation`` is the existing, already-implemented authority for
tenant lifecycle (confirmed this session: real ``tenants.py`` router with
tenant-scoped auth). This module does not reimplement tenant storage - every
tenant record returned here comes from ``FoundationClient.get_tenant``, the
same client ``session_context.py`` already established for exactly this
purpose. See ``app/adapters/foundation/client.py`` for the full contract.

``FoundationClient`` only exposes per-tenant lookups (``get_tenant``,
``list_entitlements``); it has no "list all tenants" operation. ``GET
/tenants`` therefore enumerates the distinct ``campaign_registry.
campaign_code`` values this deployment actually has provisioned campaigns
for (the same three-letter business-unit vocabulary ``calls.py``/
``queues.py`` already treat as ``tenant_id`` - see ``mappings.py``'s
``ALLOWED_UNITS``), then resolves each one against ``codestra-foundation``.
A code with no matching foundation tenant is excluded, not fabricated -
fail closed, matching this codebase's established convention.

``/tenants/{tenant_id}/campaigns`` reads ``campaign_registry`` directly -
genuinely Middleware/VICIdial-domain data, not foundation's.

``/tenants/{tenant_id}/health`` is a thin operational signal (call volume in
the last hour, distinct active agents), not a fabricated score - there is no
health-scoring model anywhere in this codebase to draw from.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.foundation.client import (
    FoundationClient,
    FoundationTenantNotFound,
    FoundationUnavailable,
)
from app.core.config import settings
from app.core.provisioning_auth import (
    ProvisioningPrincipal,
    require_provisioning_scope,
    require_tenant_match,
)
from app.db.models import AgentCallState, CampaignRegistry
from app.db.session import get_session

router = APIRouter(prefix="/platform/v1/tenants", tags=["tenants"])

RECENT_ACTIVE_WINDOW = timedelta(minutes=30)


async def _distinct_campaign_codes(session: AsyncSession) -> list[str]:
    stmt = select(CampaignRegistry.campaign_code).distinct().order_by(CampaignRegistry.campaign_code)
    return [row[0] for row in (await session.execute(stmt)).all()]


async def _resolve_tenant(
    foundation: FoundationClient, http: httpx.AsyncClient, tenant_id: str
) -> dict[str, Any] | None:
    try:
        record = await foundation.get_tenant(http, tenant_id)
    except FoundationTenantNotFound:
        return None
    except FoundationUnavailable:
        # A foundation outage must not make every tenant disappear from the
        # list; report the ID as unavailable rather than silently dropping
        # it or fabricating tenant details - same fail-closed-but-visible
        # convention session_context.py already established.
        return {"id": tenant_id, "status": "UNAVAILABLE"}
    return {"id": record.id, "slug": record.slug, "name": record.name, "status": record.status}


@router.get("")
async def list_tenants(
    principal: ProvisioningPrincipal = Depends(require_provisioning_scope("identity.request")),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    # A provisioning token is tenant-scoped. Do not turn this discovery
    # endpoint into an all-tenant enumeration primitive when the database has
    # rows for several customers.
    codes = [
        code
        for code in await _distinct_campaign_codes(session)
        if code in principal.tenant_ids
    ]
    foundation = FoundationClient(settings)
    items: list[dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=5.0) as http:
        for code in codes:
            tenant = await _resolve_tenant(foundation, http, code)
            if tenant is not None:
                items.append(tenant)
    return {"items": items}


@router.get("/{tenant_id}")
async def get_tenant(
    tenant_id: str,
    principal: ProvisioningPrincipal = Depends(require_provisioning_scope("identity.request")),
) -> dict[str, Any]:
    require_tenant_match(principal, tenant_id)
    foundation = FoundationClient(settings)
    async with httpx.AsyncClient(timeout=5.0) as http:
        tenant = await _resolve_tenant(foundation, http, tenant_id)
    if tenant is None:
        raise HTTPException(404, "tenant not found")
    return tenant


@router.get("/{tenant_id}/campaigns")
async def list_tenant_campaigns(
    tenant_id: str,
    principal: ProvisioningPrincipal = Depends(require_provisioning_scope("identity.request")),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    require_tenant_match(principal, tenant_id)
    stmt = select(CampaignRegistry).where(CampaignRegistry.campaign_code == tenant_id)
    rows = (await session.execute(stmt)).scalars().all()
    items = [
        {
            "campaign_id": row.vicidial_campaign_id,
            "campaign_number": row.campaign_number,
            "name": row.name,
            "registry_status": row.registry_status,
        }
        for row in rows
    ]
    return {"items": items}


@router.get("/{tenant_id}/health")
async def get_tenant_health(
    tenant_id: str,
    principal: ProvisioningPrincipal = Depends(require_provisioning_scope("identity.request")),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    require_tenant_match(principal, tenant_id)
    campaign_ids = (
        await session.execute(
            select(CampaignRegistry.vicidial_campaign_id).where(
                CampaignRegistry.campaign_code == tenant_id
            )
        )
    ).scalars().all()

    since = datetime.now(timezone.utc) - RECENT_ACTIVE_WINDOW
    active_agents = 0
    if campaign_ids:
        stmt = select(AgentCallState.agent_id).where(
            AgentCallState.campaign_id.in_(campaign_ids),
            AgentCallState.updated_at >= since,
        ).distinct()
        active_agents = len((await session.execute(stmt)).all())

    return {
        "tenant_id": tenant_id,
        "campaign_count": len(campaign_ids),
        "active_agents_last_30m": active_agents,
    }
