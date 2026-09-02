from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .commands import CommandEnvelope
from .security import (
    AuthorizationError,
    RequestValidationError,
    authorize_tenant,
)
from .storage import StorageError

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "config" / "provider-operation-policy.json"

SENSITIVE_PAYLOAD_KEYS = frozenset(
    {
        "access_token",
        "api_key",
        "authorization",
        "client_secret",
        "credential",
        "credentials",
        "password",
        "private_key",
        "provider_token",
        "refresh_token",
        "secret",
        "token",
    }
)
SENSITIVE_PAYLOAD_KEY_SUFFIXES = (
    "_api_key",
    "_credential",
    "_credentials",
    "_password",
    "_private_key",
    "_secret",
    "_token",
)


@dataclass(frozen=True)
class ProviderControlSpec:
    operation_id: str
    caller_client_id: str
    required_scope: str
    route: str
    command_type: str
    target: str
    capability: str


def _load_specs() -> tuple[ProviderControlSpec, ...]:
    raw = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    if raw.get("schemaVersion") != 1:
        raise RuntimeError("unsupported provider-operation policy version")

    specs: list[ProviderControlSpec] = []
    for operation in raw.get("operations", []):
        if operation.get("externalEffect") is not True:
            continue
        required = {
            "id",
            "caller",
            "scope",
            "route",
            "commandType",
            "target",
            "capability",
        }
        if not required <= operation.keys():
            raise RuntimeError("provider control operation binding is incomplete")
        specs.append(
            ProviderControlSpec(
                operation_id=str(operation["id"]),
                caller_client_id=str(operation["caller"]),
                required_scope=str(operation["scope"]),
                route=str(operation["route"]),
                command_type=str(operation["commandType"]),
                target=str(operation["target"]),
                capability=str(operation["capability"]),
            )
        )

    if not specs or len({spec.route for spec in specs}) != len(specs):
        raise RuntimeError("provider control routes are empty or duplicated")
    return tuple(sorted(specs, key=lambda spec: spec.operation_id))


PROVIDER_CONTROL_SPECS = _load_specs()


class ProviderControlRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation_id: UUID
    payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("payload")
    @classmethod
    def reject_sensitive_payload_keys(cls, value: dict[str, Any]) -> dict[str, Any]:
        def inspect(item: Any) -> None:
            if isinstance(item, dict):
                for raw_key, nested in item.items():
                    key = str(raw_key).strip().lower()
                    if key in SENSITIVE_PAYLOAD_KEYS or key.endswith(
                        SENSITIVE_PAYLOAD_KEY_SUFFIXES
                    ):
                        raise ValueError(
                            "provider credentials and secret material are forbidden"
                        )
                    inspect(nested)
            elif isinstance(item, list):
                for nested in item:
                    inspect(nested)

        inspect(value)
        return value


router = APIRouter(tags=["provider-control"])


def _required_header(request: Request, name: str, *, minimum: int, maximum: int) -> str:
    value = request.headers.get(name, "").strip()
    if not minimum <= len(value) <= maximum:
        raise RequestValidationError(
            f"{name} must contain between {minimum} and {maximum} characters"
        )
    return value


async def _submit_provider_operation(
    spec: ProviderControlSpec,
    body: ProviderControlRequest,
    request: Request,
) -> JSONResponse:
    active = request.app.state.runtime
    if active.commands is None:
        raise StorageError("command ledger is unavailable")

    tenant_id = _required_header(request, "X-Tenant-ID", minimum=1, maximum=128)
    correlation_id = _required_header(
        request,
        "X-Correlation-ID",
        minimum=1,
        maximum=180,
    )
    idempotency_key = _required_header(
        request,
        "Idempotency-Key",
        minimum=8,
        maximum=180,
    )
    authorization = request.headers.get("Authorization", "")
    claims = await active.tokens.verify(
        authorization,
        expected_client_id=spec.caller_client_id,
        required_scope=spec.required_scope,
    )
    authorize_tenant(claims, tenant_id)
    subject = claims.get("sub")
    if not isinstance(subject, str) or not subject.strip():
        raise AuthorizationError("machine token subject is required")

    command = CommandEnvelope(
        command_id=body.operation_id,
        command_type=spec.command_type,
        command_version="1.0",
        target=spec.target,
        tenant_id=tenant_id,
        requested_by=subject,
        correlation_id=correlation_id,
        idempotency_key=idempotency_key,
        capability=spec.capability,
        payload=body.payload,
    )
    operation = await active.commands.submit(
        command,
        authenticated_subject=subject,
    )
    return JSONResponse(
        status_code=200 if operation.duplicate else 202,
        content={
            **operation.model_dump(mode="json"),
            "control_operation": spec.operation_id,
            "external_effect_dispatched": False,
        },
        headers={
            "Location": f"/v1/operations/{operation.command_id}",
            "X-Correlation-ID": operation.correlation_id,
        },
    )


def _handler(spec: ProviderControlSpec):
    async def handler(
        body: ProviderControlRequest,
        request: Request,
    ) -> JSONResponse:
        return await _submit_provider_operation(spec, body, request)

    handler.__name__ = "submit_" + spec.operation_id.replace(".", "_")
    return handler


for _spec in PROVIDER_CONTROL_SPECS:
    router.add_api_route(
        _spec.route,
        _handler(_spec),
        methods=["POST"],
        name="provider_control_" + _spec.operation_id.replace(".", "_"),
        summary=f"Submit {_spec.operation_id} through the durable operation engine",
        status_code=202,
        responses={
            200: {
                "description": "Idempotent replay of the existing durable operation"
            },
            202: {"description": "Durable provider operation accepted"},
        },
    )
