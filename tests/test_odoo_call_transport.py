from __future__ import annotations

import hashlib
import hmac
from datetime import datetime, timezone
from typing import Any

import httpx
import pytest

from app.odoo_call_transport import (
    CALL_EVENT_PATH,
    CALL_EVENT_STATUS_PATH,
    OdooCallEventConfigurationError,
    OdooCallEventDispatcher,
    OdooCallEventTransportError,
)
from app.storage import OutboxRecord
from app.vicidial_call_projection import (
    ODOO_CALL_EVENT_DESTINATION,
    ODOO_CALL_EVENT_OUTBOX_TYPE,
)
from app.worker import KnownSafeRetryError

BASE_URL = "https://odoo.internal.invalid"
SECRET = b"synthetic-odoo-call-event-secret-32bytes"
TENANT = "codestra"


def call_event(**overrides: Any) -> dict[str, Any]:
    result: dict[str, Any] = {
        "schema_version": "1.0",
        "event_id": "vici-event-00000001",
        "event_type": "call.ringing",
        "timestamp": datetime(2026, 9, 4, 16, 0, tzinfo=timezone.utc).isoformat(),
        "correlation_id": "corr-vici-call-00000001",
        "tenant_id": TENANT,
        "business_unit_id": "BU-TRANSPORT",
        "campaign_id": "TRANSPORT",
        "call_id": "vici-call-00000001",
        "asterisk_uniqueid": "1788547200.101",
        "linkedid": "1788547200.101",
        "agent_id": "agent-6104",
        "extension": "6104",
        "sequence": 2,
        "keycloak_subject": "00000000-0000-4000-8000-000000006104",
        "direction": "inbound",
        "caller_number": "+18095550100",
    }
    result.update(overrides)
    return result


def record(payload: dict[str, Any] | None = None, **overrides: Any) -> OutboxRecord:
    body = payload or call_event()
    values: dict[str, Any] = {
        "id": 17,
        "tenant_id": body["tenant_id"],
        "destination": ODOO_CALL_EVENT_DESTINATION,
        "event_type": ODOO_CALL_EVENT_OUTBOX_TYPE,
        "idempotency_key": body["event_id"],
        "payload": body,
        "attempt_count": 1,
    }
    values.update(overrides)
    return OutboxRecord(**values)


def dispatcher(handler, *, secrets: dict[str, bytes] | None = None):
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return OdooCallEventDispatcher(
        client=client,
        base_url=BASE_URL,
        secrets=secrets or {},
        default_secret=SECRET,
    )


def expected_signature(request: httpx.Request, secret: bytes = SECRET) -> str:
    return hmac.new(
        secret,
        request.headers["X-Codestra-Timestamp"].encode()
        + b"."
        + request.content,
        hashlib.sha256,
    ).hexdigest()


@pytest.mark.asyncio
async def test_post_uses_the_exact_odoo_call_event_hmac_contract() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(202, json={"applied": True})

    await dispatcher(handler).dispatch(record())
    assert len(seen) == 1
    request = seen[0]
    assert request.url.path == CALL_EVENT_PATH
    assert request.headers["X-Codestra-Event-ID"] == "vici-event-00000001"
    assert hmac.compare_digest(
        request.headers["X-Codestra-Signature"],
        expected_signature(request),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [200, 202])
async def test_accepted_and_duplicate_responses_are_terminal_success(status: int) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"duplicate": status == 200})

    await dispatcher(handler).dispatch(record())


@pytest.mark.asyncio
async def test_per_tenant_secret_is_preferred() -> None:
    tenant_secret = b"tenant-specific-call-event-secret-32bytes"
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(202)

    await dispatcher(handler, secrets={TENANT: tenant_secret}).dispatch(record())
    assert hmac.compare_digest(
        seen[0].headers["X-Codestra-Signature"],
        expected_signature(seen[0], tenant_secret),
    )


@pytest.mark.asyncio
async def test_read_timeout_is_resolved_by_matching_readback() -> None:
    paths: list[str] = []
    payload = call_event()

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if request.method == "POST":
            raise httpx.ReadTimeout("response lost", request=request)
        return httpx.Response(
            200,
            json={
                "event_id": payload["event_id"],
                "event_type": payload["event_type"],
                "call_id": payload["call_id"],
                "sequence": payload["sequence"],
            },
        )

    await dispatcher(handler).dispatch(record(payload))
    assert paths == [
        CALL_EVENT_PATH,
        CALL_EVENT_STATUS_PATH.format(event_id=payload["event_id"]),
    ]


@pytest.mark.asyncio
async def test_readback_404_is_the_only_safe_retry_after_an_unknown_outcome() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            raise httpx.ReadTimeout("response lost", request=request)
        return httpx.Response(404, json={"detail": "not found"})

    with pytest.raises(KnownSafeRetryError):
        await dispatcher(handler).dispatch(record())


@pytest.mark.asyncio
async def test_mismatched_readback_stays_quarantined() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(503)
        return httpx.Response(
            200,
            json={
                "event_id": "another-event",
                "event_type": "call.ringing",
                "call_id": "another-call",
                "sequence": 2,
            },
        )

    with pytest.raises(OdooCallEventTransportError) as raised:
        await dispatcher(handler).dispatch(record())
    assert not isinstance(raised.value, KnownSafeRetryError)


@pytest.mark.asyncio
async def test_connection_failure_before_send_is_safe_to_retry() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    with pytest.raises(KnownSafeRetryError):
        await dispatcher(handler).dispatch(record())


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "overrides",
    [
        {"destination": "nats-jetstream"},
        {"event_type": "other.event"},
        {"tenant_id": "other-tenant"},
        {"idempotency_key": "other-event-id"},
    ],
)
async def test_outbox_identity_must_match_the_projected_event(
    overrides: dict[str, Any],
) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("invalid outbox rows must never be sent")

    with pytest.raises(OdooCallEventTransportError):
        await dispatcher(handler).dispatch(record(**overrides))


def test_plaintext_endpoint_and_missing_secret_are_refused() -> None:
    with pytest.raises(OdooCallEventConfigurationError):
        OdooCallEventDispatcher(
            client=httpx.AsyncClient(),
            base_url="http://odoo.invalid",
            secrets={},
            default_secret=SECRET,
        )
    with pytest.raises(OdooCallEventConfigurationError):
        OdooCallEventDispatcher(
            client=httpx.AsyncClient(),
            base_url=BASE_URL,
            secrets={},
            default_secret=None,
        )
