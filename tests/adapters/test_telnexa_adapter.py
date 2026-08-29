from __future__ import annotations

import pytest

from middleware.adapters.base import MemoryIdempotencyStore, ProviderError, ProviderResponse
from middleware.adapters.telnexa.adapter import TelnexaAdapter


class Transport:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls = 0

    def execute(self, adapter, request):
        assert adapter == "telnexa"
        assert request.path == "/send"
        self.calls += 1
        if self.fail:
            raise RuntimeError("provider unavailable")
        return ProviderResponse("sms-1", "accepted", {"queued": True})

    def read_back(self, adapter, *, provider_ref, command_type, payload):
        assert (adapter, provider_ref, command_type) == ("telnexa", "sms-1", "send_sms")
        return ProviderResponse(provider_ref, "delivered", {"status": "delivered"})


def adapter(transport=None):
    return TelnexaAdapter(store=MemoryIdempotencyStore(), transport=transport or Transport())


def command(target):
    return target.execute_command(
        command_type="send_sms",
        payload={"phone_number": "+18005550199", "message": "test"},
        idempotency_key="idem-telnexa-1",
        correlation_id="corr-telnexa-1",
        request_id="req-telnexa-1",
    )


def test_execute_command_success():
    result = command(adapter())
    assert result.success is True
    assert result.provider_ref == "sms-1"


def test_execute_command_idempotent_replay():
    transport = Transport()
    target = adapter(transport)
    command(target)
    replay = command(target)
    assert replay.idempotent_replay is True
    assert transport.calls == 1


def test_execute_command_provider_failure():
    target = adapter(Transport(fail=True))
    with pytest.raises(ProviderError):
        command(target)
    record = target.store.get_execution("telnexa", "idem-telnexa-1")
    assert record and record.status == "failed"


def test_handle_webhook_known_event():
    result = adapter().handle_webhook(event_type="sms.delivered", payload={"id": "sms-1"}, provider_event_id="evt-1")
    assert result.status == "processed"


def test_handle_webhook_duplicate_event():
    target = adapter()
    target.handle_webhook(event_type="sms.delivered", payload={}, provider_event_id="evt-1")
    assert target.handle_webhook(event_type="sms.delivered", payload={}, provider_event_id="evt-1").status == "ignored"


def test_handle_webhook_unknown_event():
    assert adapter().handle_webhook(event_type="call.started", payload={}, provider_event_id="evt-2").status == "ignored"


def test_verify_capability():
    target = adapter()
    assert target.verify_capability("sms") is True
    assert target.verify_capability("outbound_dial") is False
    assert target.verify_capability("unknown") is False
