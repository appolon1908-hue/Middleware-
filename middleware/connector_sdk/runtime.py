"""Connector command runtime with capability and read-back enforcement."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .errors import (
    CapabilityDisabledError,
    CommandNotAllowedError,
    ConnectorStateError,
    ReadBackRequiredError,
)
from .interfaces import CapabilityProvider
from .models import (
    CommandOutcome,
    CommandRequest,
    CommandResult,
    ConnectorState,
)
from .registry import ConnectorRegistry


def _forbidden_payload_paths(
    value: Any,
    forbidden: set[str],
    path: str = "$",
) -> tuple[str, ...]:
    matches: list[str] = []
    if isinstance(value, Mapping):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if str(key).lower() in forbidden:
                matches.append(child_path)
            matches.extend(_forbidden_payload_paths(child, forbidden, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            matches.extend(
                _forbidden_payload_paths(child, forbidden, f"{path}[{index}]")
            )
    return tuple(matches)


class StaticCapabilityProvider:
    """Small test/development provider. Production uses Middleware persistence."""

    def __init__(self, values: Mapping[tuple[str, str], bool]) -> None:
        self._values = dict(values)

    def is_enabled(self, tenant_id: str, capability: str) -> bool:
        return bool(self._values.get((tenant_id, capability), False))


class ConnectorRuntime:
    def __init__(
        self,
        registry: ConnectorRegistry,
        capabilities: CapabilityProvider,
    ) -> None:
        self._registry = registry
        self._capabilities = capabilities

    def execute(self, request: CommandRequest) -> CommandResult:
        if not request.context.tenant_id:
            raise CommandNotAllowedError("tenant_id is required")
        if len(request.context.idempotency_key) < 8:
            raise CommandNotAllowedError("idempotency_key is too short")
        if request.command_version < 1:
            raise CommandNotAllowedError("command_version must be positive")

        record = self._registry.get(request.connector_id)
        forbidden_paths = _forbidden_payload_paths(
            request.payload,
            {key.lower() for key in record.manifest.forbidden_payload_keys},
        )
        if forbidden_paths:
            raise CommandNotAllowedError(
                "payload contains forbidden secret fields: "
                + ", ".join(forbidden_paths)
            )
        if record.state is not ConnectorState.ACTIVE:
            raise ConnectorStateError(
                f"connector {request.connector_id} is {record.state.value}"
            )

        resolved, policy = self._registry.resolve_command(request.command_type)
        if resolved.manifest.connector_id != request.connector_id:
            raise CommandNotAllowedError(
                f"{request.command_type} is owned by "
                f"{resolved.manifest.connector_id}, not {request.connector_id}"
            )

        for forbidden in record.manifest.forbidden_command_prefixes:
            if request.command_type.startswith(forbidden):
                raise CommandNotAllowedError(request.command_type)

        capability = policy.required_capability
        if capability != "NONE":
            snapshot_value = request.context.capability_snapshot.get(capability)
            authoritative_value = self._capabilities.is_enabled(
                request.context.tenant_id,
                capability,
            )
            if snapshot_value is not True or authoritative_value is not True:
                raise CapabilityDisabledError(capability)

        adapter = self._registry.adapter_factory(request.connector_id)(
            record.manifest
        )
        result = adapter.execute_command(request)

        if result.outcome is CommandOutcome.UNKNOWN:
            reconciled = adapter.reconcile_unknown(request, result)
            if reconciled.outcome is CommandOutcome.UNKNOWN:
                return reconciled
            result = reconciled

        if policy.readback_required and result.outcome in {
            CommandOutcome.ACCEPTED,
            CommandOutcome.SUBMITTED,
            CommandOutcome.COMPLETED,
        }:
            result = adapter.read_back(request, result)
            if result.outcome is CommandOutcome.UNKNOWN:
                raise ReadBackRequiredError(
                    f"authoritative read-back remains unknown for "
                    f"{request.command_id}"
                )

        return result

    def test_connection(
        self,
        connector_id: str,
        configuration: Mapping[str, Any],
    ) -> Any:
        record = self._registry.get(connector_id)
        adapter = self._registry.adapter_factory(connector_id)(record.manifest)
        errors = adapter.validate_configuration(record.manifest, configuration)
        if errors:
            return {"ok": False, "code": "CONFIGURATION_INVALID", "errors": errors}
        return adapter.test_connection(record.manifest, configuration)

    def health(self, connector_id: str) -> Any:
        record = self._registry.get(connector_id)
        adapter = self._registry.adapter_factory(connector_id)(record.manifest)
        return adapter.health()
