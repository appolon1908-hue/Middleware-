from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .config import ConfigurationError, Settings
from .contracts import WEBHOOK_ROUTES, WebhookRoute
from .runtime import Runtime, build_runtime
from .security import SecurityError
from .service import IngressError, accept_webhook
from .storage import StorageError


def create_app(
    *,
    settings: Settings | None = None,
    runtime: Runtime | None = None,
) -> FastAPI:
    resolved = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        active = runtime or await build_runtime(resolved)
        app.state.runtime = active
        try:
            yield
        finally:
            if runtime is None:
                await active.close()

    app = FastAPI(
        title="Codestra Middleware API",
        version=resolved.app_version,
        docs_url=None if resolved.app_env in {"staging", "production"} else "/docs",
        redoc_url=None,
        lifespan=lifespan,
    )

    @app.exception_handler(SecurityError)
    async def security_error(_: Request, exc: SecurityError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": exc.__class__.__name__, "detail": str(exc)},
        )

    @app.exception_handler(IngressError)
    async def ingress_error(_: Request, exc: IngressError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": exc.__class__.__name__, "detail": str(exc)},
        )

    @app.exception_handler(StorageError)
    async def storage_error(_: Request, exc: StorageError) -> JSONResponse:
        return JSONResponse(
            status_code=503,
            content={"error": "StorageUnavailable", "detail": str(exc)},
        )

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/ready")
    async def ready(request: Request) -> JSONResponse:
        is_ready = await request.app.state.runtime.ready()
        return JSONResponse(
            status_code=200 if is_ready else 503,
            content={"status": "ready" if is_ready else "not_ready"},
        )

    @app.get("/version")
    async def version() -> dict[str, str]:
        return {
            "service": "middleware-api",
            "version": resolved.app_version,
            "environment": resolved.app_env,
        }

    def register(route: WebhookRoute) -> None:
        async def ingress(request: Request) -> JSONResponse:
            raw = await request.body()
            headers = {key.lower(): value for key, value in request.headers.items()}
            result, status_code = await accept_webhook(
                request.app.state.runtime,
                route,
                method=request.method,
                path=request.url.path,
                raw_body=raw,
                headers=headers,
            )
            return JSONResponse(
                status_code=status_code,
                content=result.model_dump(mode="json"),
            )

        app.add_api_route(
            route.path,
            ingress,
            methods=["POST"],
            name=f"ingress-{route.producer_client_id}-{route.path.rsplit('/', 1)[-1]}",
        )

    for webhook_route in WEBHOOK_ROUTES:
        register(webhook_route)

    return app


try:
    app = create_app()
except ConfigurationError:
    app = None
