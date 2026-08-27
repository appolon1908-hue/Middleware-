"""Webhook source verification, replay protection, and normalization."""

from __future__ import annotations

import hashlib
import hmac
import threading
import time
from collections.abc import Mapping
from typing import Any

from .errors import (
    ConnectorStateError,
    ReplayDetectedError,
    WebhookVerificationError,
)
from .interfaces import ReplayStore, SecretResolver
from .models import (
    ConnectorState,
    ReplayDecision,
    VerifiedWebhook,
    WebhookRequest,
)
from .registry import ConnectorRegistry


class MappingSecretResolver:
    """Test/development resolver. Production resolves from external secrets."""

    def __init__(self, values: Mapping[str, bytes]) -> None:
        self._values = dict(values)

    def resolve(self, reference: str) -> bytes:
        try:
            value = self._values[reference]
        except KeyError as error:
            raise WebhookVerificationError(
                f"secret reference is unavailable: {reference}"
            ) from error
        if not isinstance(value, bytes) or len(value) < 32:
            raise WebhookVerificationError(
                f"secret reference is invalid: {reference}"
            )
        return value


class InMemoryReplayStore:
    """Atomic TTL replay store for tests and local development only."""

    def __init__(self) -> None:
        self._claims: dict[str, tuple[str, int]] = {}
        self._lock = threading.Lock()

    def claim(
        self,
        event_key: str,
        body_sha256: str,
        ttl_seconds: int,
    ) -> ReplayDecision:
        now = int(time.time())
        with self._lock:
            expired = [
                existing
                for existing, (_, expires_at) in self._claims.items()
                if expires_at <= now
            ]
            for existing in expired:
                self._claims.pop(existing, None)
            prior = self._claims.get(event_key)
            if prior is not None:
                prior_digest, _ = prior
                if prior_digest == body_sha256:
                    return ReplayDecision.EXACT_REPLAY
                return ReplayDecision.SEMANTIC_CONFLICT
            self._claims[event_key] = (body_sha256, now + ttl_seconds)
            return ReplayDecision.NEW


def _case_insensitive_headers(
    headers: Mapping[str, str],
) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for key, value in headers.items():
        lowered = key.lower()
        if lowered in normalized:
            raise WebhookVerificationError(
                f"duplicate webhook header: {key}"
            )
        normalized[lowered] = str(value)
    return normalized


def _signature_hex(raw: str) -> str:
    value = raw.strip()
    if value.startswith("v1="):
        value = value[3:]
    if len(value) != 64:
        raise WebhookVerificationError("signature must be 32-byte SHA-256 hex")
    try:
        bytes.fromhex(value)
    except ValueError as error:
        raise WebhookVerificationError("signature is not hexadecimal") from error
    return value.lower()


class WebhookProcessor:
    def __init__(
        self,
        registry: ConnectorRegistry,
        secrets: SecretResolver,
        replay_store: ReplayStore,
    ) -> None:
        self._registry = registry
        self._secrets = secrets
        self._replay_store = replay_store

    def verify(
        self,
        connector_id: str,
        endpoint_key: str,
        request: WebhookRequest,
    ) -> VerifiedWebhook:
        record = self._registry.get(connector_id)
        if record.state is not ConnectorState.ACTIVE:
            raise ConnectorStateError(
                f"connector {connector_id} cannot accept webhooks in "
                f"{record.state.value}"
            )
        policy = record.manifest.webhook_policy_for(endpoint_key)
        if policy is None:
            raise WebhookVerificationError(
                f"unknown webhook endpoint: {connector_id}/{endpoint_key}"
            )
        if len(request.body) > policy.maximum_body_bytes:
            raise WebhookVerificationError("webhook body exceeds policy limit")

        headers = _case_insensitive_headers(request.headers)
        try:
            signature = _signature_hex(
                headers[policy.signature_header.lower()]
            )
            timestamp_raw = headers[policy.timestamp_header.lower()]
            event_id = headers[policy.event_id_header.lower()].strip()
        except KeyError as error:
            raise WebhookVerificationError(
                f"required webhook header is missing: {error.args[0]}"
            ) from error

        try:
            timestamp = int(timestamp_raw)
        except ValueError as error:
            raise WebhookVerificationError(
                "webhook timestamp must be Unix epoch seconds"
            ) from error
        if abs(request.received_at_epoch - timestamp) > (
            policy.maximum_clock_skew_seconds
        ):
            raise WebhookVerificationError("webhook timestamp is outside policy")
        if not event_id or len(event_id) > 256:
            raise WebhookVerificationError("webhook event ID is invalid")

        secret = self._secrets.resolve(policy.secret_reference)
        signed = str(timestamp).encode("ascii") + b"." + request.body
        expected = hmac.new(secret, signed, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, signature):
            raise WebhookVerificationError("webhook signature is invalid")

        body_digest = hashlib.sha256(request.body).hexdigest()
        replay_key = f"{connector_id}:{endpoint_key}:{event_id}"
        ttl_seconds = max(policy.maximum_clock_skew_seconds * 2, 600)
        decision = self._replay_store.claim(
            replay_key,
            body_digest,
            ttl_seconds,
        )
        if decision is ReplayDecision.EXACT_REPLAY:
            raise ReplayDetectedError("exact webhook replay detected")
        if decision is ReplayDecision.SEMANTIC_CONFLICT:
            raise WebhookVerificationError(
                "webhook event ID was reused with a different body"
            )

        return VerifiedWebhook(
            connector_id=connector_id,
            endpoint_key=endpoint_key,
            event_id=event_id,
            body_sha256=body_digest,
            timestamp_epoch=timestamp,
            replay_key=replay_key,
            body=request.body,
            headers=headers,
        )

    def process(
        self,
        connector_id: str,
        endpoint_key: str,
        request: WebhookRequest,
    ) -> Any:
        verified = self.verify(connector_id, endpoint_key, request)
        record = self._registry.get(connector_id)
        adapter = self._registry.adapter_factory(connector_id)(record.manifest)
        event = adapter.normalize_webhook(verified)
        if not record.manifest.allows_event(event.event_type):
            raise WebhookVerificationError(
                f"adapter emitted undeclared event type: {event.event_type}"
            )
        return event
