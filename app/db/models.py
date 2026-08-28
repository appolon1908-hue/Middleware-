from datetime import datetime
from typing import Any
from uuid import UUID, uuid4
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class IntegrationEvent(Base):
    __tablename__ = "integration_event"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(16), nullable=False, default="1.0")
    original_event_id: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    entity_key: Mapped[str | None] = mapped_column(String(256))
    source_system: Mapped[str] = mapped_column(String(50), nullable=False, default="vicidial")
    correlation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(24), nullable=False, default="queued")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    __table_args__ = (Index("ix_integration_event_payload_hash", "payload_hash"),)


class IntegrationDelivery(Base):
    __tablename__ = "integration_delivery"
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    event_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("integration_event.id", ondelete="CASCADE"), nullable=False
    )
    target: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="disabled")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_owner: Mapped[str | None] = mapped_column(String(128))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    available_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    result_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    __table_args__ = (
        UniqueConstraint("event_id", "target", name="uq_delivery_event_target"),
    )


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_record"
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    scope: Mapped[str] = mapped_column(String(100), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    response: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status_code: Mapped[int] = mapped_column(Integer, nullable=False)
    event_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("integration_event.id")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        UniqueConstraint("scope", "key_hash", name="uq_idempotency_scope_key"),
    )


class PublisherNonce(Base):
    __tablename__ = "publisher_nonce"
    key_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    nonce: Mapped[str] = mapped_column(String(128), primary_key=True)
    signed_at: Mapped[int] = mapped_column(BigInteger, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PublisherAcknowledgement(Base):
    __tablename__ = "publisher_acknowledgement"
    acknowledgement_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    event_id: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    duplicate: Mapped[bool] = mapped_column(Boolean, nullable=False)
    retryable: Mapped[bool] = mapped_column(Boolean, nullable=False)
    reason_code: Mapped[str] = mapped_column(String(64), nullable=False)
    acknowledgement: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class SecurityRejection(Base):
    __tablename__ = "security_rejection"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    correlation_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    claimed_publisher: Mapped[str | None] = mapped_column(String(128))
    authentication_state: Mapped[str] = mapped_column(
        String(16), nullable=False, default="UNVERIFIED"
    )
    key_id: Mapped[str | None] = mapped_column(String(64))
    reason_code: Mapped[str] = mapped_column(String(64), nullable=False)
    payload_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    source_ip_classification: Mapped[str] = mapped_column(String(16), nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    __table_args__ = (
        CheckConstraint(
            "authentication_state = 'UNVERIFIED'",
            name="ck_security_rejection_unverified",
        ),
    )


class InvalidEventQuarantine(Base):
    __tablename__ = "invalid_event_quarantine"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    server_correlation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    client_correlation_id: Mapped[str | None] = mapped_column(String(128))
    claimed_source: Mapped[str | None] = mapped_column(String(64))
    claimed_publisher_identity: Mapped[str | None] = mapped_column(String(128))
    authenticated_publisher_id: Mapped[str] = mapped_column(String(128), nullable=False)
    authentication_state: Mapped[str] = mapped_column(String(24), nullable=False)
    authentication_key_id: Mapped[str | None] = mapped_column(String(64))
    original_signature_verification: Mapped[str] = mapped_column(String(24), nullable=False)
    payload_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    encrypted_payload: Mapped[bytes | None] = mapped_column(LargeBinary)
    encryption_nonce: Mapped[bytes | None] = mapped_column(LargeBinary)
    encryption_key_version: Mapped[str | None] = mapped_column(String(32))
    sanitized_preview: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    reason_code: Mapped[str] = mapped_column(String(64), nullable=False)
    business_unit: Mapped[str | None] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING_REVIEW")
    review_owner: Mapped[str | None] = mapped_column(String(128))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_by: Mapped[str | None] = mapped_column(String(128))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    replayed_event_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("integration_event.id")
    )
    replay_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    occurrence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    legal_hold: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    retention_policy_version: Mapped[str] = mapped_column(String(32), nullable=False)
    retention_deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    record_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    __table_args__ = (
        CheckConstraint("replay_count >= 0", name="ck_quarantine_replay_count"),
        CheckConstraint("occurrence_count >= 1", name="ck_quarantine_occurrence_count"),
        CheckConstraint("retention_deadline > received_at", name="ck_quarantine_retention"),
        CheckConstraint("record_version >= 1", name="ck_quarantine_record_version"),
        CheckConstraint(
            "(review_owner IS NULL) = (reviewed_at IS NULL)",
            name="ck_quarantine_review_consistency",
        ),
        CheckConstraint(
            "(resolved_by IS NULL) = (resolved_at IS NULL)",
            name="ck_quarantine_resolution_consistency",
        ),
        CheckConstraint(
            "replayed_event_id IS NULL OR (authentication_state = 'VERIFIED' AND "
            "status = 'REPLAYED' AND resolved_at IS NOT NULL)",
            name="ck_quarantine_replay_eligibility",
        ),
        CheckConstraint(
            "status IN ('PENDING_REVIEW','UNDER_REVIEW','CORRECTABLE',"
            "'REPLAY_APPROVED','REPLAYING','REPLAYED','RESOLVED_NO_REPLAY',"
            "'EXPIRED','REJECTED')",
            name="ck_quarantine_state",
        ),
        CheckConstraint(
            "authentication_state = 'VERIFIED' AND "
            "original_signature_verification = 'VERIFIED'",
            name="ck_quarantine_verified_auth",
        ),
        CheckConstraint(
            "(encrypted_payload IS NULL AND encryption_nonce IS NULL AND "
            "encryption_key_version IS NULL) OR "
            "(encrypted_payload IS NOT NULL AND encryption_nonce IS NOT NULL AND "
            "encryption_key_version IS NOT NULL)",
            name="ck_quarantine_encryption_fields",
        ),
        Index("ix_quarantine_status_received", "status", "received_at"),
        Index("ix_quarantine_publisher_received", "authenticated_publisher_id", "received_at"),
        Index("ix_quarantine_correlation", "server_correlation_id"),
        Index(
            "ix_quarantine_retention_active",
            "retention_deadline",
            postgresql_where=text("legal_hold = false"),
        ),
        Index("ix_quarantine_fingerprint", "payload_fingerprint"),
    )


class QuarantineCorrection(Base):
    __tablename__ = "quarantine_correction"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    quarantine_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("invalid_event_quarantine.id", ondelete="RESTRICT"),
        nullable=False,
    )
    correction_version: Mapped[int] = mapped_column(Integer, nullable=False)
    correction_reason: Mapped[str] = mapped_column(String(512), nullable=False)
    reviewer: Mapped[str] = mapped_column(String(128), nullable=False)
    derived_correlation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    payload_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    encrypted_payload: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    encryption_nonce: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    encryption_key_version: Mapped[str] = mapped_column(String(32), nullable=False)
    sanitized_diff: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    __table_args__ = (
        UniqueConstraint(
            "quarantine_id", "correction_version",
            name="uq_quarantine_correction_version",
        ),
        CheckConstraint(
            "correction_version >= 1", name="ck_quarantine_correction_version"
        ),
    )


