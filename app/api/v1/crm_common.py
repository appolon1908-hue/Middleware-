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
