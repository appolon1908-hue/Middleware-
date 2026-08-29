"""Idempotent provider webhook dispatch for Middleware-owned adapters."""

from __future__ import annotations

from typing import Any, Mapping

from middleware.adapters.base import BaseAdapter, ProviderError, WebhookResult


WEBHOOK_EVENT_SCHEMAS: Mapping[str, frozenset[str]] = {
    "telnexa": frozenset({"sms.delivered", "sms.failed", "sms.inbound"}),
    "klyrow": frozenset(
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
    ),
    "vicidial": frozenset(
        {"lead.dialed", "lead.answered", "lead.voicemail", "lead.dnc", "campaign.completed"}
    ),
    "scrapper": frozenset({"job.completed", "job.failed", "job.partial"}),
    "beyvra": frozenset({"operation.completed", "operation.failed", "operation.reconciled"}),
}


def validate_webhook_envelope(
    *, provider: str, event_type: str, payload: dict[str, Any], provider_event_id: str
) -> None:
    if provider not in WEBHOOK_EVENT_SCHEMAS:
        raise ProviderError("unknown webhook provider", code="invalid_webhook")
    if not isinstance(event_type, str) or not event_type:
        raise ProviderError("event_type is required", code="invalid_webhook")
    if not isinstance(provider_event_id, str) or not provider_event_id:
        raise ProviderError("provider_event_id is required", code="invalid_webhook")
    if not isinstance(payload, dict):
        raise ProviderError("webhook payload must be an object", code="invalid_webhook")


def dispatch_webhook(
    adapter: BaseAdapter,
    *,
    event_type: str,
    payload: dict[str, Any],
    provider_event_id: str,
) -> WebhookResult:
    validate_webhook_envelope(
        provider=adapter.ADAPTER_NAME,
        event_type=event_type,
        payload=payload,
        provider_event_id=provider_event_id,
    )
    return adapter.handle_webhook(
        event_type=event_type,
        payload=payload,
        provider_event_id=provider_event_id,
    )
