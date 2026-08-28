from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.models import EventEnvelope


def payload(schema_version: int) -> dict:
    return {
        "specversion": "1.0",
        "id": "evt-schema",
        "type": "codestra.test.event",
        "source": "urn:codestra:test-source",
        "subject": "subject/1",
        "time": datetime.now(timezone.utc),
        "tenant_id": "tenant-test",
        "correlation_id": "corr-1",
        "causation_id": "cause-1",
        "idempotency_key": "idem-schema-1",
        "schema_version": schema_version,
        "data": {},
    }


def test_schema_version_one_is_supported() -> None:
    assert EventEnvelope.model_validate(payload(1)).schema_version == 1


@pytest.mark.parametrize("unsupported", [0, 2, 99])
def test_unsupported_schema_versions_fail_closed(unsupported: int) -> None:
    with pytest.raises(ValidationError):
        EventEnvelope.model_validate(payload(unsupported))
