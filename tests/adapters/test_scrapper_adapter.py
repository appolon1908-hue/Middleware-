from __future__ import annotations

import pytest

from middleware.adapters.base import MemoryIdempotencyStore, ProviderError, ProviderResponse
from middleware.adapters.scrapper.adapter import ScrapperAdapter


class Transport:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls = 0

    def execute(self, adapter, request):
        assert adapter == "scrapper"
        assert request.path == "/api/v2/jobs"
        assert request.body["seedUrls"] == ["https://example.test"]
        self.calls += 1
        if self.fail:
            raise RuntimeError("scrapper unavailable")
        return ProviderResponse("job-1", "accepted", {"id": "job-1"})

    def read_back(self, adapter, *, provider_ref, command_type, payload):
        assert adapter == "scrapper"
        return ProviderResponse(provider_ref, "queued", {"id": provider_ref})


def adapter(transport=None):
    return ScrapperAdapter(store=MemoryIdempotencyStore(), transport=transport or Transport())


def command(target):
    return target.execute_command(
        command_type="dispatch_scrape_job",
        payload={"tenant_id": "tenant-1", "job_type": "url", "target": "https://example.test", "depth": 1},
        idempotency_key="idem-scrapper-1",
        correlation_id="corr-scrapper-1",
        request_id="req-scrapper-1",
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
    assert target.store.get_execution("scrapper", "idem-scrapper-1").status == "failed"


def test_keyword_job_fails_closed_without_provider_binding():
    target = adapter()
    with pytest.raises(ProviderError, match="no approved provider binding"):
        target.execute_command(
            command_type="dispatch_scrape_job",
            payload={"job_type": "keyword", "target": "plumber", "depth": 1},
            idempotency_key="idem-scrapper-2",
            correlation_id="corr-scrapper-2",
            request_id="req-scrapper-2",
        )


def test_handle_webhook_known_event():
    assert adapter().handle_webhook(event_type="job.completed", payload={}, provider_event_id="evt-1").status == "processed"


def test_handle_webhook_duplicate_event():
    target = adapter()
    target.handle_webhook(event_type="job.partial", payload={}, provider_event_id="evt-1")
    assert target.handle_webhook(event_type="job.partial", payload={}, provider_event_id="evt-1").status == "ignored"


def test_handle_webhook_unknown_event():
    assert adapter().handle_webhook(event_type="domain.discovered", payload={}, provider_event_id="evt-2").status == "ignored"


def test_verify_capability():
    target = adapter()
    assert target.verify_capability("url_scrape") is True
    assert target.verify_capability("domain_crawl") is False
    assert target.verify_capability("unknown") is False
