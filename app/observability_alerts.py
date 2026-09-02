from __future__ import annotations

import hashlib
import uuid
from contextlib import asynccontextmanager
from typing import Any, Literal, Mapping

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError as FastApiValidationError
from fastapi.responses import JSONResponse, Response
from pydantic import ValidationError

from .commands import CommandError
from .config import Settings
from .control_plane_auth import caller_for_authorization
from .models import EventEnvelope
from .observability_alert_contract import (
    ALERTMANAGER_CLIENT_ID,
    COMMAND_CAPABILITY,
    DELIVERY_CLIENT_ID,
    IDEMPOTENCY_RE,
    AlertDeliveryEvent,
    AlertPolicy,
    AlertSubmissionResponse,
    AlertmanagerWebhook,
    activation_enabled,
    build_command,
    load_policy,
    operation_view,
    require_alert_operation,
)
from .runtime import Runtime, build_runtime
from .security import (
    AuthorizationError,
    RequestValidationError,
    SecurityError,
    authorize_tenant,
)
from .storage import StorageError, canonical_payload_sha256


async def read_bounded_json(request: Request, *, maximum: int) -> bytes:
    content_type = request.headers.get("Content-Type", "").split(";", 1)[0]
    if content_type.strip().lower() != "application/json":
        raise RequestValidationError("Content-Type must be application/json")
    declared = request.headers.get("Content-Length")
    if declared:
        try:
            if int(declared) > maximum:
                raise RequestValidationError("request body exceeds the configured limit")
        except ValueError as exc:
            raise RequestValidationError("Content-Length is invalid") from exc
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > maximum:
            raise RequestValidationError("request body exceeds the configured limit")
    if not body:
        raise RequestValidationError("request body is required")
    return bytes(body)


async def authorize(
    request: Request,
    *,
    expected_client_id: str,
    scope_kind: Literal["command", "status"],
    policy: AlertPolicy,
) -> tuple[str, str]:
    tenant_id = request.headers.get("X-Tenant-ID", "").strip()
    correlation_id = request.headers.get("X-Correlation-ID", "").strip()
    if tenant_id != policy.tenant_id:
        raise AuthorizationError("observability tenant does not match the fixed policy")
    if not correlation_id or len(correlation_id) > 180:
        raise RequestValidationError("X-Correlation-ID is required")
    authorization = request.headers.get("Authorization", "")
    caller = caller_for_authorization(authorization)
    if caller.client_id != expected_client_id:
        raise AuthorizationError("caller is not authorized for observability alerts")
    required_scope = (
        caller.command_scope if scope_kind == "command" else caller.status_scope
    )
    claims = await request.app.state.runtime.tokens.verify(
        authorization,
        expected_client_id=caller.client_id,
        required_scope=required_scope,
    )
    authorize_tenant(claims, tenant_id)
    subject = claims.get("sub")
    if not isinstance(subject, str) or not subject:
        raise AuthorizationError("token subject is required")
    return subject, correlation_id


def problem(
    error: Exception,
    request: Request,
    status_code: int,
    code: str,
) -> JSONResponse:
    correlation_id = request.headers.get("X-Correlation-ID", "")
    headers = {"X-Correlation-ID": correlation_id} if correlation_id else None
    return JSONResponse(
        status_code=status_code,
        content={
            "code": code,
            "message": str(error),
            "correlation_id": correlation_id,
            "retryable": bool(getattr(error, "retryable", False)),
        },
        headers=headers,
    )


