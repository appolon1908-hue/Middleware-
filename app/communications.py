from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from .commands import CommandEnvelope, CommandService
from .control_plane_auth import authorize_command, caller_for_authorization
from .security import AuthorizationError, RequestValidationError, authorize_tenant


CommunicationChannel = Literal["email", "sms", "voice"]
MessageStatus = Literal[
    "accepted",
    "queued",
    "dispatched",
    "delivered",
    "failed",
    "cancelled",
    "suppressed",
    "expired",
    "indeterminate",
]


class CommunicationsError(RuntimeError):
    status_code = 400
    code = "communications_invalid"
    retryable = False


class CommunicationsConflict(CommunicationsError):
    status_code = 409
    code = "communications_conflict"


class CommunicationsNotFound(CommunicationsError):
    status_code = 404
    code = "communications_not_found"


class MessageContent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject: str | None = Field(default=None, max_length=998)
    text: str | None = Field(default=None, max_length=200_000)
    html: str | None = Field(default=None, max_length=200_000)
    templateId: uuid.UUID | None = None
    templateVersion: int | None = Field(default=None, ge=1)
    variables: dict[str, Any] | None = None
    mediaUrls: list[str] | None = Field(default=None, max_length=20)

    @model_validator(mode="after")
    def require_content(self) -> "MessageContent":
        if not any((self.text, self.html, self.templateId)):
            raise ValueError("email content requires text, html, or templateId")
        return self


class CreateMessageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    channel: CommunicationChannel
    from_: EmailStr | None = Field(default=None, alias="from")
    to: list[EmailStr] = Field(min_length=1, max_length=1000)
    senderIdentityId: uuid.UUID | None = None
    domainId: uuid.UUID | None = None
    content: MessageContent
    scheduledAt: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("scheduledAt")
    @classmethod
    def require_scheduled_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("scheduledAt must include timezone")
        return value

    @model_validator(mode="after")
    def email_only_for_step3(self) -> "CreateMessageRequest":
        if self.channel != "email":
            raise ValueError("Step 3 implements only channel=email")
        if self.from_ is None and self.senderIdentityId is None:
            raise ValueError("email requires from or senderIdentityId")
        return self


class CommunicationMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    messageId: uuid.UUID
    tenantId: str
    channel: CommunicationChannel
    direction: Literal["outbound", "inbound"]
    status: MessageStatus
    correlationId: str
    idempotencyKey: str
    operationId: uuid.UUID | None = None
    provider: str | None = None
    providerReference: str | None = None
    failureCode: str | None = None
    failureMessage: str | None = None
    createdAt: datetime
    acceptedAt: datetime | None = None
    dispatchedAt: datetime | None = None
    completedAt: datetime | None = None
    updatedAt: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


class MessageEvent(BaseModel):
    eventId: uuid.UUID
    messageId: uuid.UUID
    type: str
    status: MessageStatus
    occurredAt: datetime
    provider: str | None = None
    providerReference: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class Paged(BaseModel):
    items: list[Any]
    nextCursor: str | None = None


def _canonical_digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def _provider_status_to_canonical(status: str) -> MessageStatus:
    normalized = status.lower()
    if normalized in {"delivered", "sent"}:
        return "delivered"
    if normalized in {"queued", "created"}:
        return "queued"
    if normalized in {"processing", "submitted", "provider_accepted"}:
        return "dispatched"
    if normalized in {"suppressed"}:
        return "suppressed"
    if normalized in {"cancelled", "canceled"}:
        return "cancelled"
    if normalized in {"expired"}:
        return "expired"
    if normalized in {"deferred", "unknown", "indeterminate"}:
        return "indeterminate"
    return "failed"


def _provider_event_uuid(tenant_id: str, event_id: str) -> uuid.UUID:
    try:
        return uuid.UUID(event_id)
    except ValueError:
        return uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"codestra:communications:{tenant_id}:{event_id}",
        )


def _command_state_to_canonical(state: str) -> MessageStatus | None:
    if state in {"persisted", "queued"}:
        return "queued"
    if state in {"dispatching", "accepted", "readback_pending", "completed"}:
        return "dispatched"
    if state == "reconciliation_required":
        return "indeterminate"
    if state in {"failed", "dead_lettered"}:
        return "failed"
    return None


