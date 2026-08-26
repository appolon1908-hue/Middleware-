from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class EventEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    specversion: Literal["1.0"]
    id: str = Field(min_length=1, max_length=128)
    type: str = Field(pattern=r"^codestra\.[a-z0-9_]+(?:\.[a-z0-9_]+)+$", max_length=160)
    source: str = Field(pattern=r"^urn:codestra:[a-z0-9][a-z0-9-]*$", max_length=160)
    subject: str = Field(min_length=1, max_length=256)
    time: datetime
    tenant_id: str = Field(min_length=1, max_length=128)
    correlation_id: str = Field(min_length=1, max_length=128)
    causation_id: str = Field(min_length=1, max_length=128)
    idempotency_key: str = Field(min_length=8, max_length=256)
    schema_version: int = Field(ge=1)
    traceparent: str | None = Field(default=None, min_length=1, max_length=256)
    actor: dict[str, Any] | None = None
    delivery_attempt: int | None = Field(default=None, ge=1)
    data: dict[str, Any]

    @field_validator("time")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("time must include an explicit timezone")
        return value


class IngressResult(BaseModel):
    event_id: str
    tenant_id: str
    status: Literal["accepted", "duplicate"]
    duplicate: bool
    correlation_id: str
