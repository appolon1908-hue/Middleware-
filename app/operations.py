from __future__ import annotations

import base64
import json
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from .commands import CommandState
from .control_plane_auth import caller_for_authorization
from .security import RequestValidationError, authorize_tenant
from .storage import StorageError

router = APIRouter(prefix="/v1/operations", tags=["operations"])


def _encode_cursor(kind: str, values: list[Any]) -> str:
    raw = json.dumps({"v": 1, "kind": kind, "position": values}, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _decode_cursor(value: str | None, kind: str) -> list[Any] | None:
    if value is None: return None
    try:
        raw = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
        data = json.loads(raw)
    except (ValueError, UnicodeError, json.JSONDecodeError) as exc:
        raise RequestValidationError("cursor is malformed") from exc
    if not isinstance(data, dict) or set(data) != {"v", "kind", "position"} or data["v"] != 1 or data["kind"] != kind or not isinstance(data["position"], list) or len(data["position"]) != 2:
        raise RequestValidationError("cursor is malformed")
    return data["position"]


async def _context(request: Request):
    active = request.app.state.runtime
    if active.commands is None: raise StorageError("command ledger is unavailable")
    tenant_id = request.headers.get("X-Tenant-ID", "")
    if not tenant_id: raise RequestValidationError("X-Tenant-ID is required")
    authorization = request.headers.get("Authorization", "")
    caller = caller_for_authorization(authorization)
    claims = await active.tokens.verify(authorization, expected_client_id=caller.client_id, required_scope=caller.status_scope)
    authorize_tenant(claims, tenant_id)
    return active.commands, tenant_id


@router.get("")
async def list_operations(request: Request, limit: int = Query(50, ge=1, le=100), cursor: str | None = None, state: CommandState | None = None, command_type: str | None = Query(None, min_length=1, max_length=180)) -> JSONResponse:
    service, tenant_id = await _context(request)
    decoded = _decode_cursor(cursor, "operations")
    try: position = (datetime.fromisoformat(decoded[0]), UUID(decoded[1])) if decoded else None
    except (ValueError, TypeError) as exc: raise RequestValidationError("cursor is malformed") from exc
    rows = await service.list_operations(tenant_id, limit=limit + 1, position=position, state=state, command_type=command_type)
    more = len(rows) > limit
    items = rows[:limit]
    next_cursor = _encode_cursor("operations", [items[-1].created_at.isoformat(), str(items[-1].command_id)]) if more else None
    return JSONResponse(content={"items": [item.model_dump(mode="json") for item in items], "next_cursor": next_cursor})


@router.get("/{command_id}")
async def get_operation(command_id: UUID, request: Request) -> JSONResponse:
    service, tenant_id = await _context(request)
    operation = await service.get(tenant_id, command_id)
    return JSONResponse(content=operation.model_dump(mode="json"), headers={"X-Correlation-ID": operation.correlation_id})


@router.get("/{command_id}/events")
async def list_events(command_id: UUID, request: Request, limit: int = Query(50, ge=1, le=100), cursor: str | None = None) -> JSONResponse:
    service, tenant_id = await _context(request)
    decoded = _decode_cursor(cursor, "events")
    try: position = (datetime.fromisoformat(decoded[0]), int(decoded[1])) if decoded else None
    except (ValueError, TypeError) as exc: raise RequestValidationError("cursor is malformed") from exc
    rows = await service.list_events(tenant_id, command_id, limit=limit + 1, position=position)
    items, more = rows[:limit], len(rows) > limit
    next_cursor = _encode_cursor("events", [items[-1].created_at.isoformat(), items[-1].event_id]) if more else None
    return JSONResponse(content={"items": [item.model_dump(mode="json") for item in items], "next_cursor": next_cursor})


@router.get("/{command_id}/attempts")
async def list_attempts(command_id: UUID, request: Request, limit: int = Query(50, ge=1, le=100), cursor: str | None = None) -> JSONResponse:
    service, tenant_id = await _context(request)
    decoded = _decode_cursor(cursor, "attempts")
    try: position = (int(decoded[0]), int(decoded[1])) if decoded else None
    except (ValueError, TypeError) as exc: raise RequestValidationError("cursor is malformed") from exc
    rows = await service.list_attempts(tenant_id, command_id, limit=limit + 1, position=position)
    items, more = rows[:limit], len(rows) > limit
    next_cursor = _encode_cursor("attempts", [items[-1].attempt_number, items[-1].attempt_id]) if more else None
    return JSONResponse(content={"items": [item.model_dump(mode="json") for item in items], "next_cursor": next_cursor})
