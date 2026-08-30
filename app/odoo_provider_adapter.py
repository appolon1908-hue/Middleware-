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

    The adapter owns exactly one reviewed CRM command. It signs the command and
    every status read with the byte-exact contract implemented by
    ``codestra_middleware_bridge``. A write timeout is an unknown outcome: the
    Temporal workflow records ``reconciliation_required`` and never submits the
    command a second time. Reconciliation uses the command-status route.
    """

    UPSERT_LEAD = "crm.lead.upsert"
    SUPPORTED = {UPSERT_LEAD}
    COMMAND_PATH = "/codestra/middleware/v1/commands/crm.lead.upsert"
    STATUS_PATH = "/codestra/middleware/v1/commands/{command_id}/status"

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
            raise ConfigurationError(
                "ODOO_INTEGRATION_BASE_URL must not contain credentials, query, or fragment"
            )
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
        if request.command_version != "1.0":
            raise OdooProviderAdapterError("Odoo command version must be 1.0")

    @staticmethod
    def _source_record_id(request: CommandExecutionRequest) -> str:
        value = request.payload.get("source_record_id")
        if not isinstance(value, str) or not value.strip() or len(value) > 180:
            raise OdooProviderAdapterError("payload.source_record_id is required")
        return value.strip()

    @staticmethod
    def _canonical_body(payload: dict[str, Any]) -> bytes:
        return json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")

    @staticmethod
    def _command_document(request: CommandExecutionRequest) -> dict[str, Any]:
        return {
            "command_id": request.command_id,
            "command_type": request.command_type,
            "command_version": request.command_version,
            "target": request.target,
            "tenant_id": request.tenant_id,
            "requested_by": request.requested_by,
            "correlation_id": request.correlation_id,
            "idempotency_key": request.idempotency_key,
            "capability": request.capability,
            "payload": request.payload,
        }

    def _headers(
        self,
        *,
        method: str,
        path: str,
        body: bytes,
        request: CommandExecutionRequest,
        suffix: str = "",
        timestamp: str | None = None,
    ) -> dict[str, str]:
        signed_timestamp = timestamp or str(int(time.time()))
        event_id = f"{request.command_id}{suffix}"
        idempotency_key = f"{request.idempotency_key}{suffix}"
        canonical = b"\n".join(
            (
                signed_timestamp.encode("utf-8"),
                event_id.encode("utf-8"),
                method.upper().encode("utf-8"),
                path.encode("utf-8"),
                request.tenant_id.encode("utf-8"),
                request.correlation_id.encode("utf-8"),
                idempotency_key.encode("utf-8"),
                body,
            )
        )
        signature = hmac.new(self._secret(), canonical, hashlib.sha256).hexdigest()
        return {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-Codestra-Timestamp": signed_timestamp,
            "X-Codestra-Event-ID": event_id,
            "X-Codestra-Signature": f"sha256={signature}",
            "X-Tenant-ID": request.tenant_id,
            "X-Correlation-ID": request.correlation_id,
            "Idempotency-Key": idempotency_key,
        }

    def _write_request(
        self,
        request: CommandExecutionRequest,
    ) -> tuple[str, str, dict[str, Any]]:
        self._source_record_id(request)
        return "POST", self.COMMAND_PATH, self._command_document(request)

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
            raise OdooProviderAdapterError(
                "Odoo command outcome is unknown; reconcile by command status"
            ) from exc
        source_record_id = self._source_record_id(request)
        if (
            not isinstance(data, dict)
            or data.get("command_id") != request.command_id
            or data.get("external_id") != source_record_id
            or data.get("outcome") not in {"created", "updated"}
        ):
            raise OdooProviderAdapterError(
                "Odoo response did not confirm the canonical command identity"
            )
        return ActivityResult(
            status="accepted",
            detail="Odoo accepted the canonical CRM upsert command",
            provider_operation_id=request.command_id,
        )

    async def readback(self, request: CommandExecutionRequest) -> ActivityResult:
        """Read the recorded command outcome without replaying the write."""
        self._require_active(request)
        path = self.STATUS_PATH.format(
            command_id=quote(request.command_id, safe="")
        )
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
                        suffix=":status",
                    ),
                )
                response.raise_for_status()
                data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise OdooProviderAdapterError(
                "Odoo command-status reconciliation failed"
            ) from exc

        source_record_id = self._source_record_id(request)
        result = data.get("result") if isinstance(data, dict) else None
        if (
            not isinstance(data, dict)
            or data.get("command_id") != request.command_id
            or data.get("operation") != self.UPSERT_LEAD
            or not isinstance(result, dict)
            or result.get("command_id") != request.command_id
            or result.get("external_id") != source_record_id
            or result.get("outcome") not in {"created", "updated"}
        ):
            return ActivityResult(
                status="mismatch",
                detail="Odoo command status did not match durable command intent",
                provider_operation_id=request.command_id,
            )
        return ActivityResult(
            status="matched",
            detail="Odoo command status matched durable command intent",
            provider_operation_id=request.command_id,
        )
