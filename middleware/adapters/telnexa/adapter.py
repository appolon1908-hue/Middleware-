"""This adapter is called by Middleware only. No other system may call Telnexa directly."""

from __future__ import annotations

import re
from typing import Any, Mapping

from ..base import BaseAdapter, EnvRef, ProviderError, ProviderRequest, ProviderResponse

E164 = re.compile(r"^\+[1-9][0-9]{7,14}$")


class TelnexaAdapter(BaseAdapter):
    """Translate Middleware SMS commands onto Telnexa's documented Jasmin `/send` surface."""

    ADAPTER_NAME = "telnexa"
    COMMANDS = frozenset({"send_sms"})
    WEBHOOK_EVENTS = frozenset({"sms.delivered", "sms.failed", "sms.inbound"})
    CAPABILITIES = {
        "sms": True,
        "inbound_webhook": True,
        "outbound_dial": False,
        "call_recording": False,
    }
    ENVIRONMENT_NAMES = (
        "TELNEXA_BASE_URL",
        "TELNEXA_HTTP_USERNAME",
        "TELNEXA_HTTP_PASSWORD",
        "TELNEXA_WEBHOOK_SECRET",
    )

    def _validate(self, command_type: str, payload: Mapping[str, Any]) -> None:
        del command_type
        phone = str(payload.get("phone_number") or payload.get("to") or "")
        if not E164.fullmatch(phone):
            raise ProviderError("Telnexa destination must be E.164", code="invalid_phone")
        content = payload.get("content") or payload.get("message")
        if not isinstance(content, str) or not content.strip():
            raise ProviderError("Telnexa SMS content is required", code="invalid_payload")

    def _build_request(
        self,
        *,
        command_type: str,
        payload: Mapping[str, Any],
        idempotency_key: str,
        correlation_id: str,
        request_id: str,
    ) -> ProviderRequest:
        del command_type
        phone = str(payload.get("phone_number") or payload.get("to"))
        return ProviderRequest(
            method="POST",
            path="/send",
            query={
                "username": EnvRef("TELNEXA_HTTP_USERNAME"),
                "password": EnvRef("TELNEXA_HTTP_PASSWORD"),
                "to": phone,
                "from": payload.get("caller_id") or payload.get("from") or "",
                "content": payload.get("content") or payload.get("message"),
                "coding": payload.get("coding", 0),
                "dlr": "yes",
                "dlr-level": 3,
            },
            headers={
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
        del command_type, payload, write
        # Jasmin's final delivery truth is the DLR path. Do not treat mere queue
        # acceptance as successful delivery.
        return readback.status.strip().lower() in {"delivered", "confirmed"}
