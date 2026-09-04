from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest

from app.models import EventEnvelope, IngressResult
from app.vicidial_call_projection import (
    EVENT_TYPE_MAP,
    ODOO_CALL_EVENT_DESTINATION,
    CallProjectionError,
    MemoryCallProjectionStore,
    ProjectingInboxStore,
    build_odoo_call_event,
)


def lifecycle_event(
    event_type: str = "codestra.vicidial.call.lifecycle.created",
    *,
    event_id: str = "vici-event-00000001",
    payload: dict[str, Any] | None = None,
) -> EventEnvelope:
    occurred = datetime(2026, 9, 4, 16, 0, tzinfo=timezone.utc)
    body: dict[str, Any] = {
        "schema_version": "1.0",
        "business_unit_id": "BU-TRANSPORT",
        "campaign_id": "TRANSPORT",
        "call_id": "vici-call-00000001",
        "asterisk_uniqueid": "1788547200.101",
        "linkedid": "1788547200.101",
        "agent_id": "agent-6104",
        "extension": "6104",
        "sequence": 1,
        "keycloak_subject": "00000000-0000-4000-8000-000000006104",
        "direction": "inbound",
        "caller_number": "+18095550100",
    }
    if payload:
        body.update(payload)
    return EventEnvelope(
        event_id=event_id,
        event_type=event_type,
        event_version="1.0",
        occurred_at=occurred,
        received_at=occurred,
        source="vicidial-adapter",
        tenant_id="codestra",
        correlation_id="corr-vici-call-00000001",
        causation_id="ami-AgentCalled-1788547200.101",
        idempotency_key=event_id,
        payload=body,
        metadata={"transport": "asterisk-ami"},
    )


@pytest.mark.parametrize(("source_type", "odoo_type"), EVENT_TYPE_MAP.items())
def test_every_ami_lifecycle_type_maps_to_the_odoo_contract(
    source_type: str,
    odoo_type: str,
) -> None:
    result = build_odoo_call_event(lifecycle_event(source_type))
    assert result["event_type"] == odoo_type
    assert result["event_id"] == "vici-event-00000001"
    assert result["tenant_id"] == "codestra"
    assert result["timestamp"] == "2026-09-04T16:00:00Z"


def test_projection_flattens_outer_identity_without_trusting_payload_overrides() -> None:
    event = lifecycle_event()
    result = build_odoo_call_event(event)
    assert result["correlation_id"] == event.correlation_id
    assert result["call_id"] == event.payload["call_id"]
    assert result["sequence"] == 1

    with pytest.raises(CallProjectionError):
        build_odoo_call_event(
            lifecycle_event(payload={"tenant_id": "attacker-selected-tenant"})
        )


@pytest.mark.parametrize(
    "change",
    [
        {"source": "n8n-automation"},
        {"event_type": "codestra.vicidial.call.started"},
        {"idempotency_key": "different-event-identity"},
    ],
)
def test_projection_rejects_noncanonical_source_type_and_identity(
    change: dict[str, str],
) -> None:
    data = lifecycle_event().model_dump()
    data.update(change)
    event = EventEnvelope.model_validate(data)
    with pytest.raises(CallProjectionError):
        build_odoo_call_event(event)


def test_projection_rejects_missing_agent_campaign_or_subject_binding() -> None:
    for field in ("campaign_id", "agent_id", "extension", "keycloak_subject"):
        payload = dict(lifecycle_event().payload)
        payload.pop(field)
        with pytest.raises(CallProjectionError):
            build_odoo_call_event(
                EventEnvelope.model_validate(
                    {**lifecycle_event().model_dump(), "payload": payload}
                )
            )


class FakeInbox:
    def __init__(self) -> None:
        self.duplicate = False
        self.closed = False

    async def accept(self, envelope, **_kwargs):
        return IngressResult(
            event_id=envelope.event_id,
            tenant_id=envelope.tenant_id,
            status="duplicate" if self.duplicate else "accepted",
            duplicate=self.duplicate,
            correlation_id=envelope.correlation_id,
        )

    async def ready(self) -> bool:
        return True

    async def close(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_duplicate_replay_repairs_a_missing_projection() -> None:
    delegate = FakeInbox()
    projector = MemoryCallProjectionStore()
    store = ProjectingInboxStore(delegate, projector, enabled=True)
    event = lifecycle_event()

    await store.accept(
        event,
        producer_client_id="vicidial-adapter",
        body_sha256="a" * 64,
        semantic_sha256="b" * 64,
    )
    assert ("codestra", event.event_id) in projector.rows

    # Simulate projection loss after an accepted event, then replay the exact
    # event. The wrapper projects on duplicates as well as first acceptance.
    projector.rows.clear()
    delegate.duplicate = True
    replay = await store.accept(
        event,
        producer_client_id="vicidial-adapter",
        body_sha256="a" * 64,
        semantic_sha256="b" * 64,
    )
    assert replay.duplicate is True
    assert projector.rows[("codestra", event.event_id)]["call_id"] == event.payload["call_id"]


@pytest.mark.asyncio
async def test_projection_gate_is_closed_without_odoo_write_authority() -> None:
    delegate = FakeInbox()
    projector = MemoryCallProjectionStore()
    store = ProjectingInboxStore(delegate, projector, enabled=False)
    event = lifecycle_event()
    await store.accept(
        event,
        producer_client_id="vicidial-adapter",
        body_sha256="a" * 64,
        semantic_sha256="b" * 64,
    )
    assert projector.rows == {}
    assert ODOO_CALL_EVENT_DESTINATION == "odoo-call-event"


@pytest.mark.asyncio
async def test_same_event_identity_with_changed_payload_is_rejected() -> None:
    projector = MemoryCallProjectionStore()
    first = lifecycle_event()
    await projector.ensure_projection(first)
    changed = lifecycle_event(payload={"caller_number": "+18095550999"})
    with pytest.raises(CallProjectionError):
        await projector.ensure_projection(changed)
