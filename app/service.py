from __future__ import annotations

import json
from typing import Any

from pydantic import ValidationError

from .contracts import WebhookRoute
from .models import EventEnvelope, IngressResult
from .replay import ReplayBusy
from .runtime import Runtime
from .security import RequestValidationError, verify_signed_request
from .storage import ReplayConflict


class IngressError(RuntimeError):
    status_code = 400


class EventTypeError(IngressError):
    status_code = 422


class ReplayConflictError(IngressError):
    status_code = 409


class ProcessingConflictError(IngressError):
    status_code = 409


async def accept_webhook(
    runtime: Runtime,
    route: WebhookRoute,
    *,
    method: str,
    path: str,
    raw_body: bytes,
    headers: dict[str, str],
) -> tuple[IngressResult, int]:
    runtime.tokens.verify(
        headers.get("authorization", ""),
        expected_client_id=route.producer_client_id,
        required_scope=route.required_scope,
    )
    signed = verify_signed_request(
        settings=runtime.settings,
        method=method,
        path=path,
        body=raw_body,
        headers=headers,
        expected_source_client_id=route.producer_client_id,
    )
    try:
        payload: Any = json.loads(raw_body)
        envelope = EventEnvelope.model_validate(payload)
    except (json.JSONDecodeError, ValidationError) as exc:
        raise RequestValidationError("body does not match the canonical event envelope") from exc

    if envelope.type not in route.event_types:
        raise EventTypeError("event type is not allowed for this route")
    if signed.event_type != envelope.type:
        raise RequestValidationError("X-Codestra-Event-Type does not match body")
    if signed.event_id != envelope.id:
        raise RequestValidationError("X-Codestra-Event-Id does not match body")
    if signed.tenant_id != envelope.tenant_id:
        raise RequestValidationError("X-Codestra-Tenant-Id does not match body")
    if signed.correlation_id != envelope.correlation_id:
        raise RequestValidationError("X-Correlation-Id does not match body")
    if envelope.idempotency_key != signed.idempotency_key:
        raise RequestValidationError("body idempotency_key does not match headers")
    if envelope.source != f"urn:codestra:{route.producer_client_id}":
        raise RequestValidationError("body source does not match route producer")

    token: str | None = None
    try:
        token = await runtime.replay.acquire(envelope.tenant_id, envelope.id)
        try:
            result = await runtime.inbox.accept(
                envelope,
                producer_client_id=route.producer_client_id,
                body_sha256=signed.body_sha256,
            )
        except ReplayConflict as exc:
            raise ReplayConflictError(str(exc)) from exc
    except ReplayBusy as exc:
        raise ProcessingConflictError(str(exc)) from exc
    finally:
        if token is not None:
            await runtime.replay.release(envelope.tenant_id, envelope.id, token)

    return result, 200 if result.duplicate else 202