class EventInbox(Base):
    __tablename__ = "event_inbox"
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    event_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    source: Mapped[str] = mapped_column(String(32))
    event_type: Mapped[str] = mapped_column(String(100))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    correlation_id: Mapped[str] = mapped_column(String(128), index=True)
    status: Mapped[str] = mapped_column(String(24), default="accepted")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class OutboxEvent(Base):
    __tablename__ = "outbox_event"
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    topic: Mapped[str] = mapped_column(String(128))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    correlation_id: Mapped[str | None] = mapped_column(String(128), index=True)
    status: Mapped[str] = mapped_column(String(24), default="pending")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    dead_lettered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    replay_count: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class SyncJob(Base):
    __tablename__ = "sync_job"
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    job_type: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(24), default="queued")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    last_error: Mapped[str | None] = mapped_column(Text)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class WebhookDelivery(Base):
    __tablename__ = "webhook_delivery"
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    target: Mapped[str] = mapped_column(String(128))
    event_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    status: Mapped[str] = mapped_column(String(24), default="pending")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuditEvent(Base):
    __tablename__ = "audit_event"
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    action: Mapped[str] = mapped_column(String(128))
    subject: Mapped[str] = mapped_column(String(128))
    correlation_id: Mapped[str] = mapped_column(String(128))
    decision: Mapped[str] = mapped_column(String(32))
    redacted_payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class PolicyDecision(Base):
    __tablename__ = "policy_decision"
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    policy: Mapped[str] = mapped_column(String(128))
    allowed: Mapped[bool] = mapped_column(Boolean)
    reason: Mapped[str] = mapped_column(Text)
    correlation_id: Mapped[str] = mapped_column(String(128))
    context: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class OrchestrationRequest(Base):
    __tablename__ = "orchestration_request"
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    request_uid: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    operation: Mapped[str] = mapped_column(String(32), nullable=False)
    business_unit: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    subject_reference: Mapped[str] = mapped_column(String(128), nullable=False)
    department_reference: Mapped[str] = mapped_column(String(128), nullable=False)
    team_reference: Mapped[str] = mapped_column(String(128), nullable=False)
    supervisor_reference: Mapped[str] = mapped_column(String(128), nullable=False)
    campaign_references: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    requested_resources: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    idempotency_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="disabled")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class CredentialGrant(Base):
    __tablename__ = "credential_grant"
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    orchestration_request_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("orchestration_request.id", ondelete="CASCADE"),
        nullable=False,
    )
    credential_type: Mapped[str] = mapped_column(String(32), nullable=False)
    vault_reference: Mapped[str] = mapped_column(String(255), nullable=False)
    secret_fingerprint: Mapped[str] = mapped_column(String(128), nullable=False)
    retrieval_token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    retrieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class LeadSyncRequest(Base):
    __tablename__ = "lead_sync_request"
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    source_reference: Mapped[str] = mapped_column(String(128), nullable=False)
    business_unit: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    campaign_reference: Mapped[str] = mapped_column(String(128), nullable=False)
    list_reference: Mapped[str] = mapped_column(String(128), nullable=False)
    canonical_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    correlation_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    state: Mapped[str] = mapped_column(String(24), nullable=False, default="disabled")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ReconciliationCheckpoint(Base):
    __tablename__ = "reconciliation_checkpoint"
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    source: Mapped[str] = mapped_column(String(64), unique=True)
    cursor: Mapped[str | None] = mapped_column(String(256))
    status: Mapped[str] = mapped_column(String(24), default="idle")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class TransferPolicyDecision(Base):
    __tablename__ = "transfer_policy_decision"
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    transfer_id: Mapped[str] = mapped_column(String(128))
    allowed: Mapped[bool] = mapped_column(Boolean)
    reason: Mapped[str] = mapped_column(Text)
    correlation_id: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class SystemHealthSnapshot(Base):
    __tablename__ = "system_health_snapshot"
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    component: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(24))
    details: Mapped[dict[str, Any]] = mapped_column(JSONB)
    checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class TelephonyExtensionPool(Base):
    __tablename__ = "telephony_extension_pool"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    business_unit: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    role_class: Mapped[str] = mapped_column(String(32), nullable=False)
    range_start: Mapped[int] = mapped_column(Integer, nullable=False)
    range_end: Mapped[int] = mapped_column(Integer, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    __table_args__ = (
        CheckConstraint("range_start >= 6100", name="ck_telephony_pool_start"),
        CheckConstraint("range_end <= 6999", name="ck_telephony_pool_end"),
        CheckConstraint("range_start <= range_end", name="ck_telephony_pool_order"),
    )


class TelephonyExtensionReservation(Base):
    __tablename__ = "telephony_extension_reservation"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    extension: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    employee_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    request_id: Mapped[str] = mapped_column(String(128), nullable=False)
    pool_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("telephony_extension_pool.id"), nullable=False
    )
    state: Mapped[str] = mapped_column(String(24), nullable=False, default="RESERVED")
    idempotency_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    evidence_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    reserved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cooldown_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        CheckConstraint("extension <> 6101", name="ck_telephony_reservation_6101"),
        CheckConstraint("extension <> 1001", name="ck_telephony_reservation_1001"),
        CheckConstraint(
            "state IN ('RESERVED','DISABLED_READY','ACTIVE','SUSPENDED','RELEASED','EXPIRED','COOLDOWN')",
            name="ck_telephony_reservation_state",
        ),
        Index(
            "uq_telephony_active_extension",
            "extension",
            unique=True,
            postgresql_where=text(
                "state IN ('RESERVED','DISABLED_READY','ACTIVE','SUSPENDED','COOLDOWN')"
            ),
        ),
        Index(
            "uq_telephony_active_employee",
            "employee_id",
            unique=True,
            postgresql_where=text(
                "state IN ('RESERVED','DISABLED_READY','ACTIVE','SUSPENDED')"
            ),
        ),
    )


class TelephonyProvisioningSaga(Base):
    __tablename__ = "telephony_provisioning_saga"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    request_id: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    employee_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    business_unit: Mapped[str] = mapped_column(String(64), nullable=False)
    campaign: Mapped[str] = mapped_column(String(64), nullable=False)
    role: Mapped[str] = mapped_column(String(64), nullable=False)
    extension: Mapped[int | None] = mapped_column(Integer)
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="DRAFT")
    idempotency_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    correlation_id: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    approved_odoo_request: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    credential_reference: Mapped[str | None] = mapped_column(String(255))
    completed_steps: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    last_error_code: Mapped[str | None] = mapped_column(String(64))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    __table_args__ = (
        CheckConstraint("version >= 1", name="ck_telephony_saga_version"),
        CheckConstraint(
            "state IN ('DRAFT','PENDING_APPROVAL','APPROVED','INVENTORY_CHECK','RESERVED',"
            "'PROVISIONING','DISABLED_READY','ACTIVATION_PENDING','ACTIVE','FAILED',"
            "'ROLLED_BACK','SUSPENDING','SUSPENDED','DEPROVISIONING','COOLDOWN')",
            name="ck_telephony_saga_state",
        ),
    )
