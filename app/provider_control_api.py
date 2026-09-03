from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .commands import CommandEnvelope
from .control_api import router
from .operations import OperationResponse, _operation_json
from .security import (
    AuthorizationError,
    RequestValidationError,
    authorize_tenant,
)
from .storage import StorageError

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "config" / "provider-operation-policy.json"

# Separator-insensitive normalization matching the Connector SDK's canonical
# secret-key rules. Governance controls such as token_budget and max_tokens are
# explicitly safe; credential spellings such as APIKEY, client-secret,
# accessToken, and secretValue are always rejected before persistence.
_SECRET_KEY_NAMES = frozenset(
    {
        "accesstoken",
        "apikey",
        "authorization",
        "clientsecret",
        "cookie",
        "credential",
        "credentials",
        "password",
        "passwd",
        "privatekey",
        "providertoken",
        "refreshtoken",
        "secret",
        "secretvalue",
        "session",
        "sessionid",
        "token",
    }
)
_ALLOWED_GOVERNANCE_KEYS = frozenset({"maxtokens", "tokenbudget"})
_REFERENCE_SUFFIXES = ("reference", "references")


def normalize_payload_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def is_forbidden_provider_key(value: str) -> bool:
    normalized = normalize_payload_key(value)
    if not normalized or normalized in _ALLOWED_GOVERNANCE_KEYS:
        return False
    if normalized.endswith(_REFERENCE_SUFFIXES):
        return False
    return normalized in _SECRET_KEY_NAMES or any(
        normalized.endswith(secret_name) for secret_name in _SECRET_KEY_NAMES
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
    provider_class: str


def _load_specs() -> tuple[ProviderControlSpec, ...]:
    try:
        raw = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("provider-operation policy cannot be loaded") from exc
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
            "providerClass",
        }
        if not required <= operation.keys():
            raise RuntimeError("provider control operation binding is incomplete")
        values = {name: operation[name] for name in required}
        if not all(isinstance(value, str) and value for value in values.values()):
            raise RuntimeError("provider control operation binding is malformed")
        specs.append(
            ProviderControlSpec(
                operation_id=operation["id"],
                caller_client_id=operation["caller"],
                required_scope=operation["scope"],
                route=operation["route"],
                command_type=operation["commandType"],
                target=operation["target"],
                capability=operation["capability"],
                provider_class=operation["providerClass"],
            )
        )

    if not specs or len({spec.route for spec in specs}) != len(specs):
        raise RuntimeError("provider control routes are empty or duplicated")
    if len({spec.operation_id for spec in specs}) != len(specs):
        raise RuntimeError("provider control operation identities are duplicated")
    return tuple(sorted(specs, key=lambda spec: spec.operation_id))


PROVIDER_CONTROL_SPECS = _load_specs()


class ProviderControlRequest(BaseModel):
    """Minimal public request; Middleware owns all provider bindings."""

    model_config = ConfigDict(extra="forbid")

    operation_id: UUID
    payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("payload")
    @classmethod
    def reject_sensitive_payload_keys(cls, value: dict[str, Any]) -> dict[str, Any]:
        def inspect(item: Any) -> None:
            if isinstance(item, dict):
                for raw_key, nested in item.items():
                    if is_forbidden_provider_key(str(raw_key)):
                        raise ValueError(
                            "provider credentials and secret material are forbidden"
                        )
                    inspect(nested)
            elif isinstance(item, list):
                for nested in item:
                    inspect(nested)

        inspect(value)
        return value


class ProviderControlResponse(OperationResponse):
    control_operation: str
    external_effect_dispatched: Literal[False]


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
        minimum=8,
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
    authenticated_client_id = claims.get("azp")
    if authenticated_client_id != spec.caller_client_id:
        raise AuthorizationError("verified machine client identity is required")

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
        authenticated_client_id=spec.caller_client_id,
    )
    content = _operation_json(operation)
    content.update(
        {
            "control_operation": spec.operation_id,
            "external_effect_dispatched": False,
        }
    )
    return JSONResponse(
        status_code=200 if operation.duplicate else 202,
        content=content,
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


# Provider-control is part of the durable control surface. app.__init__ imports
# this module before app.main imports control_api.router, so the existing router
# is extended without a second application-registration authority.
for _spec in PROVIDER_CONTROL_SPECS:
    router.add_api_route(
        _spec.route,
        _handler(_spec),
        methods=["POST"],
        name="provider_control_" + _spec.operation_id.replace(".", "_"),
        summary=f"Submit {_spec.operation_id} through the durable operation engine",
        tags=["provider-control"],
        status_code=202,
        response_model=ProviderControlResponse,
        responses={
            200: {
                "description": "Idempotent replay of the existing durable operation",
                "model": ProviderControlResponse,
            },
            202: {
                "description": "Durable provider operation accepted",
                "model": ProviderControlResponse,
            },
        },
    )
