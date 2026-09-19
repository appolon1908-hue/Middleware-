"""Shared plumbing for the contacts/opportunities/tickets routers.

All three are thin adapters over ``codestra_middleware_bridge`` (see
``app.adapters.odoo.crm_bridge_client``) -- this module only carries the
request/response glue (correlation id, idempotency key, exception mapping)
common to them, not any CRM business logic.
"""

from __future__ import annotations

from uuid import uuid4

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

from app.adapters.odoo.crm_bridge_client import (
    BridgeResponse,
    CrmBridgeNotConfigured,
    CrmBridgeNotFound,
    CrmBridgeUnavailable,
)


def correlation_id(request: Request) -> str:
    return request.headers.get("X-Correlation-ID", "").strip() or str(uuid4())


def ensure_bridge_tenant(client: object, tenant_id: str) -> None:
    """Fail closed when this bridge instance is pinned to another tenant.

    The bridge credential is configured for one tenant. The API still accepts
    a tenant selector so the caller's token can be checked at the edge, but a
    request must never be signed with the configured tenant while claiming to
    serve a different one. Test doubles may omit the property; the concrete
    OdooCrmBridgeClient always exposes it.
    """
    configured = getattr(client, "configured_tenant_id", None)
    if isinstance(configured, str) and configured and configured != tenant_id:
        raise HTTPException(
            503,
            "Odoo CRM bridge is not configured for the requested tenant",
        )


def idempotency_key(request: Request, correlation: str) -> str:
    return request.headers.get("Idempotency-Key", "").strip() or correlation


def as_response(result: BridgeResponse) -> JSONResponse:
    return JSONResponse(result.body, status_code=result.status_code)


async def call_bridge(coro) -> JSONResponse:
    """Run a ``OdooCrmBridgeClient`` call, mapping its errors to HTTP ones.

    A 4xx from the bridge (validation, tenant scoping, etc.) is relayed
    as-is via ``as_response`` -- only transport-level failures and the
    bridge's own 404 are translated here.
    """
    try:
        result = await coro
    except CrmBridgeNotConfigured as exc:
        raise HTTPException(503, str(exc)) from exc
    except CrmBridgeNotFound as exc:
        raise HTTPException(404, "not found") from exc
    except CrmBridgeUnavailable as exc:
        raise HTTPException(502, f"Odoo CRM bridge unavailable: {exc}") from exc
    return as_response(result)
