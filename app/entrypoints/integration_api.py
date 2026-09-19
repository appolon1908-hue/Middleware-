"""Authenticated integration and control surface."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.campaign_design_api import router as campaign_design_router
from app.api.v1.commands import router as commands_router
from app.api.v1.control import router as control_router
from app.api.v1.lead_reconciliation import router as lead_reconciliation_router
from app.api.v1.lead_automation import router as lead_automation_router
from app.api.v1.mappings import router as mappings_router
from app.api.v1.n8n_staging import router as n8n_staging_router
from app.api.v1.n8n_transport import router as n8n_transport_router
from app.api.v1.n8n_runtime import router as n8n_runtime_router
from app.api.v1.operations import router as operations_router
from app.api.v1.orchestration import router as orchestration_router
from app.api.v1.provider_webhooks import router as provider_webhooks_router
from app.api.v1.quarantine import router as quarantine_router
from app.api.v1.reports import router as reports_router
from app.api.v1.telephony import router as telephony_router
from app.api.v1.sales import router as sales_router
from app.api.v1.booking import router as booking_router
from app.api.v1.platform import router as platform_router
from app.api.internal.telnexa_events import router as telnexa_events_router
from app.api.internal.klyrow_events import router as klyrow_events_router
from app.api.v1.webphone import router as webphone_router
from app.entrypoints.runtime import add_api_runtime, run_api
from app.config import Settings as DomainSettings
from app.router_registry import mount_canonical_routers
from app.runtime import build_runtime as build_domain_runtime

SERVICE = "middleware-integration-api"
logger = logging.getLogger("codestra.integration_api")


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    """Own the canonical API runtime while keeping dependency failures unready."""

    # Configuration errors remain fatal. Only runtime dependency initialization
    # is allowed to degrade into a live-but-not-ready process.
    resolved = DomainSettings.from_env()
    runtime = None
    application.state.domain_runtime_startup_failed = False

    try:
        runtime = await build_domain_runtime(resolved)
        application.state.runtime = runtime
    except Exception:
        application.state.runtime = None
        application.state.domain_runtime_startup_failed = True
        logger.warning(
            "domain runtime unavailable during startup; readiness remains closed"
        )

    try:
        yield
    finally:
        if runtime is not None:
            await runtime.close()


routers = (
    commands_router,
    control_router,
    campaign_design_router,
    reports_router,
    operations_router,
    lead_reconciliation_router,
    lead_automation_router,
    orchestration_router,
    provider_webhooks_router,
    mappings_router,
    webphone_router,
    n8n_staging_router,
    n8n_transport_router,
    n8n_runtime_router,
    quarantine_router,
    telephony_router,
    sales_router,
    booking_router,
    platform_router,
    klyrow_events_router,
    telnexa_events_router,
)
app = FastAPI(
    title="Codestra Integration API",
    version="1.0.0",
    lifespan=lifespan,
    routes=[
        route
        for router in routers
        for route in router.routes
        if (
            not (getattr(route, "path", "") or "").startswith("/api/v1/events/")
            or getattr(route, "path", "")
            in {"/api/v1/events/telnexa", "/api/v1/events/klyrow"}
        )
    ],
)
mount_canonical_routers(app)
add_api_runtime(app, SERVICE)


if __name__ == "__main__":
    run_api(app, SERVICE)