@dataclass
class MemoryCommunicationsStore:
    messages: dict[tuple[str, uuid.UUID], CommunicationMessage] = field(default_factory=dict)
    events: dict[tuple[str, uuid.UUID], list[MessageEvent]] = field(default_factory=dict)
    idempotency: dict[tuple[str, str, str], tuple[str, uuid.UUID]] = field(default_factory=dict)
    provider_event_digests: dict[tuple[str, str], str] = field(default_factory=dict)
    suppressions: set[tuple[str, str]] = field(default_factory=set)
    denied_consent: set[tuple[str, str]] = field(default_factory=set)
    verified_senders: set[tuple[str, str]] = field(default_factory=set)
    verified_domains: set[tuple[str, str]] = field(default_factory=set)

    async def ready(self) -> bool:
        return True

    def add_event(
        self,
        tenant_id: str,
        message_id: uuid.UUID,
        *,
        event_type: str,
        status: MessageStatus,
        provider: str | None = None,
        provider_reference: str | None = None,
        metadata: dict[str, Any] | None = None,
        event_id: uuid.UUID | None = None,
    ) -> MessageEvent:
        event = MessageEvent(
            eventId=event_id or uuid.uuid4(),
            messageId=message_id,
            type=event_type,
            status=status,
            occurredAt=datetime.now(UTC),
            provider=provider,
            providerReference=provider_reference,
            metadata=metadata or {},
        )
        key = (tenant_id, message_id)
        timeline = self.events.setdefault(key, [])
        if not any(item.eventId == event.eventId for item in timeline):
            timeline.append(event)
        return event


class KlyrowEmailAdapter(Protocol):
    async def submit(self, message: CommunicationMessage, request: CreateMessageRequest) -> dict[str, Any]:
        ...

    async def health(self, tenant_id: str) -> dict[str, Any]:
        ...

    async def reputation(self, tenant_id: str) -> dict[str, Any]:
        ...


class DisabledKlyrowEmailAdapter:
    async def submit(self, message: CommunicationMessage, request: CreateMessageRequest) -> dict[str, Any]:
        raise RuntimeError("email_delivery_kill_switch_disabled")

    async def health(self, tenant_id: str) -> dict[str, Any]:
        return {
            "status": "disabled",
            "checkedAt": datetime.now(UTC).isoformat(),
            "providers": [
                {
                    "provider": "klyrow",
                    "channel": "email",
                    "status": "disabled",
                    "reason": "EMAIL_DELIVERY_ENABLED is false",
                }
            ],
        }

    async def reputation(self, tenant_id: str) -> dict[str, Any]:
        return {
            "status": "watch",
            "checkedAt": datetime.now(UTC).isoformat(),
            "domains": [],
            "providers": [
                {
                    "provider": "klyrow",
                    "channel": "email",
                    "status": "watch",
                    "queueDepth": 0,
                }
            ],
        }


