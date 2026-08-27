"""Immutable data models used by connector manifests and runtime adapters."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping


class ConnectorCell(str, Enum):
    CORE_COMMUNICATIONS = "core-communications"
    BEYVRA_FINANCIAL = "beyvra-financial"
    TELEPHONY_PRIVATE = "telephony-private"


class ConnectorState(str, Enum):
    DECLARED = "DECLARED"
    VALIDATED = "VALIDATED"
    INSTALLED_DISABLED = "INSTALLED_DISABLED"
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    FAILED = "FAILED"


class CommandOutcome(str, Enum):
    ACCEPTED = "ACCEPTED"
    SUBMITTED = "SUBMITTED"
    UNKNOWN = "UNKNOWN"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class ReplayDecision(str, Enum):
    NEW = "NEW"
    EXACT_REPLAY = "EXACT_REPLAY"
    SEMANTIC_CONFLICT = "SEMANTIC_CONFLICT"


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    maximum_attempts: int
    initial_backoff_seconds: float
    maximum_backoff_seconds: float
    jitter_ratio: float
    unknown_outcome_requires_readback: bool = True


@dataclass(frozen=True, slots=True)
class CommandPolicy:
    prefix: str
    required_capability: str
    timeout_seconds: int
    readback_required: bool
    retry_policy: RetryPolicy


@dataclass(frozen=True, slots=True)
class EventPolicy:
    event_type: str
    direction: str


@dataclass(frozen=True, slots=True)
class WebhookPolicy:
    endpoint_key: str
    route_path: str
    signature_algorithm: str
    signature_header: str
    timestamp_header: str
    event_id_header: str
    maximum_clock_skew_seconds: int
    maximum_body_bytes: int
    acknowledgement_deadline_seconds: int
    secret_reference: str


@dataclass(frozen=True, slots=True)
class RuntimeBinding:
    status: str
    base_url: str
    health_path: str
    operation_path_template: str


@dataclass(frozen=True, slots=True)
class AuthenticationPolicy:
    type: str
    audience: str
    scopes: tuple[str, ...]
    secret_references: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ConnectorManifest:
    manifest_version: str
    connector_id: str
    display_name: str
    version: str
    cell: ConnectorCell
    repository: str
    enabled_by_default: bool
    direct_n8n_access: bool
    runtime_binding: RuntimeBinding
    authentication: AuthenticationPolicy
    command_policies: tuple[CommandPolicy, ...]
    event_policies: tuple[EventPolicy, ...]
    webhook_policies: tuple[WebhookPolicy, ...]
    forbidden_command_prefixes: tuple[str, ...]
    forbidden_payload_keys: tuple[str, ...]
    workflow_families: tuple[str, ...]
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))

    def command_policy_for(self, command_type: str) -> CommandPolicy | None:
        matches = [
            policy
            for policy in self.command_policies
            if command_type.startswith(policy.prefix)
        ]
        if not matches:
            return None
        return max(matches, key=lambda policy: len(policy.prefix))

    def webhook_policy_for(self, endpoint_key: str) -> WebhookPolicy | None:
        for policy in self.webhook_policies:
            if policy.endpoint_key == endpoint_key:
                return policy
        return None

    def allows_event(self, event_type: str) -> bool:
        return any(policy.event_type == event_type for policy in self.event_policies)


@dataclass(frozen=True, slots=True)
class CommandContext:
    tenant_id: str
    actor_id: str
    correlation_id: str
    causation_id: str
    idempotency_key: str
    capability_snapshot: Mapping[str, bool]


@dataclass(frozen=True, slots=True)
class CommandRequest:
    connector_id: str
    command_id: str
    command_type: str
    command_version: int
    payload: Mapping[str, Any]
    context: CommandContext


@dataclass(frozen=True, slots=True)
class CommandResult:
    outcome: CommandOutcome
    operation_id: str
    provider_reference: str | None = None
    safe_result: Mapping[str, Any] = field(default_factory=dict)
    retryable: bool = False
    error_code: str | None = None


@dataclass(frozen=True, slots=True)
class ConnectionTestResult:
    ok: bool
    code: str
    safe_details: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ConnectorHealth:
    status: str
    checked_at_epoch: int
    safe_details: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class WebhookRequest:
    headers: Mapping[str, str]
    body: bytes
    received_at_epoch: int


@dataclass(frozen=True, slots=True)
class VerifiedWebhook:
    connector_id: str
    endpoint_key: str
    event_id: str
    body_sha256: str
    timestamp_epoch: int
    replay_key: str
    body: bytes
    headers: Mapping[str, str]


@dataclass(frozen=True, slots=True)
class NormalizedWebhookEvent:
    event_id: str
    event_type: str
    tenant_id: str
    correlation_id: str
    causation_id: str
    occurred_at: str
    payload: Mapping[str, Any]
