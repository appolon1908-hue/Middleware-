from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

import httpx
import pytest
from fastapi.testclient import TestClient

from app.contracts import ROUTE_BY_PATH
from app.main import create_app
from app.models import EventEnvelope
from app.storage import OutboxRecord
from app.telephony_projection import (
    MIDDLEWARE_TO_ODOO_EVENT,
    ODOO_CALL_EVENT_DESTINATION,
    ODOO_CALL_EVENT_OUTBOX_TYPE,
    ODOO_CALL_EVENT_PATH,
    ODOO_EVENT_STATE,
    OdooCallEventDispatcher,
    TelephonyProjectionError,
    build_odoo_call_event,
    odoo_payload_hash,
)
from app.worker import KnownSafeRetryError

from .conftest import make_event, signed_headers


SECRET = b"telephony-test-secret-that-is-at-least-thirty-two-bytes"


def lifecycle_payload(**values):
    payload = {
        "schema_version": "1.0",
        "business_unit_id": "BU-1",
        "campaign_id": "CAMPAIGN-1",
        "call_id": "call-00000001",
        "asterisk_uniqueid": "1710000000.1",
        "linkedid": "1710000000.1",
        "agent_id": "AGENT-6101",
        "extension": "6101",
        "keycloak_subject": "11111111-1111-4111-8111-111111111111",
        "sequence": 1,
        "direction": "inbound",
        "caller_number": "+18095550100",
        "destination_number": "+18095550101",
    }
    payload.update(values)
    return payload


def lifecycle_event(
    event_type="codestra.vicidial.call.lifecycle.created",
    **payload_values,
):
    value = make_event(
        producer="vicidial-adapter",
        event_type=event_type,
        event_id="evt-telephony-00000001",
        data=lifecycle_payload(**payload_values),
    )
    value["occurred_at"] = "2026-09-04T12:00:00.987654Z"
    value["received_at"] = "2026-09-04T12:00:01Z"
    return EventEnvelope.model_validate(value)


def outbox_record(payload):
    return OutboxRecord(
        id=41,
        tenant_id=payload["tenant_id"],
        destination=ODOO_CALL_EVENT_DESTINATION,
        event_type=ODOO_CALL_EVENT_OUTBOX_TYPE,
        idempotency_key="odoo-call-event:" + payload["event_id"],
        payload=payload,
        attempt_count=1,
    )


def test_all_lifecycle_events_map_to_supported_odoo_states():
    assert len(MIDDLEWARE_TO_ODOO_EVENT) == 16
    for source, target in MIDDLEWARE_TO_ODOO_EVENT.items():
        assert source.startswith("codestra.vicidial.call.lifecycle.")
        assert target in ODOO_EVENT_STATE


