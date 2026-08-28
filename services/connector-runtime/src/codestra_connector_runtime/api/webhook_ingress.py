"""Public signed-webhook ingress with durable acknowledgement semantics."""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import Request

from middleware.connector_sdk import parse_manifest

from .body_limits import read_bounded_body
from .config import RuntimeSettings
from .crypto import EncryptedBodyStore
from .problems import ProblemError
from .repository import ConnectorRepository

_EVENT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}$")
_LOG = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class EnvironmentSecretResolver:
    """Resolve reviewed aliases from mounted files first, then environment."""

    def resolve(self, alias: str) -> bytes:
        file_value = os.environ.get(alias + "_FILE")
        if file_value:
            path = Path(file_value)
            if not path.is_absolute():
                raise ProblemError(
                    status=503,
                    code="WEBHOOK_SECRET_UNAVAILABLE",
                    title="Webhook secret unavailable",
                    detail="The configured secret file path is invalid.",
                )
            value = path.read_bytes().strip()
        else:
            raw = os.environ.get(alias)
            if raw is None:
                raise ProblemError(
                    status=503,
                    code="WEBHOOK_SECRET_UNAVAILABLE",
                    title="Webhook secret unavailable",
                    detail="The webhook secret reference is unavailable.",
                )
            value = raw.encode("utf-8")
        if len(value) < 32:
            raise ProblemError(
                status=503,
                code="WEBHOOK_SECRET_UNAVAILABLE",
                title="Webhook secret unavailable",
                detail="The webhook secret does not satisfy runtime policy.",
            )
        return value


