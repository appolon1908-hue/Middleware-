"""``/platform/v1/contacts`` (+ their notes/tasks) and ``/platform/v1/tasks``.

Odoo's ``cc.customer.profile`` (a campaign-scoped, phone-masked projection of
``res.partner``) is the authoritative contact record; notes are
``mail.message``, tasks are ``mail.activity``. This router owns none of that
-- it only signs and forwards requests to ``codestra_middleware_bridge``'s
HTTP surface via ``app.adapters.odoo.crm_bridge_client`` and relays its
response. See that client's module docstring for why this is a distinct
auth/transport contract from ``app.adapters.odoo.sync.OdooRuntimeClient``.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse

from app.adapters.odoo.crm_bridge_client import (
    OdooCrmBridgeClient,
    get_crm_bridge_client,
)
from app.api.v1.crm_common import call_bridge, correlation_id, idempotency_key
from app.core.provisioning_auth import (
    ProvisioningPrincipal,
    require_provisioning_scope,
    require_tenant_match,
)

router = APIRouter(prefix="/platform/v1", tags=["contacts"])


@router.get("/contacts")
async def list_contacts(
    request: Request,
    tenant_id: str = Query(...),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    principal: ProvisioningPrincipal = Depends(require_provisioning_scope("identity.request")),
    client: OdooCrmBridgeClient = Depends(get_crm_bridge_client),
) -> JSONResponse:
    require_tenant_match(principal, tenant_id)
    cid = correlation_id(request)
    return await call_bridge(client.list_contacts(correlation_id=cid, limit=limit, offset=offset))


@router.get("/contacts/{contact_id}")
async def get_contact(
    request: Request,
    contact_id: int,
    tenant_id: str = Query(...),
    principal: ProvisioningPrincipal = Depends(require_provisioning_scope("identity.request")),
    client: OdooCrmBridgeClient = Depends(get_crm_bridge_client),
) -> JSONResponse:
    require_tenant_match(principal, tenant_id)
    cid = correlation_id(request)
    return await call_bridge(client.get_contact(contact_id, correlation_id=cid))


@router.post("/contacts")
async def create_contact(
    request: Request,
    payload: dict[str, Any],
    tenant_id: str = Query(...),
    principal: ProvisioningPrincipal = Depends(require_provisioning_scope("identity.request")),
    client: OdooCrmBridgeClient = Depends(get_crm_bridge_client),
) -> JSONResponse:
    require_tenant_match(principal, tenant_id)
    cid = correlation_id(request)
    return await call_bridge(
        client.create_contact(payload, correlation_id=cid, idempotency_key=idempotency_key(request, cid))
    )


@router.patch("/contacts/{contact_id}")
async def update_contact(
    request: Request,
    contact_id: int,
    payload: dict[str, Any],
    tenant_id: str = Query(...),
    principal: ProvisioningPrincipal = Depends(require_provisioning_scope("identity.request")),
    client: OdooCrmBridgeClient = Depends(get_crm_bridge_client),
) -> JSONResponse:
    require_tenant_match(principal, tenant_id)
    cid = correlation_id(request)
    return await call_bridge(
        client.update_contact(
            contact_id, payload, correlation_id=cid, idempotency_key=idempotency_key(request, cid)
        )
    )


@router.get("/contacts/{contact_id}/notes")
async def list_notes(
    request: Request,
    contact_id: int,
    tenant_id: str = Query(...),
    principal: ProvisioningPrincipal = Depends(require_provisioning_scope("identity.request")),
    client: OdooCrmBridgeClient = Depends(get_crm_bridge_client),
) -> JSONResponse:
    require_tenant_match(principal, tenant_id)
    cid = correlation_id(request)
    return await call_bridge(client.list_notes(contact_id, correlation_id=cid))


@router.post("/contacts/{contact_id}/notes")
async def create_note(
    request: Request,
    contact_id: int,
    payload: dict[str, Any],
    tenant_id: str = Query(...),
    principal: ProvisioningPrincipal = Depends(require_provisioning_scope("identity.request")),
    client: OdooCrmBridgeClient = Depends(get_crm_bridge_client),
) -> JSONResponse:
    require_tenant_match(principal, tenant_id)
    cid = correlation_id(request)
    return await call_bridge(
        client.create_note(
            contact_id, payload, correlation_id=cid, idempotency_key=idempotency_key(request, cid)
        )
    )


@router.patch("/contacts/{contact_id}/notes/{note_id}")
async def update_note(
    request: Request,
    contact_id: int,
    note_id: int,
    payload: dict[str, Any],
    tenant_id: str = Query(...),
    principal: ProvisioningPrincipal = Depends(require_provisioning_scope("identity.request")),
    client: OdooCrmBridgeClient = Depends(get_crm_bridge_client),
) -> JSONResponse:
    # contact_id is accepted (and required by the route shape given in the
    # directive) for URL symmetry with the read side; the bridge scopes notes
    # by note_id alone, same as codestra_middleware_bridge's own routing.
    require_tenant_match(principal, tenant_id)
    cid = correlation_id(request)
    return await call_bridge(
        client.update_note(
            note_id, payload, correlation_id=cid, idempotency_key=idempotency_key(request, cid)
        )
    )


@router.get("/contacts/{contact_id}/tasks")
async def list_tasks(
    request: Request,
    contact_id: int,
    tenant_id: str = Query(...),
    principal: ProvisioningPrincipal = Depends(require_provisioning_scope("identity.request")),
    client: OdooCrmBridgeClient = Depends(get_crm_bridge_client),
) -> JSONResponse:
    require_tenant_match(principal, tenant_id)
    cid = correlation_id(request)
    return await call_bridge(client.list_tasks(contact_id, correlation_id=cid))


@router.post("/contacts/{contact_id}/tasks")
async def create_task(
    request: Request,
    contact_id: int,
    payload: dict[str, Any],
    tenant_id: str = Query(...),
    principal: ProvisioningPrincipal = Depends(require_provisioning_scope("identity.request")),
    client: OdooCrmBridgeClient = Depends(get_crm_bridge_client),
) -> JSONResponse:
    require_tenant_match(principal, tenant_id)
    cid = correlation_id(request)
    return await call_bridge(
        client.create_task(
            contact_id, payload, correlation_id=cid, idempotency_key=idempotency_key(request, cid)
        )
    )


@router.patch("/tasks/{task_id}")
async def update_task(
    request: Request,
    task_id: int,
    payload: dict[str, Any],
    tenant_id: str = Query(...),
    principal: ProvisioningPrincipal = Depends(require_provisioning_scope("identity.request")),
    client: OdooCrmBridgeClient = Depends(get_crm_bridge_client),
) -> JSONResponse:
    require_tenant_match(principal, tenant_id)
    cid = correlation_id(request)
    return await call_bridge(
        client.update_task(
            task_id, payload, correlation_id=cid, idempotency_key=idempotency_key(request, cid)
        )
    )


@router.post("/tasks/{task_id}/complete")
async def complete_task(
    request: Request,
    task_id: int,
    tenant_id: str = Query(...),
    principal: ProvisioningPrincipal = Depends(require_provisioning_scope("identity.request")),
    client: OdooCrmBridgeClient = Depends(get_crm_bridge_client),
) -> JSONResponse:
    require_tenant_match(principal, tenant_id)
    cid = correlation_id(request)
    return await call_bridge(
        client.complete_task(task_id, {}, correlation_id=cid, idempotency_key=idempotency_key(request, cid))
    )