@dataclass
class CommunicationsService:
    store: MemoryCommunicationsStore
    commands: CommandService
    adapter: KlyrowEmailAdapter = field(default_factory=DisabledKlyrowEmailAdapter)

    async def submit_email(
        self,
        request: CreateMessageRequest,
        *,
        tenant_id: str,
        correlation_id: str,
        idempotency_key: str,
        actor: str,
        authorization: str,
        token_verifier: Any,
    ) -> tuple[CommunicationMessage, bool]:
        caller = caller_for_authorization(authorization)
        claims = await token_verifier.verify(
            authorization,
            expected_client_id=caller.client_id,
            required_scope=caller.command_scope,
        )
        authorize_command(caller, command_type="email.message.send.v1", target="klyrow-email")
        authorize_tenant(claims, tenant_id)
        subject = claims.get("sub")
        if subject != actor:
            raise AuthorizationError("requested actor must equal token subject")
        body = request.model_dump(mode="json", by_alias=True)
        digest = _canonical_digest(body)
        key = (tenant_id, "POST /v1/communications/messages", idempotency_key)
        existing = self.store.idempotency.get(key)
        if existing is not None:
            existing_digest, existing_message_id = existing
            if existing_digest != digest:
                raise CommunicationsConflict("Idempotency-Key was reused with different content")
            return self.store.messages[(tenant_id, existing_message_id)].model_copy(), True

        recipient = str(request.to[0]).lower()
        sender = str(request.from_).lower() if request.from_ is not None else ""
        sender_domain = sender.rsplit("@", 1)[1] if "@" in sender else ""
        status: MessageStatus = "accepted"
        failure_code: str | None = None
        failure_message: str | None = None
        if (tenant_id, recipient) in self.store.suppressions:
            status = "suppressed"
            failure_code = "recipient_suppressed"
            failure_message = "recipient is suppressed before provider submission"
        elif (tenant_id, recipient) in self.store.denied_consent or request.metadata.get("consent") == "denied":
            status = "suppressed"
            failure_code = "consent_required"
            failure_message = "recipient does not have required consent"
        elif sender and self.store.verified_senders and (tenant_id, sender) not in self.store.verified_senders:
            raise RequestValidationError("sender identity is not verified for tenant")
        elif sender_domain and self.store.verified_domains and (tenant_id, sender_domain) not in self.store.verified_domains:
            raise RequestValidationError("sender domain is not verified for tenant")

        now = datetime.now(UTC)
        message_id = uuid.uuid4()
        command_id = uuid.uuid4()
        message = CommunicationMessage(
            messageId=message_id,
            tenantId=tenant_id,
            channel="email",
            direction="outbound",
            status=status,
            correlationId=correlation_id,
            idempotencyKey=idempotency_key,
            operationId=command_id,
            provider="klyrow",
            failureCode=failure_code,
            failureMessage=failure_message,
            createdAt=now,
            acceptedAt=now,
            completedAt=now if status == "suppressed" else None,
            updatedAt=now,
            metadata={"recipientCount": len(request.to), **request.metadata},
        )
        command: CommandEnvelope | None = None
        if status != "suppressed":
            command = CommandEnvelope(
                command_id=command_id,
                command_type="email.message.send.v1",
                command_version="1.0",
                target="klyrow-email",
                tenant_id=tenant_id,
                requested_by=actor,
                correlation_id=correlation_id,
                idempotency_key=idempotency_key,
                capability="EMAIL_DELIVERY",
                payload={
                    "message_id": str(message_id),
                    "channel": "email",
                    "from": sender,
                    "to": [str(item).lower() for item in request.to],
                    "content": request.content.model_dump(
                        mode="json",
                        exclude_none=True,
                    ),
                    "scheduled_at": (
                        request.scheduledAt.isoformat()
                        if request.scheduledAt
                        else None
                    ),
                    "metadata": request.metadata,
                },
            )
            self.commands.policies.authorize(command)

        self.store.messages[(tenant_id, message_id)] = message
        self.store.idempotency[key] = (digest, message_id)
        self.store.add_event(tenant_id, message_id, event_type="accepted", status="accepted", provider="klyrow")
        if status == "suppressed":
            self.store.add_event(
                tenant_id,
                message_id,
                event_type=failure_code or "suppressed",
                status="suppressed",
                provider="klyrow",
            )
            return message, False

        assert command is not None
        await self.commands.submit(command, authenticated_subject=actor)
        message.status = "queued"
        message.updatedAt = datetime.now(UTC)
        self.store.messages[(tenant_id, message_id)] = message
        self.store.add_event(tenant_id, message_id, event_type="queued", status="queued", provider="klyrow")
        return message, False

    def list_messages(self, tenant_id: str, *, channel: str | None = None, status: str | None = None) -> list[CommunicationMessage]:
        values = [item for (tenant, _), item in self.store.messages.items() if tenant == tenant_id]
        if channel:
            values = [item for item in values if item.channel == channel]
        if status:
            values = [item for item in values if item.status == status]
        return sorted(values, key=lambda item: item.createdAt, reverse=True)

    def get_message(self, tenant_id: str, message_id: uuid.UUID) -> CommunicationMessage:
        try:
            return self.store.messages[(tenant_id, message_id)]
        except KeyError as exc:
            raise CommunicationsNotFound("message was not found") from exc

    def message_events(self, tenant_id: str, message_id: uuid.UUID) -> list[MessageEvent]:
        self.get_message(tenant_id, message_id)
        return sorted(self.store.events.get((tenant_id, message_id), []), key=lambda item: item.occurredAt)

    async def refresh_command_status(
        self,
        tenant_id: str,
        message_id: uuid.UUID,
    ) -> CommunicationMessage:
        message = self.get_message(tenant_id, message_id)
        if message.operationId is None:
            return message
        operation = await self.commands.get(tenant_id, message.operationId)
        target_status = _command_state_to_canonical(operation.state)
        if target_status is None or target_status == message.status:
            return message
        if message.status in {"delivered", "failed", "cancelled", "suppressed", "expired"}:
            return message

        now = datetime.now(UTC)
        update: dict[str, Any] = {
            "status": target_status,
            "providerReference": (
                operation.provider_operation_id or message.providerReference
            ),
            "updatedAt": now,
        }
        if target_status == "indeterminate":
            update.update(
                {
                    "failureCode": "provider_outcome_unknown",
                    "failureMessage": (
                        operation.last_error
                        or "provider outcome requires authoritative read-back"
                    ),
                }
            )
        elif target_status == "failed":
            update.update(
                {
                    "failureCode": "provider_command_failed",
                    "failureMessage": operation.last_error,
                    "completedAt": now,
                }
            )
        updated = message.model_copy(update=update)
        self.store.messages[(tenant_id, message_id)] = updated
        self.store.add_event(
            tenant_id,
            message_id,
            event_type=f"command.{operation.state}",
            status=target_status,
            provider="klyrow",
            provider_reference=updated.providerReference,
            metadata={"commandState": operation.state},
            event_id=uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"codestra:communications:{tenant_id}:{operation.command_id}:{operation.state}",
            ),
        )
        return updated

    def cancel(self, tenant_id: str, message_id: uuid.UUID) -> CommunicationMessage:
        message = self.get_message(tenant_id, message_id)
        if message.status not in {"accepted", "queued"}:
            raise CommunicationsConflict("message cannot be cancelled in its current state")
        updated = message.model_copy(
            update={
                "status": "cancelled",
                "completedAt": datetime.now(UTC),
                "updatedAt": datetime.now(UTC),
            }
        )
        self.store.messages[(tenant_id, message_id)] = updated
        self.store.add_event(tenant_id, message_id, event_type="cancelled", status="cancelled", provider="klyrow")
        return updated

    def record_provider_event(self, envelope: Any) -> bool:
        payload = envelope.payload if hasattr(envelope, "payload") else {}
        tenant_id = envelope.tenant_id
        raw_message_id = payload.get("messageId") or payload.get("message_id")
        if not raw_message_id:
            return False
        try:
            message_id = uuid.UUID(str(raw_message_id))
        except ValueError:
            return False
        message = self.store.messages.get((tenant_id, message_id))
        if message is None:
            return False
        event_id = str(envelope.event_id)
        event_digest = _canonical_digest(envelope.model_dump(mode="json"))
        replay_key = (tenant_id, event_id)
        existing_digest = self.store.provider_event_digests.get(replay_key)
        if existing_digest is not None:
            if existing_digest != event_digest:
                raise CommunicationsConflict(
                    "provider event identity was reused with different content"
                )
            return False
        raw_status = str(payload.get("status") or payload.get("canonical_status") or envelope.event_type.rsplit(".", 1)[-1])
        status = _provider_status_to_canonical(raw_status)
        provider_reference = payload.get("providerReference") or payload.get("provider_reference") or payload.get("provider_message_id")
        updated = message.model_copy(
            update={
                "status": status,
                "providerReference": str(provider_reference) if provider_reference else message.providerReference,
                "failureCode": payload.get("failureCode") or payload.get("failure_code") or message.failureCode,
                "failureMessage": payload.get("failureMessage") or payload.get("failure_message") or message.failureMessage,
                "completedAt": datetime.now(UTC) if status in {"delivered", "failed", "cancelled", "suppressed", "expired"} else message.completedAt,
                "updatedAt": datetime.now(UTC),
            }
        )
        self.store.messages[(tenant_id, message_id)] = updated
        self.store.add_event(
            tenant_id,
            message_id,
            event_type=envelope.event_type,
            status=status,
            provider="klyrow",
            provider_reference=updated.providerReference,
            metadata={"providerEventType": payload.get("providerEventType") or payload.get("provider_event_type")},
            event_id=_provider_event_uuid(tenant_id, event_id),
        )
        self.store.provider_event_digests[replay_key] = event_digest
        return True
