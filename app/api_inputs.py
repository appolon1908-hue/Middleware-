from __future__ import annotations

from typing import Any

from fastapi import Request

from .control_plane_auth import ControlPlaneCaller, caller_for_authorization
from .security import RequestValidationError, authorize_tenant


def reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON field: {key}")
        value[key] = item
    return value


def required_header(
    request: Request,
    name: str,
    *,
    minimum: int,
    maximum: int,
) -> str:
    values = request.headers.getlist(name)
    if len(values) != 1:
        raise RequestValidationError(f"{name} must be provided exactly once")
    value = values[0]
    if not minimum <= len(value) <= maximum:
        raise RequestValidationError(f"{name} is malformed")
    return value


def optional_header(
    request: Request,
    name: str,
    *,
    minimum: int,
    maximum: int,
) -> str | None:
    values = request.headers.getlist(name)
    if len(values) > 1:
        raise RequestValidationError(f"{name} must be provided at most once")
    if not values:
        return None
    value = values[0]
    if not minimum <= len(value) <= maximum:
        raise RequestValidationError(f"{name} is malformed")
    return value


def authorization_header(request: Request) -> str:
    values = request.headers.getlist("Authorization")
    if len(values) > 1:
        raise RequestValidationError("Authorization must be provided at most once")
    value = values[0] if values else ""
    if len(value) > 8192:
        raise RequestValidationError("Authorization is malformed")
    return value


async def authenticated_tenant(
    request: Request,
    *,
    mutation: bool = False,
) -> tuple[ControlPlaneCaller, dict[str, Any], str]:
    authorization = authorization_header(request)
    caller = caller_for_authorization(authorization)
    claims = await request.app.state.runtime.tokens.verify(
        authorization,
        expected_client_id=caller.client_id,
        required_scope=caller.command_scope if mutation else caller.status_scope,
    )
    tenant = required_header(
        request,
        "X-Tenant-ID",
        minimum=1,
        maximum=128,
    )
    authorize_tenant(claims, tenant)
    return caller, claims, tenant
