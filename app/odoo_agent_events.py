"""Contract validation and durable persistence for Odoo agent events."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.contracts import ROUTE_BY_PATH
from app.models import EventEnvelope, IngressResult
from app.storage import (
    NATS_JETSTREAM_DESTINATION,
    ZERO_LEDGER_HASH,
    canonical_payload_sha256,
    event_ledger_hash,
)


ODOO_EVENTS_PATH = "/api/v1/odoo/events"
ODOO_EVENT_ROUTE = ROUTE_BY_PATH[ODOO_EVENTS_PATH]
ODOO_EVENT_TYPES = ODOO_EVENT_ROUTE.event_types
ODOO_AGENT_EVENT_TYPES = frozenset(
    {
        "codestra.odoo.agent.provisioning_requested",
        "codestra.odoo.agent.activation_email_requested",
    }
)

PROVISIONING_PAYLOAD_TYPE = "agent.provisioning.requested.v1"
ACTIVATION_EMAIL_PAYLOAD_TYPE = "agent.activation-email.requested.v1"
FORBIDDEN_PAYLOAD_KEYS = frozenset(
    {
        "password",
        "temporary_password",
        "token",
        "secret",
        "private_key",
        "recovery_code",
        "activation_link",
        "action_link",
        "reset_link",
    }
)


class OdooAgentEventValidationError(ValueError):
    """Raised when an Odoo agent event violates its specialized payload contract."""


class OdooAgentEventConflict(RuntimeError):
    """Raised when an event or idempotency identity is reused with new content."""


class OdooAgentEventPersistenceError(RuntimeError):
    """Raised when durable acceptance cannot be committed."""


def _normalized_key(value: object) -> str:
    text_value = re.sub(r"(?<!^)([A-Z])", r"_\1", str(value))
    return text_value.lower().replace("-", "_")


def _nested_keys(value: object) -> list[str]:
    if isinstance(value, Mapping):
        keys: list[str] = []
        for key, nested in value.items():
            keys.append(str(key))
            keys.extend(_nested_keys(nested))
        return keys
    if isinstance(value, list):
        keys: list[str] = []
        for nested in value:
            keys.extend(_nested_keys(nested))
        return keys
    return []


def _require_dict(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise OdooAgentEventValidationError(f"{label} must be an object")
    return value


def _require_string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise OdooAgentEventValidationError(f"{label} must be a non-empty string")
    return value


def _require_string_list(value: object, label: str) -> list[str]:
    if not isinstance(value, list) or not value or not all(
        isinstance(item, str) and item.strip() for item in value
    ):
        raise OdooAgentEventValidationError(
            f"{label} must be a non-empty string array"
        )
    return value


def _require_control_values(
    controls: dict[str, Any],
    expected: Mapping[str, bool],
) -> None:
    for name, value in expected.items():
        if controls.get(name) is not value:
            raise OdooAgentEventValidationError(
                f"controls.{name} must be {str(value).lower()}"
            )


def _validate_context(payload: dict[str, Any]) -> None:
    _require_string(payload.get("onboarding_uuid"), "onboarding_uuid")
    _require_string(payload.get("login_identifier"), "login_identifier")


def _validate_credential_free_https_url(value: object) -> None:
    url = _require_string(value, "login.url")
    try:
        parsed = urlsplit(url)
        has_credentials = bool(parsed.username or parsed.password)
        hostname = parsed.hostname
    except ValueError as exc:
        raise OdooAgentEventValidationError("login.url is malformed") from exc
    if (
        parsed.scheme != "https"
        or not hostname
        or has_credentials
        or parsed.query
        or parsed.fragment
    ):
        raise OdooAgentEventValidationError(
            "login.url must be credential-free HTTPS without a query or fragment"
        )


def _validate_provisioning_payload(payload: dict[str, Any]) -> None:
    if payload.get("schema_version") != "1.0":
        raise OdooAgentEventValidationError(
            "provisioning payload schema_version must be 1.0"
        )
    if payload.get("event_type") != PROVISIONING_PAYLOAD_TYPE:
        raise OdooAgentEventValidationError(
            "provisioning payload event_type is not canonical"
        )
    _validate_context(payload)
    _require_string(payload.get("recipient_email"), "recipient_email")
    targets = _require_string_list(payload.get("targets"), "targets")
    if len(targets) > 32:
        raise OdooAgentEventValidationError("targets may contain at most 32 entries")
    telephony = _require_dict(
        payload.get("telephony_assignment"),
        "telephony_assignment",
    )
    if telephony.get("webrtc_max_devices") != 1:
        raise OdooAgentEventValidationError(
            "telephony_assignment.webrtc_max_devices must be 1"
        )
    controls = _require_dict(payload.get("controls"), "controls")
    _require_control_values(
        controls,
        {
            "create_disabled": True,
            "activate_immediately": False,
            "send_activation_email": False,
            "plaintext_password_allowed": False,
            "browser_campaign_selection_allowed": False,
            "change_agent_campaign": False,
            "production_dialing": False,
            "live_call_control": False,
            "webrtc_credential_issuance": False,
        },
    )


def _validate_activation_payload(payload: dict[str, Any]) -> None:
    if payload.get("schema_version") != "1.0":
        raise OdooAgentEventValidationError(
            "activation payload schema_version must be 1.0"
        )
    if payload.get("event_type") != ACTIVATION_EMAIL_PAYLOAD_TYPE:
        raise OdooAgentEventValidationError(
            "activation payload event_type is not canonical"
        )
    _validate_context(payload)
    delivery = _require_dict(payload.get("delivery"), "delivery")
    if delivery.get("channel") != "email":
        raise OdooAgentEventValidationError("delivery.channel must be email")
    if delivery.get("provider") != "klyrow":
        raise OdooAgentEventValidationError("delivery.provider must be klyrow")
    if delivery.get("mode") != "keycloak_execute_actions_email":
        raise OdooAgentEventValidationError(
            "delivery.mode is not the Keycloak action-email mode"
        )
    if delivery.get("template_key") != "agent-welcome-v1":
        raise OdooAgentEventValidationError(
            "delivery.template_key is not agent-welcome-v1"
        )
    _require_string(delivery.get("recipient"), "delivery.recipient")
    login = _require_dict(payload.get("login"), "login")
    _require_string(login.get("identifier"), "login.identifier")
    _validate_credential_free_https_url(login.get("url"))
    actions = _require_string_list(
        login.get("required_actions"),
        "login.required_actions",
    )
    if actions != ["UPDATE_PASSWORD", "CONFIGURE_TOTP"]:
        raise OdooAgentEventValidationError(
            "login.required_actions must be UPDATE_PASSWORD then CONFIGURE_TOTP"
        )
    ttl = login.get("expires_in_minutes")
    if isinstance(ttl, bool) or not isinstance(ttl, int) or not 5 <= ttl <= 1440:
        raise OdooAgentEventValidationError(
            "login.expires_in_minutes must be an integer from 5 to 1440"
        )
    controls = _require_dict(payload.get("controls"), "controls")
    _require_control_values(
        controls,
        {
            "one_time_action_required": True,
            "plaintext_password_allowed": False,
            "link_persistence_allowed": False,
            "activate_immediately": False,
            "production_dialing": False,
        },
    )


def validate_odoo_agent_event(envelope: EventEnvelope) -> None:
    """Validate the specialized payload for the two agent event types."""
    if envelope.event_type not in ODOO_AGENT_EVENT_TYPES:
        return
    leaked = sorted(
        {
            _normalized_key(key)
            for key in _nested_keys(envelope.payload)
            if _normalized_key(key) in FORBIDDEN_PAYLOAD_KEYS
        }
    )
    if leaked:
        raise OdooAgentEventValidationError(
            "agent event payload contains forbidden fields: " + ", ".join(leaked)
        )
    if envelope.event_type == "codestra.odoo.agent.provisioning_requested":
        _validate_provisioning_payload(envelope.payload)
    else:
        _validate_activation_payload(envelope.payload)


async def persist_odoo_agent_event(
    session: AsyncSession,
    envelope: EventEnvelope,
    *,
    body_sha256: str,
    source_client_id: str = ODOO_EVENT_ROUTE.producer_client_id,
) -> IngressResult:
    """Commit inbox, immutable ledger, and publication intent atomically."""
    if envelope.source != source_client_id:
        raise OdooAgentEventValidationError(
            "event source does not match the Odoo route"
        )
    if envelope.event_type not in ODOO_EVENT_TYPES:
        raise OdooAgentEventValidationError(
            "event type is not allowed for the Odoo route"
        )

    payload = envelope.model_dump(mode="json")
    semantic_sha256 = canonical_payload_sha256(payload)
    payload_json = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    now = datetime.now(timezone.utc)
    try:
        inserted = (
            await session.execute(
                text(
                    """
                    INSERT INTO middleware_inbox (
                        event_id, tenant_id, source_client_id, event_type,
                        body_sha256, semantic_sha256, idempotency_key, correlation_id,
                        payload, received_at, status
                    ) VALUES (
                        :event_id, :tenant_id, :source_client_id, :event_type,
                        :body_sha256, :semantic_sha256, :idempotency_key, :correlation_id,
                        CAST(:payload AS jsonb), :received_at, 'accepted'
                    )
                    ON CONFLICT DO NOTHING
                    RETURNING event_id
                    """
                ),
                {
                    "event_id": envelope.event_id,
                    "tenant_id": envelope.tenant_id,
                    "source_client_id": source_client_id,
                    "event_type": envelope.event_type,
                    "body_sha256": body_sha256,
                    "semantic_sha256": semantic_sha256,
                    "idempotency_key": envelope.idempotency_key,
                    "correlation_id": envelope.correlation_id,
                    "payload": payload_json,
                    "received_at": now,
                },
            )
        ).scalar_one_or_none()
        if inserted is not None:
            await session.execute(
                text(
                    "SELECT pg_advisory_xact_lock(hashtextextended(:tenant_id, 0))"
                ),
                {"tenant_id": envelope.tenant_id},
            )
            previous = (
                await session.execute(
                    text(
                        """
                        SELECT tenant_sequence, entry_hash
                        FROM middleware_event_ledger
                        WHERE tenant_id = :tenant_id
                        ORDER BY tenant_sequence DESC
                        LIMIT 1
                        """
                    ),
                    {"tenant_id": envelope.tenant_id},
                )
            ).mappings().first()
            tenant_sequence = int(previous["tenant_sequence"]) + 1 if previous else 1
            previous_entry_hash = (
                str(previous["entry_hash"]) if previous else ZERO_LEDGER_HASH
            )
            entry_hash = event_ledger_hash(
                tenant_id=envelope.tenant_id,
                tenant_sequence=tenant_sequence,
                event_id=envelope.event_id,
                semantic_sha256=semantic_sha256,
                previous_entry_hash=previous_entry_hash,
            )
            await session.execute(
                text(
                    """
                    INSERT INTO middleware_event_ledger (
                        tenant_id, tenant_sequence, event_id, event_type,
                        event_version, source_client_id, correlation_id,
                        causation_id, idempotency_key, semantic_sha256,
                        previous_entry_hash, entry_hash, payload
                    ) VALUES (
                        :tenant_id, :tenant_sequence, :event_id, :event_type,
                        :event_version, :source_client_id, :correlation_id,
                        :causation_id, :idempotency_key, :semantic_sha256,
                        :previous_entry_hash, :entry_hash, CAST(:payload AS jsonb)
                    )
                    """
                ),
                {
                    "tenant_id": envelope.tenant_id,
                    "tenant_sequence": tenant_sequence,
                    "event_id": envelope.event_id,
                    "event_type": envelope.event_type,
                    "event_version": envelope.event_version,
                    "source_client_id": source_client_id,
                    "correlation_id": envelope.correlation_id,
                    "causation_id": envelope.causation_id,
                    "idempotency_key": envelope.idempotency_key,
                    "semantic_sha256": semantic_sha256,
                    "previous_entry_hash": previous_entry_hash,
                    "entry_hash": entry_hash,
                    "payload": payload_json,
                },
            )
            await session.execute(
                text(
                    """
                    INSERT INTO middleware_outbox (
                        tenant_id, destination, event_type, payload, idempotency_key
                    ) VALUES (
                        :tenant_id, :destination, :event_type,
                        CAST(:payload AS jsonb), :idempotency_key
                    )
                    """
                ),
                {
                    "tenant_id": envelope.tenant_id,
                    "destination": NATS_JETSTREAM_DESTINATION,
                    "event_type": envelope.event_type,
                    "payload": payload_json,
                    "idempotency_key": envelope.idempotency_key,
                },
            )
            await session.commit()
            return IngressResult(
                event_id=envelope.event_id,
                tenant_id=envelope.tenant_id,
                status="accepted",
                duplicate=False,
                correlation_id=envelope.correlation_id,
            )

        existing_rows = (
            await session.execute(
                text(
                    """
                    SELECT event_id, tenant_id, idempotency_key,
                           semantic_sha256, correlation_id
                    FROM middleware_inbox
                    WHERE (tenant_id = :tenant_id AND event_id = :event_id)
                       OR (tenant_id = :tenant_id AND idempotency_key = :idempotency_key)
                    ORDER BY received_at ASC
                    """
                ),
                {
                    "tenant_id": envelope.tenant_id,
                    "event_id": envelope.event_id,
                    "idempotency_key": envelope.idempotency_key,
                },
            )
        ).mappings().all()
        if not existing_rows:
            raise OdooAgentEventPersistenceError(
                "inbox conflict could not be reconciled"
            )
        identities = {
            (row["event_id"], row["idempotency_key"]) for row in existing_rows
        }
        if len(identities) > 1:
            raise OdooAgentEventConflict(
                "event and idempotency identities refer to different accepted events"
            )
        existing = existing_rows[0]
        if existing["semantic_sha256"] != semantic_sha256:
            raise OdooAgentEventConflict(
                "event/idempotency identity was reused with a different semantic payload"
            )
        await session.commit()
        return IngressResult(
            event_id=existing["event_id"],
            tenant_id=existing["tenant_id"],
            status="duplicate",
            duplicate=True,
            correlation_id=existing["correlation_id"],
        )
    except OdooAgentEventConflict:
        await session.rollback()
        raise
    except OdooAgentEventPersistenceError:
        await session.rollback()
        raise
    except SQLAlchemyError as exc:
        await session.rollback()
        raise OdooAgentEventPersistenceError(
            "durable event acceptance is unavailable"
        ) from exc
