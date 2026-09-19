"""Canonical router registry shared by every Middleware application factory."""

from __future__ import annotations

from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.v1.activity import router as activity_router
from app.api.v1.automation import router as automation_router
from app.api.v1.agent_provisioning import router as agent_provisioning_router
from app.api.v1.agent_provisioning_reads import (
    router as agent_provisioning_reads_router,
)
from app.api.v1.calls import router as calls_router
from app.api.v1.callbacks import router as callbacks_router
from app.api.v1.campaigns import router as campaigns_router
from app.api.v1.integrations import router as integrations_router
from app.api.v1.observability_sync import router as observability_sync_router
from app.api.v1.presence import router as presence_router
from app.api.v1.queues import router as queues_router
from app.api.v1.session_context import router as session_context_router
from app.api.v1.tenants import router as tenants_router
from app.email_production_control import router as email_production_router
from app.commands import CommandError
from app.communications import CommunicationsError
from app.monitoring.routes import router as monitoring_router
from app.automation_v2 import v2_router as automation_v2_router
from app.n8n_control_plane import router as n8n_control_plane_router
from app.security import SecurityError
from app.service import IngressError
from app.storage import StorageError
from app.webhook_api import odoo_event_router


CANONICAL_ROUTERS = (
    automation_v2_router,
    automation_router,
    callbacks_router,
    email_production_router,
    agent_provisioning_router,
    agent_provisioning_reads_router,
    session_context_router,
    calls_router,
    activity_router,
    presence_router,
    queues_router,
    tenants_router,
    campaigns_router,
    monitoring_router,
    observability_sync_router,
    integrations_router,
    odoo_event_router,
)

# Deprecated routers that exist only on the in-process monolith. The canonical
# edge contract classifies their paths as ``denied``: Kong and Caddy answer 404,
# and the deployed ``app.entrypoints.integration_api`` never mounts them (the
# release endpoint audit fails if a denied path is mounted there). They stay on
# the monolith until their published sunset so existing in-process callers keep
# receiving Deprecation/Sunset/Link metadata; new use is prohibited.
LEGACY_MONOLITH_ONLY_ROUTERS = (n8n_control_plane_router,)


def mount_canonical_routers(app: FastAPI) -> None:
    """Mount the complete contract-backed route set exactly once."""

    async def domain_error(request: Request, exc: Exception) -> JSONResponse:
        correlation_id = (
            getattr(request.state, "correlation_id", None)
            or request.headers.get("X-Correlation-ID")
            or str(uuid4())
        )
        status_code = int(getattr(exc, "status_code", 500))
        code = str(getattr(exc, "code", "internal_error"))
        retryable = bool(getattr(exc, "retryable", status_code >= 500))
        message = (
            "required persistence dependency is unavailable"
            if isinstance(exc, StorageError)
            else str(exc)
        )
        return JSONResponse(
            status_code=status_code,
            content={
                "error": {
                    "code": code,
                    "message": message,
                    "correlation_id": correlation_id,
                    "retryable": retryable,
                    "details": {},
                }
            },
            headers={"X-Correlation-ID": correlation_id},
        )

    for error_type in (
        SecurityError,
        IngressError,
        StorageError,
        CommandError,
        CommunicationsError,
    ):
        app.add_exception_handler(error_type, domain_error)
    for router in CANONICAL_ROUTERS:
        app.include_router(router)


def mount_legacy_monolith_routers(app: FastAPI) -> None:
    """Mount the deprecated, edge-denied aliases on a monolith application only."""

    for router in LEGACY_MONOLITH_ONLY_ROUTERS:
        app.include_router(router)