def create_app(
    *,
    settings: Settings | None = None,
    runtime: Runtime | None = None,
    policy: AlertPolicy | None = None,
    env: Mapping[str, str] | None = None,
) -> FastAPI:
    active_settings = settings or Settings.from_env()
    active_policy = policy or load_policy()
    delivery_enabled = activation_enabled(active_settings, env=env)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        active = runtime or await build_runtime(active_settings)
        if active.commands is None:
            raise StorageError("command ledger is unavailable")
        active.commands.policies.capabilities[COMMAND_CAPABILITY] = delivery_enabled
        app.state.runtime = active
        try:
            yield
        finally:
            if runtime is None:
                await active.close()

    app = FastAPI(
        title="Codestra Middleware Observability Alert API",
        version=active_settings.app_version,
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
    )

    @app.exception_handler(SecurityError)
    async def security_error(request: Request, exc: SecurityError) -> JSONResponse:
        return problem(exc, request, exc.status_code, exc.code)

    @app.exception_handler(CommandError)
    async def command_error(request: Request, exc: CommandError) -> JSONResponse:
        return problem(exc, request, exc.status_code, exc.code)

    @app.exception_handler(StorageError)
    async def storage_error(request: Request, exc: StorageError) -> JSONResponse:
        return problem(exc, request, 503, exc.code)

    @app.exception_handler(FastApiValidationError)
    async def validation_error(
        request: Request,
        exc: FastApiValidationError,
    ) -> JSONResponse:
        return problem(
            RequestValidationError("request validation failed"),
            request,
            422,
            "validation_failed",
        )

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "healthy", "service": "middleware-observability-alerts"}

    @app.head("/health")
    async def health_head() -> Response:
        return Response(status_code=200)

    @app.get("/readiness")
    async def readiness(request: Request) -> JSONResponse:
        report = await request.app.state.runtime.readiness()
        return JSONResponse(
            status_code=200 if report.ready else 503,
            content={"ready": report.ready, "components": report.components},
        )

    @app.get("/version")
    async def version() -> dict[str, str]:
        return {
            "service": "middleware-observability-alerts",
            "environment": active_settings.app_env,
            "release_id": active_settings.release_id,
            "git_sha": active_settings.source_sha,
            "image_digest": active_settings.image_digest,
            "build_time": active_settings.build_time,
            "schema_version": active_settings.schema_head,
            "configuration_checksum": active_settings.configuration_checksum,
        }

    @app.get("/capabilities")
    async def capabilities() -> dict[str, Any]:
        return {
            "service": "middleware-observability-alerts",
            "default_policy": "DENY",
            "normal_delivery_path": active_policy.normal_delivery_path,
            "direct_smtp_allowed": False,
            COMMAND_CAPABILITY: delivery_enabled,
            "recipient_policy_id": active_policy.recipient_policy_id,
            "sender_policy_id": active_policy.sender_policy_id,
        }

    @app.post("/v1/integrations/alertmanager/events")
    @app.post("/v1/observability/alerts", deprecated=True)
    async def submit_alerts(request: Request) -> JSONResponse:
        actor, correlation_id = await authorize(
            request,
            expected_client_id=ALERTMANAGER_CLIENT_ID,
            scope_kind="command",
            policy=active_policy,
        )
        supplied_idempotency = request.headers.get("Idempotency-Key", "").strip()
        if not IDEMPOTENCY_RE.fullmatch(supplied_idempotency):
            raise RequestValidationError("Idempotency-Key is required and malformed")
        raw = await read_bounded_json(request, maximum=active_policy.max_body_bytes)
        try:
            webhook = AlertmanagerWebhook.model_validate_json(raw)
        except ValidationError as exc:
            raise RequestValidationError("Alertmanager payload is invalid") from exc
        if webhook.receiver != active_policy.receiver:
            raise AuthorizationError("Alertmanager receiver is not approved")
        if len(webhook.alerts) > active_policy.max_alerts_per_request:
            raise RequestValidationError("too many alerts in one request")

        for alert in webhook.alerts:
            if alert.labels["environment"] not in active_policy.allowed_environments:
                raise AuthorizationError("alert environment is not approved")
            if alert.labels["severity"] not in active_policy.allowed_severities:
                raise AuthorizationError("alert severity is not approved")

        operations = []
        for alert in webhook.alerts:
            command = build_command(
                policy=active_policy,
                alert=alert,
                receiver=webhook.receiver,
                actor=actor,
                correlation_id=correlation_id,
                request_idempotency_key=supplied_idempotency,
            )
            operation = await request.app.state.runtime.commands.submit(
                command,
                authenticated_subject=actor,
                authenticated_client_id=ALERTMANAGER_CLIENT_ID,
            )
            operations.append(operation_view(operation, alert))

        response = AlertSubmissionResponse(
            policy_id=active_policy.policy_id,
            recipient_policy_id=active_policy.recipient_policy_id,
            sender_policy_id=active_policy.sender_policy_id,
            operations=operations,
        )
        duplicate = all(item.duplicate for item in operations)
        return JSONResponse(
            status_code=200 if duplicate else 202,
            content=response.model_dump(mode="json"),
            headers={"X-Correlation-ID": correlation_id},
        )

    @app.get("/v1/observability/alerts/{operation_id}")
    async def get_alert(operation_id: uuid.UUID, request: Request) -> JSONResponse:
        _, correlation_id = await authorize(
            request,
            expected_client_id=ALERTMANAGER_CLIENT_ID,
            scope_kind="status",
            policy=active_policy,
        )
        operation = await request.app.state.runtime.commands.get(
            active_policy.tenant_id,
            operation_id,
        )
        require_alert_operation(operation)
        return JSONResponse(
            content=operation.model_dump(mode="json"),
            headers={"X-Correlation-ID": correlation_id},
        )

    @app.get("/v1/observability/alerts/{operation_id}/events")
    async def get_alert_events(
        operation_id: uuid.UUID,
        request: Request,
    ) -> JSONResponse:
        _, correlation_id = await authorize(
            request,
            expected_client_id=ALERTMANAGER_CLIENT_ID,
            scope_kind="status",
            policy=active_policy,
        )
        operation = await request.app.state.runtime.commands.get(
            active_policy.tenant_id,
            operation_id,
        )
        require_alert_operation(operation)
        events = await request.app.state.runtime.commands.list_events(
            active_policy.tenant_id,
            operation_id,
            limit=100,
        )
        return JSONResponse(
            content={"items": [event.model_dump(mode="json") for event in events]},
            headers={"X-Correlation-ID": correlation_id},
        )

    @app.post("/v1/observability/alert-delivery-events")
    async def accept_delivery_event(request: Request) -> JSONResponse:
        actor, correlation_id = await authorize(
            request,
            expected_client_id=DELIVERY_CLIENT_ID,
            scope_kind="command",
            policy=active_policy,
        )
        supplied_idempotency = request.headers.get("Idempotency-Key", "").strip()
        if not IDEMPOTENCY_RE.fullmatch(supplied_idempotency):
            raise RequestValidationError("Idempotency-Key is required and malformed")
        raw = await read_bounded_json(request, maximum=65_536)
        try:
            event = AlertDeliveryEvent.model_validate_json(raw)
        except ValidationError as exc:
            raise RequestValidationError("alert delivery event is invalid") from exc
        operation = await request.app.state.runtime.commands.get(
            active_policy.tenant_id,
            event.operation_id,
        )
        require_alert_operation(operation)
        if supplied_idempotency != event.event_id:
            raise RequestValidationError(
                "Idempotency-Key must equal the delivery event_id"
            )
        envelope = EventEnvelope(
            event_id=event.event_id,
            event_type="codestra.observability.alert_delivery.v1",
            event_version="1.0",
            occurred_at=event.occurred_at,
            received_at=event.occurred_at,
            source=DELIVERY_CLIENT_ID,
            tenant_id=active_policy.tenant_id,
            correlation_id=operation.correlation_id,
            causation_id=str(event.operation_id),
            idempotency_key=event.event_id,
            payload={**event.model_dump(mode="json"), "actor": actor},
            metadata={
                "recipient_policy_id": active_policy.recipient_policy_id,
                "sender_policy_id": active_policy.sender_policy_id,
            },
        )
        semantic = canonical_payload_sha256(envelope.model_dump(mode="json"))
        result = await request.app.state.runtime.inbox.accept(
            envelope,
            producer_client_id=DELIVERY_CLIENT_ID,
            body_sha256=hashlib.sha256(raw).hexdigest(),
            semantic_sha256=semantic,
        )
        return JSONResponse(
            status_code=200 if result.duplicate else 202,
            content={
                **result.model_dump(mode="json"),
                "operation_id": str(event.operation_id),
                "authoritative_completion": "provider-readback",
            },
            headers={"X-Correlation-ID": correlation_id},
        )

    return app
