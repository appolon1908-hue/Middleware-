from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import AsyncIterator
from uuid import UUID

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError as FastApiValidationError
from fastapi.responses import JSONResponse, Response

from .config import ConfigurationError, Settings
from .commands import CommandEnvelope, CommandError
from .contracts import WEBHOOK_ROUTES, WebhookRoute
from .n8n_control_plane import router as n8n_control_plane_router
from .observability import (
    MiddlewareObservability,
    safe_correlation_id,
    safe_traceparent,
)
from .runtime import Runtime, build_runtime
from .runtime_safety import runtime_safety_readback
from .security import SecurityError
from .service import IngressError, PayloadTooLargeError, accept_webhook
from .storage import StorageError


def _correlation_id(request: Request) -> str:
    assigned = getattr(request.state, "correlation_id", None)
    if isinstance(assigned, str):
        return assigned
    supplied = safe_correlation_id(request.headers.get("X-Correlation-ID"))
    if supplied is not None:
        return supplied
    return str(uuid.uuid4())


def _operation(request: Request) -> str:
    route = request.scope.get("route")
    template = getattr(route, "path", None)
    if isinstance(template, str) and template.startswith("/"):
        return template
    return "unmatched"


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
    telemetry = MiddlewareObservability(resolved)
    app.state.observability = telemetry
    app.include_router(n8n_control_plane_router)

    @app.middleware("http")
    async def observe_request(request: Request, call_next):
        request.state.correlation_id = (
            safe_correlation_id(request.headers.get("X-Correlation-ID"))
            or str(uuid.uuid4())
        )
        request.state.traceparent = safe_traceparent(
            request.headers.get("traceparent")
        )
        started = telemetry.start_request()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers["X-Correlation-ID"] = request.state.correlation_id
            if request.state.traceparent is not None:
                response.headers["traceparent"] = request.state.traceparent
            return response
        finally:
            telemetry.finish_request(
                started=started,
                operation=_operation(request),
                method=request.method,
                status_code=status_code,
                correlation_id=request.state.correlation_id,
                traceparent=request.state.traceparent,
            )

    @app.exception_handler(SecurityError)
    async def security_error(request: Request, exc: SecurityError) -> JSONResponse:
        request.app.state.observability.record_auth_denial(
            _operation(request),
            exc.code,
        )
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

    @app.exception_handler(CommandError)
    async def command_error(request: Request, exc: CommandError) -> JSONResponse:
        return _error_response(
            request,
            status_code=exc.status_code,
            code=exc.code,
            message=str(exc),
            retryable=exc.retryable,
        )

    @app.exception_handler(FastApiValidationError)
    async def validation_error(
        request: Request,
        exc: FastApiValidationError,
    ) -> JSONResponse:
        return _error_response(
            request,
            status_code=400,
            code="invalid_request",
            message="request does not match the canonical API contract",
            retryable=False,
        )

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {
            "status": "ok",
            "service": "middleware-api",
            "component": "api",
        }

    @app.get("/ready")
    async def ready(request: Request) -> JSONResponse:
        report = await request.app.state.runtime.readiness()
        request.app.state.observability.record_readiness(report.components)
        return JSONResponse(
            status_code=200 if report.ready else 503,
            content={
                "status": "ready" if report.ready else "not_ready",
                "service": "middleware-api",
                "component": "api",
                "environment": resolved.app_env,
                "release_sha": resolved.source_sha,
                "image_digest": resolved.image_digest,
                "schema_or_migration_head": resolved.schema_head,
                "checked_at": datetime.now(UTC).isoformat(),
                "components": report.components,
            },
        )

    @app.get("/metrics")
    async def metrics(request: Request) -> Response:
        await request.app.state.runtime.tokens.verify(
            request.headers.get("Authorization", ""),
            expected_client_id="monitoring-readonly",
            required_scope="metrics.read",
        )
        report = await request.app.state.runtime.readiness()
        request.app.state.observability.record_readiness(report.components)
        body, media_type = request.app.state.observability.render()
        return Response(content=body, headers={"Content-Type": media_type})

    @app.get("/version")
    async def version() -> dict[str, str]:
        return {
            "service": "middleware-api",
            "version": resolved.app_version,
            "environment": resolved.app_env,
            "runtime_profile_id": (
                resolved.runtime_profile_id or "local-unlocked"
            ),
            "source_sha": resolved.source_sha,
            "image_digest": resolved.image_digest,
            "schema_head": resolved.schema_head,
            "build_time": resolved.build_time,
        }

    @app.get("/v1/runtime/safety")
    async def runtime_safety(request: Request) -> dict[str, object]:
        await request.app.state.runtime.tokens.verify(
            request.headers.get("Authorization", ""),
            expected_client_id="monitoring-readonly",
            required_scope="health.read",
        )
        return runtime_safety_readback(request.app.state.runtime.settings)

    @app.post("/v1/commands")
    async def submit_command(
        command: CommandEnvelope,
        request: Request,
    ) -> JSONResponse:
        active = request.app.state.runtime
        if active.commands is None:
            raise StorageError("command ledger is unavailable")
        claims = await active.tokens.verify(
            request.headers.get("Authorization", ""),
            expected_client_id="kong-gateway",
            required_scope="middleware.request.forward",
        )
        from .security import authorize_tenant

        authorize_tenant(claims, command.tenant_id)
        if request.headers.get("X-Tenant-ID") != command.tenant_id:
            from .security import RequestValidationError

            raise RequestValidationError("X-Tenant-ID does not match command tenant")
        if request.headers.get("X-Correlation-ID") != command.correlation_id:
            from .security import RequestValidationError

            raise RequestValidationError(
                "X-Correlation-ID does not match command correlation_id"
            )
        if request.headers.get("Idempotency-Key") != command.idempotency_key:
            from .security import RequestValidationError

            raise RequestValidationError(
                "Idempotency-Key does not match command idempotency_key"
            )
        subject = claims.get("sub")
        if not isinstance(subject, str) or not subject:
            from .security import AuthorizationError

            raise AuthorizationError("token subject is required for commands")
        operation = await active.commands.submit(
            command,
            authenticated_subject=subject,
        )
        status_code = 200 if operation.duplicate else 202
        return JSONResponse(
            status_code=status_code,
            content=operation.model_dump(mode="json"),
            headers={
                "Location": f"/v1/operations/{operation.command_id}",
                "X-Correlation-ID": operation.correlation_id,
            },
        )

    @app.get("/v1/operations/{command_id}")
    async def get_operation(command_id: UUID, request: Request) -> JSONResponse:
        active = request.app.state.runtime
        if active.commands is None:
            raise StorageError("command ledger is unavailable")
        claims = await active.tokens.verify(
            request.headers.get("Authorization", ""),
            expected_client_id="kong-gateway",
            required_scope="middleware.status.read",
        )
        tenant_id = request.headers.get("X-Tenant-ID", "")
        from .security import authorize_tenant

        authorize_tenant(claims, tenant_id)
        operation = await active.commands.get(tenant_id, command_id)
        return JSONResponse(
            status_code=200,
            content=operation.model_dump(mode="json"),
            headers={"X-Correlation-ID": operation.correlation_id},
        )

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
