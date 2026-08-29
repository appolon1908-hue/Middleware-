"""This adapter is called by Middleware only. No other system may call VICIdial directly."""

from __future__ import annotations

import re
from typing import Any, Mapping

from ..base import BaseAdapter, EnvRef, ProviderError, ProviderRequest, ProviderResponse

E164 = re.compile(r"^\+[1-9][0-9]{7,14}$")


class VicidialAdapter(BaseAdapter):
    """Translate governed commands onto the restricted VICIdial adapter API."""

    ADAPTER_NAME = "vicidial"
    COMMANDS = frozenset(
        {
            "validate_campaign",
            "provision_campaign_disabled",
            "disable_campaign",
            "publish_lead",
            "add_to_campaign",
        }
    )
    WEBHOOK_EVENTS = frozenset(
        {"lead.dialed", "lead.answered", "lead.voicemail", "lead.dnc", "campaign.completed"}
    )
    CAPABILITIES = {
        "outbound_campaign": False,
        "dnc_enforcement": True,
        "inbound_webhook": True,
        "predictive_dialing": False,
        "disabled_campaign_provisioning": True,
        "lead_publication": True,
    }
    ENVIRONMENT_NAMES = (
        "VICIDIAL_ADAPTER_URL",
        "VICIDIAL_ADAPTER_CA_FILE",
        "VICIDIAL_ADAPTER_CLIENT_CERT_FILE",
        "VICIDIAL_ADAPTER_CLIENT_KEY_FILE",
        "VICIDIAL_ADAPTER_HMAC_FILE",
    )

    def _validate(self, command_type: str, payload: Mapping[str, Any]) -> None:
        if command_type in {"validate_campaign", "provision_campaign_disabled", "disable_campaign", "add_to_campaign"}:
            if not payload.get("campaign_id"):
                raise ProviderError("VICIdial campaign_id is required", code="invalid_payload")
        if command_type in {"publish_lead", "add_to_campaign"}:
            phone = str(payload.get("phone_number") or "")
            if not E164.fullmatch(phone):
                raise ProviderError("VICIdial lead phone_number must be E.164", code="invalid_phone")
        if command_type == "add_to_campaign" and payload.get("dnc_passed") is not True:
            raise ProviderError("VICIdial DNC gate must pass before lead publication", code="dnc_rejected")

    def _build_request(
        self,
        *,
        command_type: str,
        payload: Mapping[str, Any],
        idempotency_key: str,
        correlation_id: str,
        request_id: str,
    ) -> ProviderRequest:
        if command_type == "validate_campaign":
            path = "/v1/campaigns/validate"
            body = dict(payload)
        elif command_type == "provision_campaign_disabled":
            path = "/v1/campaigns/provision-disabled"
            body = dict(payload)
        elif command_type == "disable_campaign":
            path = "/v1/campaigns/disable"
            body = dict(payload)
        else:
            path = "/v1/leads/publish"
            body = dict(payload)
            if command_type == "add_to_campaign":
                body.setdefault("external_id", payload.get("contact_id") or request_id)
                body.pop("dnc_passed", None)
        return ProviderRequest(
            method="POST",
            path=path,
            body=body,
            headers={
                "X-Codestra-Identity": "codestra-middleware",
                "X-Codestra-Scope": "telephony:provision",
                "X-Codestra-HMAC": EnvRef("VICIDIAL_ADAPTER_HMAC_FILE"),
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
        status = readback.status.strip().lower()
        if command_type == "validate_campaign":
            return status in {"valid", "matched", "confirmed"}
        if command_type == "provision_campaign_disabled":
            return status in {"disabled", "matched", "confirmed"}
        if command_type == "disable_campaign":
            return status in {"disabled", "matched", "confirmed"}
        return status in {"published", "matched", "confirmed"}
