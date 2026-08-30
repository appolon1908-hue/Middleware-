from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from typing import Any, Mapping
from urllib.parse import quote, urlsplit

import httpx

from .config import ConfigurationError, Settings
from .temporal_workflows import ActivityResult, CommandExecutionRequest


class OdooProviderAdapterError(RuntimeError):
    pass


class OdooProviderAdapter:
    """Fail-closed transport from the durable command plane to Odoo 19.

    The adapter implements only the explicitly reviewed CRM command subset. It
    signs every request using the HMAC contract already enforced by
    codestra_middleware_bridge and performs a mandatory read-back before a
    Temporal workflow can mark a command completed.
    """

    CREATE_LEAD = "crm.lead.create.v1"
    UPDATE_LEAD = "crm.lead.update.v1"
    SUPPORTED = {CREATE_LEAD, UPDATE_LEAD}

    def __init__(
        self,
        settings: Settings,
        env: Mapping[str, str] | None = None,
    ) -> None:
        self.settings = settings
        self.env = os.environ if env is None else env

    def _required(self, name: str) -> str:
        value = self.env.get(name, "").strip()
        if not value:
            raise ConfigurationError(f"{name} is required for the Odoo adapter")
        return value

    def _base_url(self) -> str:
        value = self._required("ODOO_INTEGRATION_BASE_URL").rstrip("/")
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ConfigurationError("ODOO_INTEGRATION_BASE_URL must be an HTTP(S) origin")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ConfigurationError("ODOO_INTEGRATION_BASE_URL must not contain credentials, query, or fragment")
        if self.settings.app_env == "production" and parsed.scheme != "https":
            raise ConfigurationError("production Odoo integration requires HTTPS")
        return value

    def _secret(self) -> bytes:
        return self._required("ODOO_INBOUND_HMAC_SECRET").encode("utf-8")

    def _require_active(self, request: CommandExecutionRequest) -> None:
        if request.target != "odoo-19":
            raise OdooProviderAdapterError("Odoo adapter does not own this command target")
        if request.capability != "ODOO_WRITE":
            raise OdooProviderAdapterError("Odoo command capability must be ODOO_WRITE")
        if self.settings.external_effects.get("ODOO_WRITE") is not True:
            raise OdooProviderAdapterError("ODOO_WRITE is disabled")
        if request.command_type not in self.SUPPORTED:
            raise OdooProviderAdapterError(
                f"unsupported Odoo command type: {request.command_type}"
            )

    @staticmethod
    def _external_id(request: CommandExecutionRequest) -> str:
        value = request.payload.get("external_id")
        if not isinstance(value, str) or not value.strip() or len(value) > 180:
            raise OdooProviderAdapterError("payload.external_id is required")
        return value.strip()

    @staticmethod
    def _canonical_body(payload: dict[str, Any]) -> bytes:
        return json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")

    def _headers(
        self,
        *,
        method: str,
        path: str,
        body: bytes,
        request: CommandExecutionRequest,
        suffix: str = "",
    ) -> dict[str, str]:
        timestamp = str(int(time.time()))
        event_id = f"{request.command_id}{suffix}"
        idempotency_key = f"{request.idempotency_key}{suffix}"
        canonical = b"\n".join(
            (
                timestamp.encode("utf-8"),
                event_id.encode("utf-8"),
                method.upper().encode("utf-8"),
                path.encode("utf-8"),
                body,
            )
        )
        signature = hmac.new(self._secret(), canonical, hashlib.sha256).hexdigest()
        return {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-Codestra-Timestamp": timestamp,
            "X-Codestra-Event-ID": event_id,
            "X-Codestra-Signature": f"sha256={signature}",
            "X-Tenant-ID": request.tenant_id,
            "X-Correlation-ID": request.correlation_id,
            "Idempotency-Key": idempotency_key,
        }

    def _write_request(self, request: CommandExecutionRequest) -> tuple[str, str, dict[str, Any]]:
        external_id = self._external_id(request)
        if request.command_type == self.CREATE_LEAD:
            payload = dict(request.payload)
            middleware_id = payload.get("middleware_id")
            if not isinstance(middleware_id, str) or not middleware_id.strip():
                raise OdooProviderAdapterError("payload.middleware_id is required for lead creation")
            return "POST", "/codestra/middleware/v1/crm/leads", payload
        payload = dict(request.payload)
        payload.pop("external_id", None)
        if not payload:
            raise OdooProviderAdapterError("lead update requires at least one mutable field")
        return (
            "PATCH",
            f"/codestra/middleware/v1/crm/leads/{quote(external_id, safe='')}",
            payload,
        )

    async def execute(self, request: CommandExecutionRequest) -> ActivityResult:
        self._require_active(request)
        method, path, payload = self._write_request(request)
        body = self._canonical_body(payload)
        try:
            async with httpx.AsyncClient(timeout=25.0) as client:
                response = await client.request(
                    method,
                    f"{self._base_url()}{path}",
                    content=body,
                    headers=self._headers(
                        method=method,
                        path=path,
                        body=body,
                        request=request,
                    ),
                )
                response.raise_for_status()
                data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise OdooProviderAdapterError("Odoo command transport failed") from exc
        external_id = self._external_id(request)
        if not isinstance(data, dict) or data.get("external_id") != external_id:
            raise OdooProviderAdapterError("Odoo response did not confirm the external identity")
        return ActivityResult(
            status="accepted",
            detail="Odoo accepted the durable CRM command",
            provider_operation_id=external_id,
        )

    async def readback(self, request: CommandExecutionRequest) -> ActivityResult:
        self._require_active(request)
        external_id = self._external_id(request)
        path = f"/codestra/middleware/v1/crm/leads/{quote(external_id, safe='')}"
        body = b""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{self._base_url()}{path}",
                    headers=self._headers(
                        method="GET",
                        path=path,
                        body=body,
                        request=request,
                        suffix=":readback",
                    ),
                )
                response.raise_for_status()
                data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise OdooProviderAdapterError("Odoo read-back transport failed") from exc
        if not isinstance(data, dict) or data.get("external_id") != external_id:
            return ActivityResult(
                status="mismatch",
                detail="Odoo read-back did not match the external identity",
                provider_operation_id=external_id,
            )
        comparable = {
            "name",
            "contact_name",
            "email",
            "phone",
            "company_name",
            "description",
            "source",
            "campaign",
            "middleware_id",
        }
        for key in comparable & request.payload.keys():
            if data.get(key) != request.payload.get(key):
                return ActivityResult(
                    status="mismatch",
                    detail=f"Odoo read-back mismatch for {key}",
                    provider_operation_id=external_id,
                )
        return ActivityResult(
            status="matched",
            detail="Odoo read-back matched durable command intent",
            provider_operation_id=external_id,
        )
