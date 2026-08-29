"""Provider adapter registry for automation command families."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class Adapter:
    name: str
    domain: str
    external_effect: str
    base_url_env: str
    delivery_flag_env: str
    token_file_env: str
    required_payload_fields: tuple[str, ...] = ()

    def execute(self, command_type: str, payload: dict[str, Any], *, dry_run: bool) -> dict[str, Any]:
        missing = [field for field in self.required_payload_fields if not payload.get(field)]
        if missing:
            return {
                "status": "PAYLOAD_INVALID",
                "adapter": self.name,
                "domain": self.domain,
                "missing_fields": missing,
            }
        if dry_run:
            return {
                "status": "NO_EFFECT",
                "adapter": self.name,
                "domain": self.domain,
                "reason": "dry_run",
            }
        if os.environ.get(self.delivery_flag_env, "").lower() != "true":
            return {
                "status": "DELIVERY_DISABLED",
                "adapter": self.name,
                "domain": self.domain,
                "flag": self.delivery_flag_env,
            }
        base_url = os.environ.get(self.base_url_env, "").rstrip("/")
        if not base_url:
            return {
                "status": "ADAPTER_UNCONFIGURED",
                "adapter": self.name,
                "domain": self.domain,
                "required_env": self.base_url_env,
            }
        headers = {"Content-Type": "application/json"}
        token_file = os.environ.get(self.token_file_env, "")
        if token_file:
            try:
                token = open(token_file, encoding="utf-8").read().strip()
            except OSError:
                return {
                    "status": "ADAPTER_TOKEN_UNAVAILABLE",
                    "adapter": self.name,
                    "domain": self.domain,
                    "required_env": self.token_file_env,
                }
            if token:
                headers["Authorization"] = f"Bearer {token}"
        body = json.dumps({"command_type": command_type, "payload": payload}).encode("utf-8")
        request = Request(
            f"{base_url}/automation/commands",
            data=body,
            headers=headers,
            method="POST",
        )
        try:
            with urlopen(request, timeout=10) as response:
                raw = response.read().decode("utf-8")
                parsed = json.loads(raw) if raw else {}
                return {
                    "status": "SENT",
                    "adapter": self.name,
                    "domain": self.domain,
                    "http_status": response.status,
                    "response": parsed,
                }
        except HTTPError as exc:
            return {
                "status": "ADAPTER_HTTP_ERROR",
                "adapter": self.name,
                "domain": self.domain,
                "http_status": exc.code,
            }
        except URLError as exc:
            return {
                "status": "ADAPTER_UNREACHABLE",
                "adapter": self.name,
                "domain": self.domain,
                "reason": str(exc.reason),
            }
        return {
            "status": "QUEUED",
            "adapter": self.name,
            "domain": self.domain,
            "external_effect": self.external_effect,
            "command_type": command_type,
            "payload_accepted": isinstance(payload, dict),
        }


ADAPTERS_BY_PREFIX: dict[str, Adapter] = {
    "crm.": Adapter("odoo", "crm", "odoo-state-change", "ODOO_ADAPTER_BASE_URL", "ENABLE_ODOO_DELIVERY", "ODOO_ADAPTER_TOKEN_FILE"),
    "support.": Adapter("odoo", "support", "odoo-activity-or-ticket-change", "ODOO_ADAPTER_BASE_URL", "ENABLE_ODOO_DELIVERY", "ODOO_ADAPTER_TOKEN_FILE"),
    "telephony.": Adapter("vicidial", "telephony", "call-or-callback-update", "VICIDIAL_ADAPTER_BASE_URL", "ENABLE_DIALING", "VICIDIAL_ADAPTER_TOKEN_FILE"),
    "sms.": Adapter("telnexa", "messaging.sms", "sms-dispatch", "TELNEXA_ADAPTER_BASE_URL", "ENABLE_SMS_DELIVERY", "TELNEXA_ADAPTER_TOKEN_FILE"),
    "email.klyrow.smtp-relay": Adapter("klyrow-smtp", "messaging.email.smtp", "smtp-relay-submission", "KLYROW_SMTP_RELAY_BASE_URL", "ENABLE_KLYROW_SMTP_RELAY", "KLYROW_SMTP_RELAY_TOKEN_FILE", ("tenant_id", "domain", "message_id")),
    "email.klyrow.send": Adapter("klyrow", "messaging.email", "email-submission", "KLYROW_ADAPTER_BASE_URL", "ENABLE_EMAIL_DELIVERY", "KLYROW_ADAPTER_TOKEN_FILE", ("tenant_id", "message_id")),
    "email.klyrow.event": Adapter("klyrow", "messaging.email.events", "email-lifecycle-event", "KLYROW_ADAPTER_BASE_URL", "ENABLE_EMAIL_EVENTS", "KLYROW_ADAPTER_TOKEN_FILE", ("tenant_id", "message_id", "event_type")),
    "email.": Adapter("klyrow", "messaging.email", "email-or-smtp-dispatch", "KLYROW_ADAPTER_BASE_URL", "ENABLE_EMAIL_DELIVERY", "KLYROW_ADAPTER_TOKEN_FILE"),
    "crawler.": Adapter("kyqra", "crawler.kyqra", "crawler-job-or-result-update", "KYQRA_ADAPTER_BASE_URL", "ENABLE_CRAWLER_EXECUTION", "KYQRA_ADAPTER_TOKEN_FILE"),
    "social.": Adapter("postly", "social.postly", "social-publication", "POSTLY_ADAPTER_BASE_URL", "ENABLE_SOCIAL_PUBLISH", "POSTLY_ADAPTER_TOKEN_FILE"),
    "provisioning.": Adapter("provisioning", "provisioning", "tenant-or-integration-change", "PROVISIONING_ADAPTER_BASE_URL", "ENABLE_PROVISIONING_DELIVERY", "PROVISIONING_ADAPTER_TOKEN_FILE"),
    "identity.": Adapter("identity", "identity", "service-identity-change", "IDENTITY_ADAPTER_BASE_URL", "ENABLE_PROVISIONING_DELIVERY", "IDENTITY_ADAPTER_TOKEN_FILE"),
    "moneybee.": Adapter("moneybee", "product.moneybee", "product-operation", "MONEYBEE_ADAPTER_BASE_URL", "ENABLE_PRODUCT_DELIVERY", "MONEYBEE_ADAPTER_TOKEN_FILE"),
    "beyvra.operations.": Adapter("beyvra", "product.beyvra-nonfinancial", "nonfinancial-product-operation", "BEYVRA_ADAPTER_BASE_URL", "ENABLE_PRODUCT_DELIVERY", "BEYVRA_ADAPTER_TOKEN_FILE"),
    "larim.": Adapter("larim-a", "product.larim-a", "booking-or-dispatch-operation", "LARIM_A_ADAPTER_BASE_URL", "ENABLE_PRODUCT_DELIVERY", "LARIM_A_ADAPTER_TOKEN_FILE"),
    "freight.": Adapter("freight", "product.freight", "shipment-or-document-operation", "FREIGHT_ADAPTER_BASE_URL", "ENABLE_PRODUCT_DELIVERY", "FREIGHT_ADAPTER_TOKEN_FILE"),
    "breero.": Adapter("breero", "product.breero", "marketplace-operation", "BREERO_ADAPTER_BASE_URL", "ENABLE_PRODUCT_DELIVERY", "BREERO_ADAPTER_TOKEN_FILE"),
    "booked4seasons.": Adapter("booked4seasons", "product.booked4seasons", "booking-operation", "BOOKED4SEASONS_ADAPTER_BASE_URL", "ENABLE_PRODUCT_DELIVERY", "BOOKED4SEASONS_ADAPTER_TOKEN_FILE"),
    "trading.operations.": Adapter("trading", "product.trading-nonfinancial", "nonfinancial-trading-operation", "TRADING_ADAPTER_BASE_URL", "ENABLE_PRODUCT_DELIVERY", "TRADING_ADAPTER_TOKEN_FILE"),
    "real-wallet.operations.": Adapter("trading", "product.trading-nonfinancial", "nonfinancial-wallet-operation", "TRADING_ADAPTER_BASE_URL", "ENABLE_PRODUCT_DELIVERY", "TRADING_ADAPTER_TOKEN_FILE"),
    "privacy.": Adapter("privacy", "privacy", "data-rights-operation", "PRIVACY_ADAPTER_BASE_URL", "ENABLE_PRIVACY_DELIVERY", "PRIVACY_ADAPTER_TOKEN_FILE"),
}


def adapter_for(command_type: str) -> Adapter | None:
    for prefix, adapter in ADAPTERS_BY_PREFIX.items():
        if command_type.startswith(prefix):
            return adapter
    return None
