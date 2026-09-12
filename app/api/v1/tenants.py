"""``GET /platform/v1/tenants`` - the platform-wide tenant directory.

Middleware owns no tenant table of its own (Mission-02's explicit "do not
create duplicate identity/tenant authorities" instruction - see
``app.adapters.foundation.client``'s module docstring). This endpoint is a
thin, read-only passthrough onto ``codestra-foundation``'s tenant list, the
same way ``app.api.v1.session_context`` already reads single-tenant state
from it rather than reimplementing tenant storage here.

Scope: gated to ``platform_admin``/``platform_operator`` only (via
``require_platform_scope``, the same dependency ``app.api.v1.platform``
already uses). There is currently no established pattern anywhere in this
codebase for a human tenant_admin to call a Middleware API directly with
their own session token (every existing tenant-scoped endpoint -
``session_context.py``, ``agent_provisioning.py`` - authenticates a
*machine* caller via ``require_provisioning_scope``, not a logged-in human).
Building that primitive is out of this change's scope; a tenant_admin
narrowing this list to their own tenant is therefore not yet supported and
is flagged here rather than silently faked.
"""

from __future__ import annotations

from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException

from app.adapters.foundation.client import FoundationClient, FoundationUnavailable
from app.core.config import settings
from app.core.platform_auth import PlatformPrincipal, require_platform_scope

router = APIRouter(prefix="/platform/v1/tenants", tags=["tenants"])


def _tenant_out(record: Any) -> dict[str, str]:
    return {
        "id": record.id,
        "slug": record.slug,
        "name": record.name,
        "status": record.status,
    }


@router.get("")
async def list_tenants(
    principal: PlatformPrincipal = Depends(
        require_platform_scope("platform.tenants.read")
    ),
) -> dict[str, Any]:
    foundation = FoundationClient(settings)
    async with httpx.AsyncClient() as http:
        try:
            records = await foundation.list_tenants(http)
        except FoundationUnavailable as exc:
            # Fail closed, not fail open - an empty list here would read as
            # "zero tenants exist", which is never true in production. An
            # unavailable upstream must surface as an error, not silence.
            raise HTTPException(503, "codestra-foundation is unavailable") from exc
    return {"tenants": [_tenant_out(record) for record in records]}
