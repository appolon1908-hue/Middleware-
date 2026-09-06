import hashlib
import hmac
import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException, Response

from app.api.v1 import provider_webhooks
from app.db.models import IntegrationDelivery, OdooResultDelivery, OutboxEvent


VICIDIAL = {
    "call_id": "stage2-test-001",
    "phone_number": "+15555550199",
    "disposition": "ANSWER",
    "call_time": 67,
    "campaign_id": "stage2-verification",
}


class Request:
    def __init__(self, payload):
        self.raw = json.dumps(payload, separators=(",", ":")).encode()

    async def body(self):
        return self.raw


class Session:
    def __init__(self, existing=None):
        self.existing = existing
        self.added = []
        self.commits = 0
        self.rollbacks = 0

    async def execute(self, *_args, **_kwargs):
        return None

    async def scalar(self, _query):
        return self.existing

    def add(self, value):
        self.added.append(value)

    async def flush(self):
        self.added[0].id = 17

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1


def signature(request, secret):
    return hmac.new(secret.encode(), request.raw, hashlib.sha256).hexdigest()


@pytest.mark.asyncio
async def test_valid_signature_persists_odoo_intent_and_platform_event(monkeypatch):
    request = Request(VICIDIAL)
    session = Session()
    monkeypatch.setattr(provider_webhooks.settings, "vicidial_webhook_secret", "v" * 32)
    monkeypatch.setattr(provider_webhooks.settings, "odoo_write_enabled", True)
    result = await provider_webhooks.vicidial_call_result(
        request, Response(), signature(request, "v" * 32), session
    )
    assert result["accepted"] is True
    assert any(
        isinstance(item, IntegrationDelivery) and item.status == "pending"
        for item in session.added
    )
    assert any(
        isinstance(item, OdooResultDelivery)
        and item.status == "PENDING"
        and item.standard_result_json["operation"] == "log_call_result"
        for item in session.added
    )
    assert any(
        isinstance(item, OutboxEvent) and item.topic == "call_disposition_updated"
        for item in session.added
    )


@pytest.mark.asyncio
async def test_invalid_signature_is_rejected(monkeypatch):
    monkeypatch.setattr(provider_webhooks.settings, "vicidial_webhook_secret", "v" * 32)
    with pytest.raises(HTTPException) as raised:
        await provider_webhooks.vicidial_call_result(
            Request(VICIDIAL), Response(), "0" * 64, Session()
        )
    assert raised.value.status_code == 403


@pytest.mark.asyncio
async def test_duplicate_call_id_is_safe_noop(monkeypatch):
    request = Request(VICIDIAL)
    digest = hashlib.sha256(request.raw).hexdigest()
    existing = SimpleNamespace(
        request_hash=digest,
        response={"accepted": True, "event_id": "vicidial:stage2-test-001"},
    )
    session = Session(existing)
    monkeypatch.setattr(provider_webhooks.settings, "vicidial_webhook_secret", "v" * 32)
    result = await provider_webhooks.vicidial_call_result(
        request, Response(), signature(request, "v" * 32), session
    )
    assert result["accepted"] is True
    assert session.added == []
    assert session.commits == 1


def test_disposition_map_covers_all_required_codes():
    assert set(provider_webhooks.DISPOSITION_MAP) == {
        "ANSWER",
        "NOANSWER",
        "BUSY",
        "SVUNREACH",
        "DONTCALL",
        "CALLBK",
        "VOICEMAIL",
        "SALE",
        "DROP",
        "NI",
    }


@pytest.mark.asyncio
async def test_odoo_write_is_disabled_by_flag(monkeypatch):
    request = Request(VICIDIAL)
    session = Session()
    monkeypatch.setattr(provider_webhooks.settings, "vicidial_webhook_secret", "v" * 32)
    monkeypatch.setattr(provider_webhooks.settings, "odoo_write_enabled", False)
    result = await provider_webhooks.vicidial_call_result(
        request, Response(), signature(request, "v" * 32), session
    )
    delivery = next(
        item for item in session.added if isinstance(item, IntegrationDelivery)
    )
    assert delivery.status == "disabled"
    assert not any(isinstance(item, OdooResultDelivery) for item in session.added)
    assert result["odoo_write"] == "disabled"


@pytest.mark.asyncio
async def test_telnexa_valid_signature_publishes_sms_received(monkeypatch):
    request = Request(
        {
            "message_id": "sms-stage2-001",
            "from": "+15555550199",
            "body": "Hello",
            "received_at": "2026-08-29T06:00:00Z",
        }
    )
    session = Session()
    monkeypatch.setattr(provider_webhooks.settings, "telnexa_webhook_secret", "t" * 32)
    result = await provider_webhooks.telnexa_inbound_sms(
        request, Response(), signature(request, "t" * 32), session
    )
    assert result["accepted"] is True
    assert any(
        isinstance(item, OutboxEvent) and item.topic == "sms_received"
        for item in session.added
    )
