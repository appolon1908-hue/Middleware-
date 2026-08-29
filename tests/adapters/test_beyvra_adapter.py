from __future__ import annotations

import pytest

from middleware.adapters.base import MemoryIdempotencyStore, ProviderError, ProviderResponse
from middleware.adapters.beyvra.adapter import BeyvraAdapter


class Transport:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls = 0

    def execute(self, adapter, request):
        assert adapter == "beyvra"
        assert request.path == "/v1/automation/notifications"
        self.calls += 1
        if self.fail:
            raise RuntimeError("beyvra unavailable")
        return ProviderResponse("op-1", "accepted", {"operation_id": "op-1"})

    def read_back(self, adapter, *, provider_ref, command_type, payload):
        assert adapter == "beyvra"
        return ProviderResponse(provider_ref, "completed", {"operation_id": provider_ref})


def adapter(transport=None):
    return BeyvraAdapter(store=MemoryIdempotencyStore(), transport=transport or Transport())


def command(target):
    return target.execute_command(
        command_type="notify_call_completed",
        payload={"contact_id": "contact-1", "call_ref": "call-1", "disposition": "answered", "duration_seconds": 42},
        idempotency_key="idem-beyvra-1",
        correlation_id="corr-beyvra-1",
        request_id="req-beyvra-1",
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
    assert target.store.get_execution("beyvra", "idem-beyvra-1").status == "failed"


def test_financial_fields_are_rejected():
    target = adapter()
    with pytest.raises(ProviderError, match="financial/trading"):
        target.execute_command(
            command_type="request_notification",
            payload={"wallet_id": "wallet-1"},
            idempotency_key="idem-beyvra-2",
            correlation_id="corr-beyvra-2",
            request_id="req-beyvra-2",
        )


def test_handle_webhook_known_event():
    assert adapter().handle_webhook(event_type="operation.completed", payload={}, provider_event_id="evt-1").status == "processed"


def test_handle_webhook_duplicate_event():
    target = adapter()
    target.handle_webhook(event_type="operation.failed", payload={}, provider_event_id="evt-1")
    assert target.handle_webhook(event_type="operation.failed", payload={}, provider_event_id="evt-1").status == "ignored"


def test_handle_webhook_unknown_event():
    assert adapter().handle_webhook(event_type="trade.executed", payload={}, provider_event_id="evt-2").status == "ignored"


def test_verify_capability():
    target = adapter()
    assert target.verify_capability("notifications") is True
    assert target.verify_capability("trade_execution") is False
    assert target.verify_capability("unknown") is False
