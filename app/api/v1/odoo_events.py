"""Signed Odoo agent-event ingress for the production integration API."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import math
import time
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.jwt_auth import JWTAuthError, KeycloakValidator
from app.db.session import get_session
from app.models import EventEnvelope
from app.odoo_agent_events import (
    ODOO_EVENTS_PATH,
    ODOO_EVENT_ROUTE,
    ODOO_EVENT_TYPES,
    OdooAgentEventConflict,
    OdooAgentEventPersistenceError,
    OdooAgentEventValidationError,
    persist_odoo_agent_event,
    validate_odoo_agent_event,
)


router = APIRouter(tags=["odoo-events"])


def _request_headers(request: Request) -> dict[str, str]:
    return {
        key.lower(): value.strip()
        for key, value in request.headers.items()
    }


def _require_headers(headers: Mapping[str, str]) -> None:
    required = (
        "authorization",
        "content-type",
        "idempotency-key",
        "x-codestra-event-id",
        "x-codestra-event-type",
        "x-codestra-source",
        "x-codestra-tenant-id",
        "x-codestra-timestamp",
        "x-codestra-signature",
        "x-correlation-id",
    )
    missing = [name for name in required if not headers.get(name)]
    if missing:
        raise HTTPException(
            status_code=400,
            detail="missing required headers: " + ", ".join(missing),
        )


def _authorized_parties() -> frozenset[str]:
    return frozenset(
        value.strip()
        for value in settings.keycloak_authorized_parties.split(",")
        if value.strip()
    )


def _validate_token_lifetime(claims: Mapping[str, Any]) -> None:
    issued_at = claims.get("iat")
    expires_at = claims.get("exp")
    if (
        isinstance(issued_at, bool)
        or not isinstance(issued_at, (int, float))
        or isinstance(expires_at, bool)
        or not isinstance(expires_at, (int, float))
    ):
        raise HTTPException(
            status_code=401,
            detail="machine token lifetime is invalid",
        )
    issued = float(issued_at)
    expires = float(expires_at)
    if (
        not math.isfinite(issued)
        or not math.isfinite(expires)
        or expires <= issued
        or expires - issued > 300
    ):
        raise HTTPException(
            status_code=401,
            detail="machine token lifetime exceeds policy",
        )


async def _authenticate(headers: Mapping[str, str]) -> dict[str, Any]:
    authorization = headers.get("authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(
            status_code=401,
            detail="Authorization must be a Bearer token",
        )
    parties = _authorized_parties()
    if not all(
        (
            settings.keycloak_issuer,
            settings.keycloak_audience,
            settings.keycloak_jwks_url,
            parties,
        )
    ):
        raise HTTPException(status_code=503, detail="authorization unavailable")
    validator = KeycloakValidator(
        issuer=settings.keycloak_issuer,
        audience=settings.keycloak_audience,
        jwks_url=settings.keycloak_jwks_url,
        authorized_parties=parties,
        required_scopes=frozenset({ODOO_EVENT_ROUTE.required_scope}),
    )
    try:
        claims = await asyncio.to_thread(validator.validate, token.strip())
    except JWTAuthError as exc:
        raise HTTPException(status_code=401, detail="bearer token is invalid") from exc
    _validate_token_lifetime(claims)
    return claims


def _authorized_tenant(claims: Mapping[str, Any], tenant_id: str) -> None:
    authorized: set[str] = set()
    single = claims.get("tenant_id")
    if isinstance(single, str) and single.strip():
        authorized.add(single.strip())
    multiple = claims.get("tenant_ids")
    if isinstance(multiple, list) and all(
        isinstance(item, str) for item in multiple
    ):
        authorized.update(item.strip() for item in multiple if item.strip())
    if "*" in authorized or tenant_id not in authorized:
        raise HTTPException(
            status_code=403,
            detail="bearer token is not authorized for this tenant",
        )


def _parse_timestamp(raw: str) -> float:
    try:
        observed = float(raw)
    except ValueError:
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail="X-Codestra-Timestamp must be epoch seconds or ISO-8601",
            ) from exc
        if parsed.tzinfo is None:
            raise HTTPException(
                status_code=400,
                detail="X-Codestra-Timestamp must include timezone",
            )
        observed = parsed.astimezone(timezone.utc).timestamp()
    if not math.isfinite(observed):
        raise HTTPException(
            status_code=400,
            detail="X-Codestra-Timestamp must be finite",
        )
    return observed


def _hmac_key() -> bytes:
    try:
        return settings.odoo_events_hmac_key
    except ValueError as exc:
        raise HTTPException(
            status_code=503,
            detail="webhook authentication is unavailable",
        ) from exc


def _canonical_signing_bytes(
    *,
    timestamp: str,
    event_id: str,
    body_sha256: str,
) -> bytes:
    return "\n".join(
        (
            "v1",
            "POST",
            ODOO_EVENTS_PATH,
            timestamp,
            event_id,
            ODOO_EVENT_ROUTE.producer_client_id,
            body_sha256,
        )
    ).encode("utf-8")


def _verify_signed_request(
    headers: Mapping[str, str],
    body: bytes,
) -> str:
    _require_headers(headers)
    if (
        headers["content-type"].split(";", 1)[0].strip().lower()
        != "application/json"
    ):
        raise HTTPException(
            status_code=400,
            detail="Content-Type must be application/json",
        )
    if headers["x-codestra-source"] != ODOO_EVENT_ROUTE.producer_client_id:
        raise HTTPException(
            status_code=403,
            detail="X-Codestra-Source does not match the Odoo route",
        )
    if headers["idempotency-key"] != headers["x-codestra-event-id"]:
        raise HTTPException(
            status_code=400,
            detail="Idempotency-Key must equal X-Codestra-Event-Id",
        )
    timestamp = headers["x-codestra-timestamp"]
    if (
        abs(time.time() - _parse_timestamp(timestamp))
        > settings.signature_ttl_seconds
    ):
        raise HTTPException(
            status_code=401,
            detail="webhook timestamp is outside the allowed clock skew",
        )
    body_sha256 = hashlib.sha256(body).hexdigest()
    expected = hmac.new(
        _hmac_key(),
        _canonical_signing_bytes(
            timestamp=timestamp,
            event_id=headers["x-codestra-event-id"],
            body_sha256=body_sha256,
        ),
        hashlib.sha256,
    ).hexdigest()
    supplied = headers["x-codestra-signature"]
    prefix = "sha256="
    if not supplied.startswith(prefix):
        raise HTTPException(
            status_code=401,
            detail="X-Codestra-Signature must use sha256=<hex>",
        )
    supplied_hex = supplied[len(prefix) :].lower()
    if len(supplied_hex) != 64 or any(
        character not in "0123456789abcdef" for character in supplied_hex
    ):
        raise HTTPException(
            status_code=401,
            detail="X-Codestra-Signature contains invalid hex",
        )
    if not hmac.compare_digest(supplied_hex, expected):
        raise HTTPException(
            status_code=401,
            detail="webhook signature is invalid",
        )
    return body_sha256


def _parse_envelope(body: bytes) -> EventEnvelope:
    try:
        return EventEnvelope.model_validate(json.loads(body))
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        TypeError,
        ValidationError,
    ) as exc:
        raise HTTPException(
            status_code=400,
            detail="body does not match the canonical event envelope",
        ) from exc


def _check_identity(
    envelope: EventEnvelope,
    headers: Mapping[str, str],
) -> None:
    if envelope.event_type not in ODOO_EVENT_TYPES:
        raise HTTPException(
            status_code=422,
            detail="event type is not allowed for the Odoo route",
        )
    identities = (
        ("x-codestra-event-id", envelope.event_id),
        ("x-codestra-event-type", envelope.event_type),
        ("x-codestra-source", envelope.source),
        ("x-codestra-tenant-id", envelope.tenant_id),
        ("x-correlation-id", envelope.correlation_id),
        ("idempotency-key", envelope.idempotency_key),
    )
    for name, expected in identities:
        if headers.get(name) != expected:
            raise HTTPException(
                status_code=400,
                detail=f"{name} does not match the event envelope",
            )
    if envelope.source != ODOO_EVENT_ROUTE.producer_client_id:
        raise HTTPException(
            status_code=403,
            detail="event source does not match the Odoo route",
        )


@router.post(ODOO_EVENTS_PATH)
async def ingest_odoo_event(
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    headers = _request_headers(request)
    claims = await _authenticate(headers)
    body = await request.body()
    if len(body) > settings.request_max_bytes:
        raise HTTPException(status_code=413, detail="request too large")
    body_sha256 = _verify_signed_request(headers, body)
    envelope = _parse_envelope(body)
    _check_identity(envelope, headers)
    _authorized_tenant(claims, envelope.tenant_id)
    try:
        validate_odoo_agent_event(envelope)
        result = await persist_odoo_agent_event(
            session,
            envelope,
            body_sha256=body_sha256,
        )
    except OdooAgentEventValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except OdooAgentEventConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except OdooAgentEventPersistenceError as exc:
        raise HTTPException(
            status_code=503,
            detail="durable event acceptance is unavailable",
        ) from exc
    response.status_code = 200 if result.duplicate else 202
    response.headers["X-Idempotent-Replay"] = str(result.duplicate).lower()
    return result.model_dump(mode="json")
