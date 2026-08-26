from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .config import ConfigurationError, Settings
from .contracts import WEBHOOK_ROUTES, WebhookRoute
from .runtime import Runtime, build_runtime
from .security import SecurityError
from .service import IngressError, PayloadTooLargeError, accept_webhook
from .storage import StorageError


def _correlation_id(request: Request) -> str:
    supplied = request.headers.get("X-Correlation-ID")
    if supplied and 1 <= len(supplied) <= 128:
        return supplied
    return str(uuid.uuid4())


def _error_response(
    request: Request,
    *,
    status_code: int,
    code: str,
    message: str,
    retryable: bool,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "correlation_id": _correlation_id(request),
                "retryable": retryable,
                "details": {},
            }
        },
    )


async def _read_limited_body(request: Request, maximum: int) -> bytes:
    raw_length = request.headers.get("Content-Length")
    if raw_length is not None:
        try:
            length = int(raw_length)
        except ValueError as exc:
            from .security import RequestValidationError

            raise RequestValidationError("Content-Length must be an integer") from exc
        if length < 0:
            from .security import RequestValidationError

            raise RequestValidationError("Content-Length must not be negative")
        if length > maximum:
            raise PayloadTooLargeError(f"request body exceeds {maximum} bytes")
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > maximum:
            raise PayloadTooLargeError(f"request body exceeds {maximum} bytes")
        body.extend(chunk)
    return bytes(body)


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
    async def security_error(request: Request, exc: SecurityError) -> JSONResponse:
        return _error_response(
            request,
            status_code=exc.status_code,
            code=exc.code,
            message=str(exc),
            retryable=exc.retryable,
        )

    @app.exception_handler(IngressError)
    async def ingress_error(request: Request, exc: IngressError) -> JSONResponse:
        return _error_response(
            request,
            status_code=exc.status_code,
            code=exc.code,
            message=str(exc),
            retryable=exc.retryable,
        )

    @app.exception_handler(StorageError)
    async def storage_error(request: Request, exc: StorageError) -> JSONResponse:
        return _error_response(
            request,
            status_code=503,
            code=exc.code,
            message="required persistence dependency is unavailable",
            retryable=exc.retryable,
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
            "source_sha": resolved.source_sha,
            "image_digest": resolved.image_digest,
            "schema_head": resolved.schema_head,
            "build_time": resolved.build_time,
        }

    def register(route: WebhookRoute) -> None:
        async def ingress(request: Request) -> JSONResponse:
            headers = {key.lower(): value for key, value in request.headers.items()}
            claims = await request.app.state.runtime.tokens.verify(
                headers.get("authorization", ""),
                expected_client_id=route.producer_client_id,
                required_scope=route.required_scope,
            )
            raw = await _read_limited_body(
                request,
                request.app.state.runtime.settings.max_request_body_bytes,
            )
            result, status_code = await accept_webhook(
                request.app.state.runtime,
                route,
                claims=claims,
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
