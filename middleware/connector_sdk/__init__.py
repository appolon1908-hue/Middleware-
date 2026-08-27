"""Codestra Connector SDK v1.

This package is intentionally framework-neutral. FastAPI, Django, worker, and
Temporal adapters can bind these services without giving connector manifests
the ability to load code or hold secret values.
"""

from .catalog import ConnectorCatalogService
from .errors import (
    CapabilityDisabledError,
    CommandNotAllowedError,
    ConnectorError,
    ConnectorNotFoundError,
    ConnectorStateError,
    ConnectorVersionConflictError,
    ManifestValidationError,
    ReadBackRequiredError,
    ReplayDetectedError,
    UnknownOutcomeError,
    WebhookVerificationError,
)
from .interfaces import (
    AdapterFactory,
    CapabilityProvider,
    ConnectorAdapter,
    ReplayStore,
    SecretResolver,
)
from .manifest import (
    canonical_manifest_json,
    load_manifest,
    manifest_digest,
    parse_manifest,
)
from .models import (
    CommandContext,
    CommandOutcome,
    CommandRequest,
    CommandResult,
    ConnectionTestResult,
    ConnectorCell,
    ConnectorHealth,
    ConnectorManifest,
    ConnectorState,
    NormalizedWebhookEvent,
    ReplayDecision,
    VerifiedWebhook,
    WebhookRequest,
)
from .registry import ConnectorRegistry, RegisteredConnector
from .runtime import ConnectorRuntime, StaticCapabilityProvider
from .webhooks import (
    InMemoryReplayStore,
    MappingSecretResolver,
    WebhookProcessor,
)

__all__ = [
    "AdapterFactory",
    "CapabilityDisabledError",
    "CapabilityProvider",
    "CommandContext",
    "CommandNotAllowedError",
    "CommandOutcome",
    "CommandRequest",
    "CommandResult",
    "ConnectionTestResult",
    "ConnectorAdapter",
    "ConnectorCatalogService",
    "ConnectorCell",
    "ConnectorError",
    "ConnectorHealth",
    "ConnectorManifest",
    "ConnectorNotFoundError",
    "ConnectorRegistry",
    "ConnectorRuntime",
    "ConnectorState",
    "ConnectorStateError",
    "ConnectorVersionConflictError",
    "InMemoryReplayStore",
    "ManifestValidationError",
    "MappingSecretResolver",
    "NormalizedWebhookEvent",
    "ReadBackRequiredError",
    "RegisteredConnector",
    "ReplayDecision",
    "ReplayDetectedError",
    "ReplayStore",
    "SecretResolver",
    "StaticCapabilityProvider",
    "UnknownOutcomeError",
    "VerifiedWebhook",
    "WebhookProcessor",
    "WebhookRequest",
    "WebhookVerificationError",
    "canonical_manifest_json",
    "load_manifest",
    "manifest_digest",
    "parse_manifest",
]
