from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from .commands import CommandEnvelope
from .security import AuthorizationError, RequestValidationError, authorize_tenant
from .storage import StorageError

router = APIRouter(prefix="/v1/integrations/n8n", tags=["n8n-control-plane"])


def _require_forwarding_headers(request: Request, command: CommandEnvelope) -> None:
    if request.headers.get("X-Tenant-ID") != command.tenant_id:
        raise RequestValidationError("X-Tenant-ID does not match command tenant")
    if request.headers.get("X-Correlation-ID") != command.correlation_id:
        raise RequestValidationError(
            "X-Correlation-ID does not match command correlation_id"
        )
    if request.headers.get("Idempotency-Key") != command.idempotency_key:
        raise RequestValidationError(
            "Idempotency-Key does not match command idempotency_key"
        )


@router.post("/commands")
async def submit_n8n_command(command: CommandEnvelope, request: Request) -> JSONResponse:
    """Accept a durable command from the n8n service identity through Kong.

    Kong remains the network/API gateway. Middleware independently validates the
    original Keycloak token so a gateway routing mistake cannot grant write
    authority. Provider capabilities remain fail-closed in the command policy.
    """
    active = request.app.state.runtime
    if active.commands is None:
        raise StorageError("command ledger is unavailable")
    claims = await active.tokens.verify(
        request.headers.get("Authorization", ""),
        expected_client_id="n8n-automation",
        required_scope="middleware.request.forward",
    )
    authorize_tenant(claims, command.tenant_id)
    _require_forwarding_headers(request, command)
    subject = claims.get("sub")
    if not isinstance(subject, str) or not subject:
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
            "Location": f"/v1/integrations/n8n/operations/{operation.command_id}",
            "X-Correlation-ID": operation.correlation_id,
        },
    )


@router.get("/operations/{command_id}")
async def get_n8n_operation(command_id: UUID, request: Request) -> JSONResponse:
    """Return durable command state to the originating n8n tenant."""
    active = request.app.state.runtime
    if active.commands is None:
        raise StorageError("command ledger is unavailable")
    claims = await active.tokens.verify(
        request.headers.get("Authorization", ""),
        expected_client_id="n8n-automation",
        required_scope="middleware.status.read",
    )
    tenant_id = request.headers.get("X-Tenant-ID", "")
    authorize_tenant(claims, tenant_id)
    operation = await active.commands.get(tenant_id, command_id)
    return JSONResponse(
        status_code=200,
        content=operation.model_dump(mode="json"),
        headers={"X-Correlation-ID": operation.correlation_id},
    )
