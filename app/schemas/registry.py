"""Strict, versioned, data-minimised VICIdial event registry."""
from datetime import datetime
from typing import Literal, cast
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CallIdentity(StrictModel):
    call_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_.:-]+$")


class CallEnded(CallIdentity):
    ended_at: datetime
    duration_seconds: int = Field(ge=0, le=86400)
    direction: Literal["inbound", "outbound"]


class DispositionApplied(CallIdentity):
    disposition_code: str = Field(min_length=1, max_length=32, pattern=r"^[A-Z0-9_-]+$")
    applied_at: datetime


class Callback(CallIdentity):
    callback_id: str = Field(min_length=1, max_length=128)
    scheduled_at: datetime


class CallbackCompleted(CallIdentity):
    callback_id: str = Field(min_length=1, max_length=128)
    completed_at: datetime
    outcome: str = Field(min_length=1, max_length=32)


class AgentState(StrictModel):
    agent_id: str = Field(min_length=1, max_length=64)
    state: Literal["available", "busy", "pause", "after_call_work", "offline"]
    changed_at: datetime


class RecordingReady(CallIdentity):
    recording_id: str = Field(min_length=1, max_length=128)
    ready_at: datetime


class QueueAbandoned(CallIdentity):
    queue_id: str = Field(min_length=1, max_length=64)
    abandoned_at: datetime
    wait_seconds: int = Field(ge=0, le=86400)


class TransferCompleted(CallIdentity):
    transfer_id: str = Field(min_length=1, max_length=128)
    completed_at: datetime
    target_type: Literal["agent", "queue", "external"]


class HopperState(StrictModel):
    campaign_id: str = Field(min_length=1, max_length=64)
    remaining: int = Field(ge=0)
    observed_at: datetime


class CarrierState(StrictModel):
    carrier_id: str = Field(min_length=1, max_length=64)
    observed_at: datetime
    reason_code: str = Field(min_length=1, max_length=64)


class PredictiveThrottled(StrictModel):
    campaign_id: str = Field(min_length=1, max_length=64)
    observed_at: datetime
    reason_code: str = Field(min_length=1, max_length=64)


PAYLOADS = {
    "vicidial.call.ended": CallEnded,
    "vicidial.disposition.applied": DispositionApplied,
    "vicidial.callback.created": Callback,
    "vicidial.callback.updated": Callback,
    "vicidial.callback.completed": CallbackCompleted,
    "vicidial.agent.state.changed": AgentState,
    "vicidial.recording.ready": RecordingReady,
    "vicidial.queue.abandoned": QueueAbandoned,
    "vicidial.transfer.completed": TransferCompleted,
    "vicidial.hopper.low": HopperState,
    "vicidial.hopper.empty": HopperState,
    "vicidial.carrier.degraded": CarrierState,
    "vicidial.carrier.failover": CarrierState,
    "vicidial.predictive.throttled": PredictiveThrottled,
}


class Envelope(StrictModel):
    schema_version: Literal["1.0"]
    event_id: UUID
    event_type: str = Field(min_length=1, max_length=100)
    occurred_at: datetime
    correlation_id: str = Field(min_length=1, max_length=128)
    client_instance: str = Field(min_length=1, max_length=64)
    business_unit: str | None = Field(default=None, max_length=64)
    payload: dict


REGISTRY = {
    name: {
        "version": "1.0",
        "model": model,
        "deprecated": False,
        "production_enabled": name == "vicidial.call.ended",
    }
    for name, model in PAYLOADS.items()
}


def parse_event(raw: bytes, enabled: frozenset[str]) -> tuple[Envelope, StrictModel]:
    envelope = Envelope.model_validate_json(raw)
    definition = REGISTRY.get(envelope.event_type)
    if definition is None or envelope.event_type not in enabled:
        raise ValueError("event type is not enabled")
    payload_model = cast(type[StrictModel], definition["model"])
    payload = payload_model.model_validate(envelope.payload)
    return envelope, payload
