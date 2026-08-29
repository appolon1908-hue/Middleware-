"""Dry-run adapter registry for automation command families."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Adapter:
    name: str
    domain: str
    external_effect: str

    def execute(self, command_type: str, payload: dict[str, Any], *, dry_run: bool) -> dict[str, Any]:
        if dry_run:
            return {
                "status": "NO_EFFECT",
                "adapter": self.name,
                "domain": self.domain,
                "reason": "dry_run",
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
    "crm.": Adapter("odoo", "crm", "odoo-state-change"),
    "support.": Adapter("odoo", "support", "odoo-activity-or-ticket-change"),
    "telephony.": Adapter("vicidial", "telephony", "call-or-callback-update"),
    "sms.": Adapter("telnexa", "messaging.sms", "sms-dispatch"),
    "email.": Adapter("klyrow", "messaging.email", "email-or-smtp-dispatch"),
    "crawler.": Adapter("kyqra", "crawler.kyqra", "crawler-job-or-result-update"),
    "social.": Adapter("postly", "social.postly", "social-publication"),
    "provisioning.": Adapter("provisioning", "provisioning", "tenant-or-integration-change"),
    "identity.": Adapter("identity", "identity", "service-identity-change"),
    "moneybee.": Adapter("moneybee", "product.moneybee", "product-operation"),
    "beyvra.operations.": Adapter("beyvra", "product.beyvra-nonfinancial", "nonfinancial-product-operation"),
    "larim.": Adapter("larim-a", "product.larim-a", "booking-or-dispatch-operation"),
    "freight.": Adapter("freight", "product.freight", "shipment-or-document-operation"),
    "breero.": Adapter("breero", "product.breero", "marketplace-operation"),
    "booked4seasons.": Adapter("booked4seasons", "product.booked4seasons", "booking-operation"),
    "trading.operations.": Adapter("trading", "product.trading-nonfinancial", "nonfinancial-trading-operation"),
    "real-wallet.operations.": Adapter("trading", "product.trading-nonfinancial", "nonfinancial-wallet-operation"),
    "privacy.": Adapter("privacy", "privacy", "data-rights-operation"),
}


def adapter_for(command_type: str) -> Adapter | None:
    for prefix, adapter in ADAPTERS_BY_PREFIX.items():
        if command_type.startswith(prefix):
            return adapter
    return None
