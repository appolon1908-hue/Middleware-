"""Shared fail-closed primitives for Middleware-owned provider adapters.

Provider adapters are intentionally transport-agnostic. Production code must inject a
reviewed transport and a durable idempotency store; this module never opens a network
connection by itself and never falls back to process-local state in production.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from typing import Any, Mapping, Protocol


@dataclass(frozen=True)
class EnvRef:
    """Reference to a runtime environment variable without embedding its value."""

    name: str


@dataclass(frozen=True)
class ProviderRequest:
    method: str
    path: str
    body: Mapping[str, Any] | None = None
    headers: Mapping[str, Any] | None = None
    query: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class ProviderResponse:
    provider_ref: str | None
    status: str
    data: dict[str, Any]


@dataclass(frozen=True)
class AdapterResult:
    success: bool
    provider_ref: str | None
    data: dict[str, Any]
    idempotent_replay: bool = False
    error_code: str | None = None
    error_message: str | None = None


@dataclass(frozen=True)
class WebhookResult:
    status: str  # processed | ignored | failed
    event_type: str
    provider_event_id: str
    error: str | None = None


@dataclass(frozen=True)
class ExecutionRecord:
    payload_sha256: str
    status: str
    result: AdapterResult | None = None
    error: str | None = None


class ProviderError(RuntimeError):
    def __init__(self, message: str, code: str = "provider_error") -> None:
        self.code = code
        super().__init__(message)


class IdempotentReplayError(ProviderError):
    """Raised when an idempotency key is reused with different command content."""

    def __init__(self, message: str = "idempotency key reused with different content") -> None:
        super().__init__(message, code="idempotency_conflict")


class ProviderTransport(Protocol):
    def execute(self, adapter: str, request: ProviderRequest) -> ProviderResponse: ...

    def read_back(
        self,
        adapter: str,
        *,
        provider_ref: str,
        command_type: str,
        payload: Mapping[str, Any],
    ) -> ProviderResponse: ...


class IdempotencyStore(Protocol):
    def get_execution(self, adapter: str, idempotency_key: str) -> ExecutionRecord | None: ...

    def begin_execution(
        self,
        adapter: str,
        idempotency_key: str,
        payload_sha256: str,
        *,
        correlation_id: str,
        request_id: str,
        command_type: str,
    ) -> None: ...

    def complete_execution(
        self,
        adapter: str,
        idempotency_key: str,
        payload_sha256: str,
        result: AdapterResult,
    ) -> None: ...

    def fail_execution(
        self,
        adapter: str,
        idempotency_key: str,
        payload_sha256: str,
        error: str,
    ) -> None: ...

    def webhook_seen(self, adapter: str, provider_event_id: str) -> bool: ...

    def record_webhook(self, adapter: str, provider_event_id: str) -> None: ...


class MemoryIdempotencyStore:
    """Deterministic test double only; production must inject durable persistence."""

    def __init__(self) -> None:
        self.executions: dict[tuple[str, str], ExecutionRecord] = {}
        self.webhooks: set[tuple[str, str]] = set()

    def get_execution(self, adapter: str, idempotency_key: str) -> ExecutionRecord | None:
        return self.executions.get((adapter, idempotency_key))

    def begin_execution(
        self,
        adapter: str,
        idempotency_key: str,
        payload_sha256: str,
        *,
        correlation_id: str,
        request_id: str,
        command_type: str,
    ) -> None:
        del correlation_id, request_id, command_type
        self.executions[(adapter, idempotency_key)] = ExecutionRecord(
            payload_sha256=payload_sha256,
            status="processing",
        )

    def complete_execution(
        self,
        adapter: str,
        idempotency_key: str,
        payload_sha256: str,
        result: AdapterResult,
    ) -> None:
        self.executions[(adapter, idempotency_key)] = ExecutionRecord(
            payload_sha256=payload_sha256,
            status="succeeded",
            result=result,
        )

    def fail_execution(
        self,
        adapter: str,
        idempotency_key: str,
        payload_sha256: str,
        error: str,
    ) -> None:
        self.executions[(adapter, idempotency_key)] = ExecutionRecord(
            payload_sha256=payload_sha256,
            status="failed",
            error=error,
        )

    def webhook_seen(self, adapter: str, provider_event_id: str) -> bool:
        return (adapter, provider_event_id) in self.webhooks

    def record_webhook(self, adapter: str, provider_event_id: str) -> None:
        self.webhooks.add((adapter, provider_event_id))


def _payload_digest(command_type: str, payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        {"command_type": command_type, "payload": payload},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def require_nonempty(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProviderError(f"{name} is required", code="invalid_command")
    return value.strip()


class BaseAdapter:
    ADAPTER_NAME = "base"
    COMMANDS: frozenset[str] = frozenset()
    WEBHOOK_EVENTS: frozenset[str] = frozenset()
    CAPABILITIES: Mapping[str, bool] = {}

    def __init__(self, *, store: IdempotencyStore, transport: ProviderTransport) -> None:
        self.store = store
        self.transport = transport

    def execute_command(
        self,
        *,
        command_type: str,
        payload: dict[str, Any],
        idempotency_key: str,
        correlation_id: str,
        request_id: str,
    ) -> AdapterResult:
        command_type = require_nonempty(command_type, "command_type")
        idempotency_key = require_nonempty(idempotency_key, "idempotency_key")
        correlation_id = require_nonempty(correlation_id, "correlation_id")
        request_id = require_nonempty(request_id, "request_id")
        if command_type not in self.COMMANDS:
            raise ProviderError(
                f"unsupported command for {self.ADAPTER_NAME}: {command_type}",
                code="unsupported_command",
            )
        if not isinstance(payload, dict):
            raise ProviderError("payload must be an object", code="invalid_command")

        self._validate(command_type, payload)
        digest = _payload_digest(command_type, payload)
        existing = self.store.get_execution(self.ADAPTER_NAME, idempotency_key)
        if existing is not None:
            if existing.payload_sha256 != digest:
                raise IdempotentReplayError()
            if existing.status == "succeeded" and existing.result is not None:
                return replace(existing.result, idempotent_replay=True)
            if existing.status == "processing":
                raise ProviderError(
                    "command with this idempotency key is already processing",
                    code="command_in_progress",
                )

        self.store.begin_execution(
            self.ADAPTER_NAME,
            idempotency_key,
            digest,
            correlation_id=correlation_id,
            request_id=request_id,
            command_type=command_type,
        )
        try:
            request = self._build_request(
                command_type=command_type,
                payload=payload,
                idempotency_key=idempotency_key,
                correlation_id=correlation_id,
                request_id=request_id,
            )
            response = self.transport.execute(self.ADAPTER_NAME, request)
            provider_ref = require_nonempty(response.provider_ref or "", "provider_ref")
            readback = self.transport.read_back(
                self.ADAPTER_NAME,
                provider_ref=provider_ref,
                command_type=command_type,
                payload=payload,
            )
            if not self._readback_matches(command_type, payload, response, readback):
                raise ProviderError(
                    f"{self.ADAPTER_NAME} read-back did not verify the requested write",
                    code="readback_mismatch",
                )
            result = AdapterResult(
                success=True,
                provider_ref=provider_ref,
                data={"write": response.data, "readback": readback.data, "status": readback.status},
            )
            self.store.complete_execution(self.ADAPTER_NAME, idempotency_key, digest, result)
            return result
        except ProviderError as exc:
            self.store.fail_execution(self.ADAPTER_NAME, idempotency_key, digest, str(exc))
            raise
        except Exception as exc:
            self.store.fail_execution(self.ADAPTER_NAME, idempotency_key, digest, str(exc))
            raise ProviderError(str(exc), code="provider_failure") from exc

    def handle_webhook(
        self,
        *,
        event_type: str,
        payload: dict[str, Any],
        provider_event_id: str,
    ) -> WebhookResult:
        event_type = require_nonempty(event_type, "event_type")
        provider_event_id = require_nonempty(provider_event_id, "provider_event_id")
        if self.store.webhook_seen(self.ADAPTER_NAME, provider_event_id):
            return WebhookResult("ignored", event_type, provider_event_id)
        self.store.record_webhook(self.ADAPTER_NAME, provider_event_id)
        if event_type not in self.WEBHOOK_EVENTS:
            return WebhookResult("ignored", event_type, provider_event_id)
        try:
            self._process_webhook(event_type, payload)
        except Exception as exc:
            return WebhookResult("failed", event_type, provider_event_id, str(exc))
        return WebhookResult("processed", event_type, provider_event_id)

    def verify_capability(self, capability: str) -> bool:
        return self.CAPABILITIES.get(capability, False) is True

    def _validate(self, command_type: str, payload: Mapping[str, Any]) -> None:
        del command_type, payload

    def _process_webhook(self, event_type: str, payload: Mapping[str, Any]) -> None:
        del event_type
        if not isinstance(payload, Mapping):
            raise ProviderError("webhook payload must be an object", code="invalid_webhook")

    def _build_request(
        self,
        *,
        command_type: str,
        payload: Mapping[str, Any],
        idempotency_key: str,
        correlation_id: str,
        request_id: str,
    ) -> ProviderRequest:
        raise NotImplementedError

    def _readback_matches(
        self,
        command_type: str,
        payload: Mapping[str, Any],
        write: ProviderResponse,
        readback: ProviderResponse,
    ) -> bool:
        raise NotImplementedError