def test_build_call_event_and_match_odoo_semantic_hash():
    projection = build_odoo_call_event(lifecycle_event())
    assert projection["event_type"] == "call.created"
    assert projection["tenant_id"] == "tenant-1"
    assert projection["call_id"] == "call-00000001"
    assert projection["sequence"] == 1
    assert projection["timestamp"] == "2026-09-04T12:00:00.987654Z"

    normalized = dict(projection)
    normalized["timestamp"] = "2026-09-04 12:00:00"
    normalized["state"] = "new"
    expected = hashlib.sha256(
        json.dumps(
            normalized,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    assert odoo_payload_hash(projection) == expected


@pytest.mark.parametrize(
    ("source_type", "target_type"),
    sorted(MIDDLEWARE_TO_ODOO_EVENT.items()),
)
def test_each_lifecycle_event_projects(source_type, target_type):
    extra = {}
    if source_type.endswith("recording.available"):
        extra = {
            "recording_id": "recording-1",
            "recording_reference": "restricted/recording-1.wav",
        }
    if source_type.endswith("transfer.completed"):
        extra = {
            "transfer_destination": "SUPERVISOR-6901",
            "transfer_type": "attended",
        }
    projection = build_odoo_call_event(lifecycle_event(source_type, **extra))
    assert projection["event_type"] == target_type


def test_invalid_lifecycle_payload_fails_closed():
    with pytest.raises(TelephonyProjectionError):
        build_odoo_call_event(lifecycle_event(caller_number="8095550100"))
    with pytest.raises(TelephonyProjectionError):
        build_odoo_call_event(lifecycle_event(unexpected="value"))
    with pytest.raises(TelephonyProjectionError):
        build_odoo_call_event(
            lifecycle_event(
                "codestra.vicidial.call.lifecycle.transfer.completed"
            )
        )
    with pytest.raises(TelephonyProjectionError):
        build_odoo_call_event(
            lifecycle_event(
                "codestra.vicidial.call.lifecycle.recording.available"
            )
        )


def test_runtime_accepts_valid_lifecycle_event(test_settings, runtime):
    path = "/api/v1/vicidial/events"
    route = ROUTE_BY_PATH[path]
    event = lifecycle_event().model_dump(mode="json")
    body, headers = signed_headers(
        path=path,
        producer=route.producer_client_id,
        scope=route.required_scope,
        event=event,
    )
    app = create_app(settings=test_settings, runtime=runtime)
    with TestClient(app) as client:
        response = client.post(path, content=body, headers=headers)
    assert response.status_code == 202, response.text


def test_runtime_rejects_malformed_lifecycle_event_before_acceptance(
    test_settings,
    runtime,
):
    path = "/api/v1/vicidial/events"
    route = ROUTE_BY_PATH[path]
    event = lifecycle_event().model_dump(mode="json")
    event["payload"]["caller_number"] = "not-e164"
    body, headers = signed_headers(
        path=path,
        producer=route.producer_client_id,
        scope=route.required_scope,
        event=event,
    )
    app = create_app(settings=test_settings, runtime=runtime)
    with TestClient(app) as client:
        response = client.post(path, content=body, headers=headers)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_request"


@pytest.mark.asyncio
async def test_dispatcher_posts_signed_event_and_validates_response():
    projection = build_odoo_call_event(lifecycle_event())
    requests = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.method == "POST"
        assert request.url.path == ODOO_CALL_EVENT_PATH
        body = request.content
        timestamp = request.headers["X-Codestra-Timestamp"]
        assert request.headers["X-Codestra-Signature"] == (
            OdooCallEventDispatcher._post_signature(SECRET, timestamp, body)
        )
        assert request.headers["X-Codestra-Event-ID"] == projection["event_id"]
        return httpx.Response(
            202,
            json={
                "duplicate": False,
                "applied": True,
                "state": "new",
                "call_id": projection["call_id"],
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        dispatcher = OdooCallEventDispatcher(
            client=client,
            base_url="https://odoo.example.test",
            default_secret=SECRET,
            tenant_secrets={},
        )
        await dispatcher(outbox_record(projection))

    assert len(requests) == 1


@pytest.mark.asyncio
async def test_dispatcher_reconciles_ambiguous_post_with_exact_readback():
    projection = build_odoo_call_event(lifecycle_event())
    methods = []

    async def handler(request: httpx.Request) -> httpx.Response:
        methods.append(request.method)
        if request.method == "POST":
            return httpx.Response(503, json={"error": "ambiguous"})
        assert request.url.path == ODOO_CALL_EVENT_PATH + "/" + projection["event_id"]
        timestamp = request.headers["X-Codestra-Timestamp"]
        expected = OdooCallEventDispatcher._readback_signature(
            SECRET,
            timestamp,
            request.url.path,
            projection["event_id"],
            projection["tenant_id"],
        )
        assert request.headers["X-Codestra-Signature"] == expected
        return httpx.Response(
            200,
            json={
                "schema_version": "1.0",
                "event_id": projection["event_id"],
                "tenant_id": projection["tenant_id"],
                "call_id": projection["call_id"],
                "event_type": projection["event_type"],
                "sequence": projection["sequence"],
                "processing_state": "processed",
                "payload_hash": odoo_payload_hash(projection),
                "correlation_id": projection["correlation_id"],
                "call_state": "new",
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        dispatcher = OdooCallEventDispatcher(
            client=client,
            base_url="https://odoo.example.test",
            default_secret=SECRET,
            tenant_secrets={},
        )
        await dispatcher(outbox_record(projection))

    assert methods == ["POST", "GET"]


@pytest.mark.asyncio
async def test_dispatcher_retries_only_when_readback_proves_absence():
    projection = build_odoo_call_event(lifecycle_event())

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503 if request.method == "POST" else 404)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        dispatcher = OdooCallEventDispatcher(
            client=client,
            base_url="https://odoo.example.test",
            default_secret=SECRET,
            tenant_secrets={},
        )
        with pytest.raises(KnownSafeRetryError):
            await dispatcher(outbox_record(projection))


@pytest.mark.asyncio
async def test_dispatcher_refuses_mismatched_readback():
    projection = build_odoo_call_event(lifecycle_event())

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(503)
        return httpx.Response(
            200,
            json={
                "event_id": projection["event_id"],
                "tenant_id": projection["tenant_id"],
                "call_id": "different-call",
                "event_type": projection["event_type"],
                "sequence": projection["sequence"],
                "processing_state": "processed",
                "payload_hash": odoo_payload_hash(projection),
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        dispatcher = OdooCallEventDispatcher(
            client=client,
            base_url="https://odoo.example.test",
            default_secret=SECRET,
            tenant_secrets={},
        )
        with pytest.raises(TelephonyProjectionError):
            await dispatcher(outbox_record(projection))


def test_dispatcher_requires_https_origin():
    with pytest.raises(ValueError):
        OdooCallEventDispatcher(
            client=httpx.AsyncClient(),
            base_url="http://odoo.example.test",
            default_secret=SECRET,
            tenant_secrets={},
        )


def test_projection_timestamp_is_timezone_aware():
    projection = build_odoo_call_event(lifecycle_event())
    parsed = datetime.fromisoformat(projection["timestamp"].replace("Z", "+00:00"))
    assert parsed.tzinfo is not None
    assert parsed.astimezone(timezone.utc).year == 2026
