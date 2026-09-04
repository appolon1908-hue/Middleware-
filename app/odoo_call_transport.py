"""Odoo 19 transport for authoritative VICIdial call-lifecycle events.

This transport is separate from the CRM lead-command adapter because the Odoo
call endpoint uses its established compact HMAC contract. The dispatch outcome
rules remain identical: only a confirmed POST or a matching read-back returns
success; a proven 404 may be retried; every ambiguous outcome stays quarantined.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Any

import httpx

from .storage import OutboxRecord
from .vicidial_call_projection import (
    ODOO_CALL_EVENT_DESTINATION,
    ODOO_CALL_EVENT_OUTBOX_TYPE,
    OdooCallEvent,
)
from .worker import KnownSafeRetryError

CALL_EVENT_PATH = "/codestra/api/v1/call-events"
CALL_EVENT_STATUS_PATH = "/codestra/api/v1/call-events/{event_id}"
AMBIGUOUS_STATUSES = frozenset({502, 503, 504})


class OdooCallEventTransportError(RuntimeError):
    pass


class OdooCallEventConfigurationError(RuntimeError):
    pass


def serialize_call_event(event: OdooCallEvent) -> bytes:
    return json.dumps(
        event.model_dump(mode="json", exclude_none=True),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def sign_call_event(secret: bytes, timestamp: str, body: bytes) -> str:
    return hmac.new(
        secret,
        timestamp.encode("utf-8") + b"." + body,
        hashlib.sha256,
    ).hexdigest()


@dataclass(slots=True)
class OdooCallEventDispatcher:
    client: httpx.AsyncClient
    base_url: str
    secrets: dict[str, bytes]
    default_secret: bytes | None = None

    def __post_init__(self) -> None:
        if not self.base_url.startswith("https://"):
            raise OdooCallEventConfigurationError("Odoo base URL must be HTTPS")
        if not self.secrets and not self.default_secret:
            raise OdooCallEventConfigurationError(
                "no Odoo call-event signing secret is configured"
            )

    def _secret_for(self, tenant_id: str) -> bytes:
        secret = self.secrets.get(tenant_id) or self.default_secret
        if not secret:
            raise OdooCallEventConfigurationError(
                f"no Odoo call-event signing secret exists for tenant {tenant_id}"
            )
        return secret

    @staticmethod
    def _validate(record: OutboxRecord) -> OdooCallEvent:
        if record.destination != ODOO_CALL_EVENT_DESTINATION:
            raise OdooCallEventTransportError(
                "outbox row targets an unsupported Odoo call destination"
            )
        if record.event_type != ODOO_CALL_EVENT_OUTBOX_TYPE:
            raise OdooCallEventTransportError(
                "outbox event type is not the Odoo call-event projection"
            )
        try:
            event = OdooCallEvent.model_validate(record.payload)
        except Exception as exc:
            raise OdooCallEventTransportError(
                "outbox payload does not match the Odoo call-event contract"
            ) from exc
        if event.tenant_id != record.tenant_id:
            raise OdooCallEventTransportError(
                "outbox tenant does not match the Odoo call event"
            )
        if event.event_id != record.idempotency_key:
            raise OdooCallEventTransportError(
                "outbox idempotency does not match the Odoo call event"
            )
        return event

    def _headers(
        self,
        *,
        tenant_id: str,
        event_id: str,
        body: bytes,
    ) -> dict[str, str]:
        timestamp = str(int(time.time()))
        signature = sign_call_event(
            self._secret_for(tenant_id),
            timestamp,
            body,
        )
        return {
            "X-Codestra-Timestamp": timestamp,
            "X-Codestra-Signature": signature,
            "X-Codestra-Event-ID": event_id,
            "X-Codestra-Tenant-ID": tenant_id,
        }

    async def dispatch(self, record: OutboxRecord) -> None:
        event = self._validate(record)
        body = serialize_call_event(event)
        headers = self._headers(
            tenant_id=event.tenant_id,
            event_id=event.event_id,
            body=body,
        )
        headers["Content-Type"] = "application/json"
        try:
            response = await self.client.post(
                self.base_url.rstrip("/") + CALL_EVENT_PATH,
                content=body,
                headers=headers,
            )
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            raise KnownSafeRetryError(
                "Odoo connection failed before the call event could be sent"
            ) from exc
        except httpx.RequestError as exc:
            await self._reconcile(event, reason=str(exc))
            return

        if response.status_code in {200, 202}:
            return
        if response.status_code in AMBIGUOUS_STATUSES:
            await self._reconcile(
                event,
                reason=f"gateway status {response.status_code}",
            )
            return
        raise OdooCallEventTransportError(
            "Odoo rejected the call event with status "
            f"{response.status_code}: {self._error_code(response)}"
        )

    @staticmethod
    def _error_code(response: httpx.Response) -> str:
        try:
            body = response.json()
        except ValueError:
            return "unparseable-response"
        if isinstance(body, dict):
            detail = body.get("error") or body.get("detail")
            if isinstance(detail, str):
                return detail[:160]
        return "unspecified"

    async def _reconcile(self, event: OdooCallEvent, *, reason: str) -> None:
        path = CALL_EVENT_STATUS_PATH.format(event_id=event.event_id)
        headers = self._headers(
            tenant_id=event.tenant_id,
            event_id=event.event_id,
            body=b"",
        )
        try:
            response = await self.client.get(
                self.base_url.rstrip("/") + path,
                headers=headers,
            )
        except httpx.RequestError as exc:
            raise OdooCallEventTransportError(
                f"Odoo call-event outcome is unknown ({reason}) and read-back failed"
            ) from exc

        if response.status_code == 404:
            raise KnownSafeRetryError(
                f"read-back proved Odoo did not record the call event ({reason})"
            )
        if response.status_code != 200:
            raise OdooCallEventTransportError(
                f"Odoo call-event outcome is unknown ({reason}); read-back returned "
                f"{response.status_code}"
            )

        try:
            value: Any = response.json()
        except ValueError as exc:
            raise OdooCallEventTransportError(
                "Odoo call-event read-back returned invalid JSON"
            ) from exc
        if not isinstance(value, dict):
            raise OdooCallEventTransportError(
                "Odoo call-event read-back returned an invalid document"
            )
        if (
            value.get("event_id") != event.event_id
            or value.get("event_type") != event.event_type
            or value.get("call_id") != event.call_id
            or value.get("sequence") != event.sequence
        ):
            raise OdooCallEventTransportError(
                "Odoo call-event read-back identity does not match the dispatched event"
            )
