import json
from uuid import uuid4
import pytest
from pydantic import ValidationError

from app.schemas.registry import REGISTRY, parse_event


def event(event_type="vicidial.call.ended", payload=None):
    return {
        "schema_version": "1.0", "event_id": str(uuid4()),
        "event_type": event_type, "occurred_at": "2026-07-24T20:00:00Z",
        "correlation_id": "contract-test", "client_instance": "vicidial-server-b",
        "payload": payload or {
            "call_id": "synthetic-1", "ended_at": "2026-07-24T20:00:00Z",
            "duration_seconds": 0, "direction": "outbound",
        },
    }


def test_every_registry_entry_has_strict_v1_schema():
    assert len(REGISTRY) == 14
    for definition in REGISTRY.values():
        assert definition["version"] == "1.0"
        assert definition["model"].model_json_schema()["additionalProperties"] is False


def test_call_ended_parses_and_unknown_fields_are_rejected():
    value = event()
    envelope, payload = parse_event(json.dumps(value).encode(), frozenset({value["event_type"]}))
    assert envelope.event_type == "vicidial.call.ended"
    value["payload"]["telephone_number"] = "+10000000000"
    with pytest.raises(ValidationError):
        parse_event(json.dumps(value).encode(), frozenset({value["event_type"]}))


def test_disabled_and_unsupported_event_types_are_rejected():
    with pytest.raises(ValueError, match="not enabled"):
        parse_event(json.dumps(event()).encode(), frozenset())
    value = event("vicidial.unknown")
    with pytest.raises(ValueError, match="not enabled"):
        parse_event(json.dumps(value).encode(), frozenset({"vicidial.unknown"}))