@dataclass(slots=True)
class WebhookIngressService:
    repository: ConnectorRepository
    settings: RuntimeSettings
    body_store: EncryptedBodyStore
    secrets: EnvironmentSecretResolver

    @staticmethod
    def _headers(request: Request) -> dict[str, str]:
        normalized: dict[str, str] = {}
        for key, value in request.headers.items():
            lowered = key.lower()
            if lowered in normalized:
                raise ProblemError(
                    status=400,
                    code="DUPLICATE_WEBHOOK_HEADER",
                    title="Duplicate webhook header",
                    detail="A security-sensitive webhook header was duplicated.",
                )
            normalized[lowered] = value
        return normalized

    @staticmethod
    def _signature(value: str) -> str:
        candidate = value.strip()
        candidate = candidate.removeprefix("v1=")
        if len(candidate) != 64:
            raise ProblemError(
                status=401,
                code="WEBHOOK_SIGNATURE_INVALID",
                title="Webhook authentication failed",
                detail="The webhook signature is invalid.",
            )
        try:
            bytes.fromhex(candidate)
        except ValueError as error:
            raise ProblemError(
                status=401,
                code="WEBHOOK_SIGNATURE_INVALID",
                title="Webhook authentication failed",
                detail="The webhook signature is invalid.",
            ) from error
        return candidate.lower()

    async def accept(
        self,
        request: Request,
        *,
        connector_id: str,
        endpoint_key: str,
        webhook_id: UUID,
    ) -> tuple[int, dict[str, object]]:
        if not self.settings.webhook_ingress_enabled:
            raise ProblemError(
                status=503,
                code="WEBHOOK_INGRESS_DISABLED",
                title="Webhook ingress disabled",
                detail="Webhook ingress is disabled by runtime policy.",
            )
        ingress = self.repository.resolve_ingress_webhook(
            connector_id=connector_id,
            endpoint_key=endpoint_key,
            webhook_id=webhook_id,
        )
        if ingress["webhook_state"] != "ACTIVE" or ingress["installation_state"] != "ACTIVE":
            raise ProblemError(
                status=404,
                code="WEBHOOK_NOT_FOUND",
                title="Webhook not found",
                detail="The webhook route is not active.",
            )
        manifest = parse_manifest(dict(ingress["manifest"]))
        policy = manifest.webhook_policy_for(endpoint_key)
        if policy is None:
            raise ProblemError(
                status=404,
                code="WEBHOOK_NOT_FOUND",
                title="Webhook not found",
                detail="The webhook endpoint is not declared by the connector.",
            )

        headers = self._headers(request)
        body = await read_bounded_body(
            request,
            maximum_bytes=policy.maximum_body_bytes,
            too_large_code="WEBHOOK_BODY_TOO_LARGE",
            title="Webhook body too large",
            detail="The webhook body exceeds the connector policy.",
        )
        try:
            signature = self._signature(headers[policy.signature_header.lower()])
            timestamp_text = headers[policy.timestamp_header.lower()]
            event_id = headers[policy.event_id_header.lower()].strip()
        except KeyError as error:
            raise ProblemError(
                status=401,
                code="WEBHOOK_HEADER_MISSING",
                title="Webhook authentication failed",
                detail="A required webhook authentication header is missing.",
            ) from error
        try:
            timestamp = int(timestamp_text)
        except ValueError as error:
            raise ProblemError(
                status=401,
                code="WEBHOOK_TIMESTAMP_INVALID",
                title="Webhook authentication failed",
                detail="The webhook timestamp is invalid.",
            ) from error
        now = int(time.time())
        if abs(now - timestamp) > policy.maximum_clock_skew_seconds:
            raise ProblemError(
                status=401,
                code="WEBHOOK_TIMESTAMP_EXPIRED",
                title="Webhook authentication failed",
                detail="The webhook timestamp is outside the accepted window.",
            )
        if _EVENT_ID.fullmatch(event_id) is None:
            raise ProblemError(
                status=400,
                code="WEBHOOK_EVENT_ID_INVALID",
                title="Webhook event ID invalid",
                detail="The provider event identifier is invalid.",
            )

        aliases = [str(ingress["secret_reference_current"])]
        previous = ingress.get("secret_reference_previous")
        previous_until = ingress.get("previous_secret_valid_until")
        if (
            previous
            and isinstance(previous_until, datetime)
            and previous_until > datetime.now(timezone.utc)
        ):
            aliases.append(str(previous))
        signed = str(timestamp).encode("ascii") + b"." + body
        authenticated = False
        for alias in aliases:
            secret = self.secrets.resolve(alias)
            expected = hmac.new(secret, signed, hashlib.sha256).hexdigest()
            authenticated = hmac.compare_digest(expected, signature) or authenticated
        if not authenticated:
            raise ProblemError(
                status=401,
                code="WEBHOOK_SIGNATURE_INVALID",
                title="Webhook authentication failed",
                detail="The webhook signature is invalid.",
            )

        tenant_id = str(ingress["tenant_id"])
        body_sha256 = hashlib.sha256(body).hexdigest()
        reference, created = self.body_store.persist_with_status(
            body,
            tenant_id=tenant_id,
            webhook_id=str(webhook_id),
            event_id=event_id,
        )
        correlation_id = UUID(
            str(getattr(request.state, "correlation_id", uuid4()))
        )
        try:
            duplicate, inbox_id = self.repository.persist_verified_webhook(
                ingress=ingress,
                event_id=event_id,
                body_sha256=body_sha256,
                encrypted_body_reference=reference,
                signature_version="codestra-hmac-sha256-v1",
                correlation_id=correlation_id,
                traceparent=request.headers.get("traceparent"),
            )
        except Exception:
            if created:
                try:
                    self.body_store.delete(reference)
                except OSError as cleanup_error:
                    _LOG.error(
                        "encrypted webhook body cleanup failed after database rejection",
                        extra={"error_type": type(cleanup_error).__name__},
                    )
            raise
        return 202, {
            "data": {
                "inbox_id": str(inbox_id),
                "status": "accepted",
                "duplicate": duplicate,
            },
            "meta": {
                "correlation_id": str(correlation_id),
                "api_version": "v1",
            },
        }
