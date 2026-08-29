"""This adapter is called by Middleware only. No other system may call Klyrow directly."""

from __future__ import annotations

from typing import Any, Mapping

from ..base import BaseAdapter, EnvRef, ProviderError, ProviderRequest, ProviderResponse


class KlyrowAdapter(BaseAdapter):
    """Translate Middleware commands to Klyrow's documented email/campaign API."""

    ADAPTER_NAME = "klyrow"
    COMMANDS = frozenset({"send_email", "send_bulk_email", "create_campaign"})
    WEBHOOK_EVENTS = frozenset(
        {
            "email.queued",
            "email.sent",
            "email.delivered",
            "email.bounced",
            "email.complained",
            "email.opened",
            "email.clicked",
            "email.unsubscribed",
            "campaign.started",
            "campaign.completed",
            "campaign.failed",
        }
    )
    CAPABILITIES = {
        "email_delivery": True,
        "bulk_email": True,
        "campaigns": True,
        "inbound_webhook": True,
        "enrich": False,
        "sync": False,
    }
    ENVIRONMENT_NAMES = (
        "KLYROW_BASE_URL",
        "KLYROW_API_KEY",
        "KLYROW_WEBHOOK_SECRET",
    )
    _PATHS = {
        "send_email": "/v1/email/send",
        "send_bulk_email": "/v1/email/bulk",
        "create_campaign": "/v1/campaigns",
    }

    def _validate(self, command_type: str, payload: Mapping[str, Any]) -> None:
        if not payload.get("tenant_id"):
            raise ProviderError("Klyrow tenant_id is required", code="invalid_payload")
        if command_type == "send_email" and not payload.get("to"):
            raise ProviderError("Klyrow email recipient is required", code="invalid_payload")
        if command_type == "send_bulk_email" and not payload.get("recipients"):
            raise ProviderError("Klyrow bulk recipients are required", code="invalid_payload")
        if command_type == "create_campaign" and not payload.get("name"):
            raise ProviderError("Klyrow campaign name is required", code="invalid_payload")

    def _build_request(
        self,
        *,
        command_type: str,
        payload: Mapping[str, Any],
        idempotency_key: str,
        correlation_id: str,
        request_id: str,
    ) -> ProviderRequest:
        return ProviderRequest(
            method="POST",
            path=self._PATHS[command_type],
            body=dict(payload),
            headers={
                "Authorization": EnvRef("KLYROW_API_KEY"),
                "X-Klyrow-Tenant-Id": str(payload["tenant_id"]),
                "Idempotency-Key": idempotency_key,
                "X-Correlation-ID": correlation_id,
                "X-Request-ID": request_id,
            },
        )

    def _readback_matches(
        self,
        command_type: str,
        payload: Mapping[str, Any],
        write: ProviderResponse,
        readback: ProviderResponse,
    ) -> bool:
        del payload, write
        allowed = {
            "send_email": {"queued", "sent", "delivered"},
            "send_bulk_email": {"queued", "accepted", "processing", "completed"},
            "create_campaign": {"draft", "scheduled", "active", "completed"},
        }
        return readback.status.strip().lower() in allowed[command_type]
