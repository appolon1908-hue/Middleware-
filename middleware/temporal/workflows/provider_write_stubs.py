"""Source-only Temporal workflow contract stubs for Pass 1 provider adapters.

These are data contracts, not registered Temporal workflows. Existing runtime workflows
remain untouched until a separate reviewed wiring pass binds the new adapter package to
the durable command ledger.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ProviderWriteIntent:
    provider: str
    command_type: str
    payload: dict[str, Any]
    idempotency_key: str
    correlation_id: str
    request_id: str


@dataclass(frozen=True)
class ProviderWriteOutcome:
    provider: str
    command_type: str
    provider_ref: str | None
    state: str
    readback_verified: bool


WORKFLOW_STUB_STATUS = "SOURCE_ONLY_NOT_REGISTERED"
EXTERNAL_EFFECTS_ENABLED = False
