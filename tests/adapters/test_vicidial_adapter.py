from __future__ import annotations

import pytest

from middleware.adapters.base import MemoryIdempotencyStore, ProviderError, ProviderResponse
from middleware.adapters.vicidial.adapter import VicidialAdapter


class Transport:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls = 0

    def execute(self, adapter, request):
        assert adapter == "vicidial"
        assert request.path == "/v1/leads/publish"
        self.calls += 1
        if self.fail:
            raise RuntimeError("vicidial unavailable")
        return ProviderResponse("lead-1", "accepted", {"external_id": "contact-1"})

    def read_back(self, adapter, *, provider_ref, command_type, payload):
        assert adapter == "vicidial"
        return ProviderResponse(provider_ref, "published", {"external_id": "contact-1"})


def adapter(transport=None):
    return VicidialAdapter(store=MemoryIdempotencyStore(), transport=transport or Transport())


def command(target):
    return target.execute_command(
        command_type="add_to_campaign",
        payload={
            "campaign_id": "CAMP_A",
            "phone_number": "+18005550199",
            "contact_id": "contact-1",
            "dnc_passed": True,
        },
        idempotency_key="idem-vicidial-1",
        correlation_id="corr-vicidial-1",
        request_id="req-vicidial-1",
    )


def test_execute_command_success():
    assert command(adapter()).success is True


def test_execute_command_idempotent_replay():
    transport = Transport()
    target = adapter(transport)
    command(target)
    assert command(target).idempotent_replay is True
    assert transport.calls == 1


def test_execute_command_provider_failure():
    target = adapter(Transport(fail=True))
    with pytest.raises(ProviderError):
        command(target)
    assert target.store.get_execution("vicidial", "idem-vicidial-1").status == "failed"


def test_dnc_gate_is_required():
    target = adapter()
    with pytest.raises(ProviderError, match="DNC gate"):
        target.execute_command(
            command_type="add_to_campaign",
            payload={"campaign_id": "CAMP_A", "phone_number": "+18005550199", "dnc_passed": False},
            idempotency_key="idem-vicidial-2",
            correlation_id="corr-vicidial-2",
            request_id="req-vicidial-2",
        )


def test_handle_webhook_known_event():
    assert adapter().handle_webhook(event_type="lead.answered", payload={}, provider_event_id="evt-1").status == "processed"


def test_handle_webhook_duplicate_event():
    target = adapter()
    target.handle_webhook(event_type="lead.dnc", payload={}, provider_event_id="evt-1")
    assert target.handle_webhook(event_type="lead.dnc", payload={}, provider_event_id="evt-1").status == "ignored"


def test_handle_webhook_unknown_event():
    assert adapter().handle_webhook(event_type="campaign.started", payload={}, provider_event_id="evt-2").status == "ignored"


def test_verify_capability():
    target = adapter()
    assert target.verify_capability("dnc_enforcement") is True
    assert target.verify_capability("outbound_campaign") is False
    assert target.verify_capability("unknown") is False
