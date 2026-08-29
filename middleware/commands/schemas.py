"""Source-only command schemas for the Pass 1 provider adapters.

These definitions validate orchestration envelopes without creating a second command
ledger. The durable command ledger in the Middleware runtime remains authoritative.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from middleware.adapters.base import ProviderError, require_nonempty


@dataclass(frozen=True)
class AdapterCommand:
    provider: str
    command_type: str
    payload: dict[str, Any]
    idempotency_key: str
    correlation_id: str
    request_id: str

    def validate_metadata(self) -> "AdapterCommand":
        require_nonempty(self.provider, "provider")
        require_nonempty(self.command_type, "command_type")
        require_nonempty(self.idempotency_key, "idempotency_key")
        require_nonempty(self.correlation_id, "correlation_id")
        require_nonempty(self.request_id, "request_id")
        if not isinstance(self.payload, dict):
            raise ProviderError("payload must be an object", code="invalid_command")
        return self


PROVIDER_COMMANDS: Mapping[str, frozenset[str]] = {
    "telnexa": frozenset({"send_sms"}),
    "klyrow": frozenset({"send_email", "send_bulk_email", "create_campaign"}),
    "vicidial": frozenset(
        {"validate_campaign", "provision_campaign_disabled", "disable_campaign", "publish_lead", "add_to_campaign"}
    ),
    "scrapper": frozenset({"dispatch_scrape_job", "cancel_job"}),
    "beyvra": frozenset(
        {
            "create_onboarding_case",
            "request_compliance_reminder",
            "create_support_escalation",
            "create_report_request",
            "request_notification",
            "create_security_alert",
            "reconcile_webhook_delivery",
            "notify_call_completed",
            "notify_contact_enriched",
            "notify_scrape_completed",
        }
    ),
}


# The supplied mission named these Beyvra->Middleware command aliases. The real
# provider contracts do not currently support Telnexa voice dialing or Klyrow
# enrichment, so those aliases are intentionally non-routable until their owning
# repositories publish and test matching APIs. Scrape can map to the current v2 job API.
BEYVRA_INBOUND_COMMANDS: Mapping[str, Mapping[str, str | bool]] = {
    "dial": {"provider": "telnexa", "routable": False, "reason": "no voice API in Telnexa source contract"},
    "enrich": {"provider": "klyrow", "routable": False, "reason": "no contact-enrichment API in Klyrow source contract"},
    "scrape": {"provider": "scrapper", "command_type": "dispatch_scrape_job", "routable": True},
}


def validate_adapter_command(command: AdapterCommand) -> AdapterCommand:
    command.validate_metadata()
    allowed = PROVIDER_COMMANDS.get(command.provider)
    if allowed is None or command.command_type not in allowed:
        raise ProviderError(
            f"unsupported provider command: {command.provider}.{command.command_type}",
            code="unsupported_command",
        )
    return command
