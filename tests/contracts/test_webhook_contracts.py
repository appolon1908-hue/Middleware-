from __future__ import annotations

from middleware.commands.schemas import BEYVRA_INBOUND_COMMANDS, PROVIDER_COMMANDS
from middleware.webhooks.handlers import WEBHOOK_EVENT_SCHEMAS, validate_webhook_envelope


def test_telnexa_webhook_schema_valid():
    assert {"sms.delivered", "sms.failed"} <= WEBHOOK_EVENT_SCHEMAS["telnexa"]
    validate_webhook_envelope(provider="telnexa", event_type="sms.delivered", payload={}, provider_event_id="evt-t-1")


def test_klyrow_webhook_schema_valid():
    assert {"email.delivered", "email.bounced", "email.complained"} <= WEBHOOK_EVENT_SCHEMAS["klyrow"]
    validate_webhook_envelope(provider="klyrow", event_type="email.delivered", payload={}, provider_event_id="evt-k-1")


def test_vicidial_webhook_schema_valid():
    assert {"lead.answered", "lead.dnc", "campaign.completed"} <= WEBHOOK_EVENT_SCHEMAS["vicidial"]
    validate_webhook_envelope(provider="vicidial", event_type="lead.dnc", payload={}, provider_event_id="evt-v-1")


def test_scrapper_webhook_schema_valid():
    assert WEBHOOK_EVENT_SCHEMAS["scrapper"] == {"job.completed", "job.failed", "job.partial"}
    validate_webhook_envelope(provider="scrapper", event_type="job.completed", payload={}, provider_event_id="evt-s-1")


def test_beyvra_inbound_command_schema_valid():
    assert BEYVRA_INBOUND_COMMANDS["scrape"]["routable"] is True
    assert BEYVRA_INBOUND_COMMANDS["scrape"]["command_type"] in PROVIDER_COMMANDS["scrapper"]
    # Source truth wins over the aspirational mission: Telnexa has no voice
    # command API and Klyrow has no contact-enrichment API today.
    assert BEYVRA_INBOUND_COMMANDS["dial"]["routable"] is False
    assert BEYVRA_INBOUND_COMMANDS["enrich"]["routable"] is False
