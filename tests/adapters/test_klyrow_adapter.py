from __future__ import annotations

import pytest

from middleware.adapters.base import MemoryIdempotencyStore, ProviderError, ProviderResponse
from middleware.adapters.klyrow.adapter import KlyrowAdapter


class Transport:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls = 0

    def execute(self, adapter, request):
        assert adapter == "klyrow"
        assert request.path == "/v1/email/send"
        self.calls += 1
        if self.fail:
            raise RuntimeError("klyrow unavailable")
        return ProviderResponse("msg-1", "accepted", {"message_id": "msg-1"})

    def read_back(self, adapter, *, provider_ref, command_type, payload):
        assert adapter == "klyrow"
        return ProviderResponse(provider_ref, "queued", {"message_id": provider_ref})


def adapter(transport=None):
    return KlyrowAdapter(store=MemoryIdempotencyStore(), transport=transport or Transport())


def command(target):
    return target.execute_command(
        command_type="send_email",
        payload={"tenant_id": "tenant-1", "to": "person@example.test", "subject": "test", "text": "hello"},
        idempotency_key="idem-klyrow-1",
        correlation_id="corr-klyrow-1",
        request_id="req-klyrow-1",
    )


def test_execute_command_success():
    assert command(adapter()).success is True


def test_execute_command_idempotent_replay():
    transport = Transport()
    target = adapter(transport)
    first = command(target)
    second = command(target)
    assert second.provider_ref == first.provider_ref
    assert second.idempotent_replay is True
    assert transport.calls == 1


def test_execute_command_provider_failure():
    target = adapter(Transport(fail=True))
    with pytest.raises(ProviderError):
        command(target)
    assert target.store.get_execution("klyrow", "idem-klyrow-1").status == "failed"


def test_handle_webhook_known_event():
    assert adapter().handle_webhook(event_type="email.delivered", payload={}, provider_event_id="evt-1").status == "processed"


def test_handle_webhook_duplicate_event():
    target = adapter()
    target.handle_webhook(event_type="email.bounced", payload={}, provider_event_id="evt-1")
    assert target.handle_webhook(event_type="email.bounced", payload={}, provider_event_id="evt-1").status == "ignored"


def test_handle_webhook_unknown_event():
    assert adapter().handle_webhook(event_type="contact.enriched", payload={}, provider_event_id="evt-2").status == "ignored"


def test_verify_capability():
    target = adapter()
    assert target.verify_capability("email_delivery") is True
    assert target.verify_capability("enrich") is False
    assert target.verify_capability("unknown") is False
