from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Literal

import asyncpg
from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from .api_inputs import authenticated_tenant, required_header
from .commands import CommandCapabilityDisabled
from .communications import (
    CommunicationsConflict,
    CommunicationsError,
    CommunicationsService,
    CreateMessageRequest,
)
from .config import Settings
from .security import AuthorizationError, RequestValidationError


ROOT = Path(__file__).resolve().parents[1]
DOMAIN_REGISTRY_PATH = ROOT / "config" / "postal-domain-registry.json"
PRODUCTION_OPERATOR_CLIENT_ID = "production-operator"

ProductionMode = Literal[
    "SAFE",
    "TRANSACTIONAL_CANARY",
    "TRANSACTIONAL_PRODUCTION",
    "CAMPAIGN_PRODUCTION",
]
AuthorizationState = Literal[
    "NOT_AUTHORIZED",
    "AUTHORIZED_NOT_ACTIVE",
    "ACTIVE",
    "REVOKED",
]
RecipientScope = Literal[
    "DENY_ALL",
    "ALLOWLIST",
    "TRANSACTIONAL_ANY",
    "CONSENTED_MARKETING",
]


class EmailProductionBlocked(CommunicationsError):
    status_code = 403
    code = "email_production_blocked"


class EmailProductionUnavailable(CommunicationsError):
    status_code = 503
    code = "email_production_unavailable"
    retryable = True


class EmailProductionRateLimited(CommunicationsError):
    status_code = 429
    code = "email_production_quota_exhausted"
    retryable = True


class EmailProductionPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenantId: str
    mode: ProductionMode = "SAFE"
    authorizationState: AuthorizationState = "NOT_AUTHORIZED"
    approvedDomains: list[str] = Field(default_factory=list, max_length=100)
    approvedSenders: list[EmailStr] = Field(default_factory=list, max_length=500)
    recipientScope: RecipientScope = "DENY_ALL"
    approvedRecipients: list[EmailStr] = Field(default_factory=list, max_length=500)
    perMinuteLimit: int = Field(default=0, ge=0, le=100_000)
    perHourLimit: int = Field(default=0, ge=0, le=1_000_000)
    perDayLimit: int = Field(default=0, ge=0, le=10_000_000)
    validFrom: datetime | None = None
    validUntil: datetime | None = None
    changeId: str | None = Field(default=None, max_length=200)
    approvedBy: str | None = Field(default=None, max_length=300)
    monitoringOwner: str | None = Field(default=None, max_length=300)
    killSwitchOpen: bool = False
    version: int = Field(default=1, ge=1)
    updatedAt: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("approvedDomains")
    @classmethod
    def normalize_domains(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        for value in values:
            domain = value.strip().lower().rstrip(".")
            if (
                not domain
                or len(domain) > 253
                or "@" in domain
                or domain.startswith(".")
                or domain.endswith(".")
            ):
                raise ValueError("invalid approved domain")
            normalized.append(domain)
        if len(set(normalized)) != len(normalized):
            raise ValueError("approved domains must be unique")
        return normalized

    @model_validator(mode="after")
    def validate_window(self) -> "EmailProductionPolicy":
        if self.validFrom and self.validFrom.tzinfo is None:
            raise ValueError("validFrom must be timezone-aware")
        if self.validUntil and self.validUntil.tzinfo is None:
            raise ValueError("validUntil must be timezone-aware")
        if self.validFrom and self.validUntil and self.validUntil <= self.validFrom:
            raise ValueError("validUntil must be after validFrom")
        return self


class AuthorizeEmailProduction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expectedVersion: int = Field(ge=1)
    mode: Literal[
        "TRANSACTIONAL_CANARY",
        "TRANSACTIONAL_PRODUCTION",
        "CAMPAIGN_PRODUCTION",
    ]
    approvedDomains: list[str] = Field(min_length=1, max_length=100)
    approvedSenders: list[EmailStr] = Field(min_length=1, max_length=500)
    recipientScope: RecipientScope
    approvedRecipients: list[EmailStr] = Field(default_factory=list, max_length=500)
    perMinuteLimit: int = Field(ge=1, le=100_000)
    perHourLimit: int = Field(ge=1, le=1_000_000)
    perDayLimit: int = Field(ge=1, le=10_000_000)
    validFrom: datetime | None = None
    validUntil: datetime | None = None
    changeId: str = Field(min_length=3, max_length=200)
    monitoringOwner: str = Field(min_length=1, max_length=300)
    reason: str = Field(min_length=3, max_length=500)

    @model_validator(mode="after")
    def validate_scope(self) -> "AuthorizeEmailProduction":
        if self.perMinuteLimit > self.perHourLimit or self.perHourLimit > self.perDayLimit:
            raise ValueError("quota limits must be monotonic")
        if self.mode == "TRANSACTIONAL_CANARY":
            if self.recipientScope != "ALLOWLIST" or not self.approvedRecipients:
                raise ValueError("canary mode requires an explicit recipient allowlist")
        elif self.mode == "TRANSACTIONAL_PRODUCTION":
            if self.recipientScope not in {"ALLOWLIST", "TRANSACTIONAL_ANY"}:
                raise ValueError("transactional production requires transactional recipient scope")
        elif self.recipientScope != "CONSENTED_MARKETING":
            raise ValueError("campaign production requires consented marketing scope")
        return self


class ControlMutation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expectedVersion: int = Field(ge=1)
    reason: str = Field(min_length=3, max_length=500)


class KillSwitchMutation(ControlMutation):
    open: bool


@dataclass(frozen=True)
class QuotaReservation:
    tenant_id: str
    units: int
    reserved_at: datetime


@dataclass
class MemoryEmailProductionPolicyStore:
    policies: dict[str, EmailProductionPolicy] = field(default_factory=dict)
    mutations: dict[tuple[str, str, str, str], tuple[str, dict[str, Any]]] = field(
        default_factory=dict
    )
    audits: list[dict[str, Any]] = field(default_factory=list)
    quotas: dict[tuple[str, str, datetime], int] = field(default_factory=dict)

    async def get(self, tenant_id: str) -> EmailProductionPolicy:
        policy = self.policies.get(tenant_id)
        if policy is None:
            return EmailProductionPolicy(tenantId=tenant_id)
        return policy.model_copy(deep=True)

    async def mutate(
        self,
        tenant_id: str,
        *,
        actor: str,
        correlation_id: str,
        idempotency_key: str,
        action: str,
        expected_version: int,
        reason: str,
        request_sha256: str,
        transform: Callable[[EmailProductionPolicy], EmailProductionPolicy],
    ) -> EmailProductionPolicy:
        mutation_key = (tenant_id, action, actor, idempotency_key)
        prior = self.mutations.get(mutation_key)
        if prior is not None:
            if prior[0] != request_sha256:
                raise CommunicationsConflict(
                    "Idempotency-Key was reused with different production-control content"
                )
            return EmailProductionPolicy.model_validate(prior[1])
        current = await self.get(tenant_id)
        if current.version != expected_version:
            raise CommunicationsConflict("expectedVersion is stale")
        changed = transform(current).model_copy(
            update={"version": current.version + 1, "updatedAt": datetime.now(UTC)}
        )
        self.policies[tenant_id] = changed.model_copy(deep=True)
        response = changed.model_dump(mode="json")
        self.mutations[mutation_key] = (request_sha256, response)
        self.audits.append(
            {
                "tenant_id": tenant_id,
                "action": action,
                "actor_id": actor,
                "reason": reason,
                "correlation_id": correlation_id,
                "previous_policy": current.model_dump(mode="json"),
                "new_policy": response,
                "created_at": datetime.now(UTC),
            }
        )
        return changed.model_copy(deep=True)

    async def reserve_quota(
        self, tenant_id: str, units: int, policy: EmailProductionPolicy
    ) -> QuotaReservation:
        reserved_at = datetime.now(UTC)
        buckets = _quota_buckets(reserved_at)
        limits = {
            "minute": policy.perMinuteLimit,
            "hour": policy.perHourLimit,
            "day": policy.perDayLimit,
        }
        for window, start in buckets.items():
            used = self.quotas.get((tenant_id, window, start), 0)
            if used + units > limits[window]:
                raise EmailProductionRateLimited(f"{window} email quota is exhausted")
        for window, start in buckets.items():
            key = (tenant_id, window, start)
            self.quotas[key] = self.quotas.get(key, 0) + units
        return QuotaReservation(tenant_id=tenant_id, units=units, reserved_at=reserved_at)

    async def release_quota(self, reservation: QuotaReservation) -> None:
        for window, start in _quota_buckets(reservation.reserved_at).items():
            key = (reservation.tenant_id, window, start)
            self.quotas[key] = max(0, self.quotas.get(key, 0) - reservation.units)

    async def quota_status(self, tenant_id: str) -> dict[str, int]:
        now = datetime.now(UTC)
        return {
            window: self.quotas.get((tenant_id, window, start), 0)
            for window, start in _quota_buckets(now).items()
        }

    async def audit(self, tenant_id: str, limit: int) -> list[dict[str, Any]]:
        return [
            item for item in reversed(self.audits) if item["tenant_id"] == tenant_id
        ][:limit]


@dataclass
class PostgresEmailProductionPolicyStore:
    pool: asyncpg.Pool

    async def get(self, tenant_id: str) -> EmailProductionPolicy:
        raw = await self.pool.fetchval(
            "SELECT payload FROM middleware_email_production_policy WHERE tenant_id=$1",
            tenant_id,
        )
        if raw is None:
            return EmailProductionPolicy(tenantId=tenant_id)
        return EmailProductionPolicy.model_validate(
            json.loads(raw) if isinstance(raw, str) else raw
        )

    async def mutate(
        self,
        tenant_id: str,
        *,
        actor: str,
        correlation_id: str,
        idempotency_key: str,
        action: str,
        expected_version: int,
        reason: str,
        request_sha256: str,
        transform: Callable[[EmailProductionPolicy], EmailProductionPolicy],
    ) -> EmailProductionPolicy:
        async with self.pool.acquire() as conn, conn.transaction():
            replay = await conn.fetchrow(
                """SELECT request_sha256,response_payload
                   FROM middleware_email_production_mutations
                   WHERE tenant_id=$1 AND action=$2 AND actor_id=$3 AND idempotency_key=$4""",
                tenant_id,
                action,
                actor,
                idempotency_key,
            )
            if replay is not None:
                if replay["request_sha256"] != request_sha256:
                    raise CommunicationsConflict(
                        "Idempotency-Key was reused with different production-control content"
                    )
                raw_response = replay["response_payload"]
                return EmailProductionPolicy.model_validate(
                    json.loads(raw_response)
                    if isinstance(raw_response, str)
                    else raw_response
                )
            row = await conn.fetchrow(
                "SELECT version,payload FROM middleware_email_production_policy WHERE tenant_id=$1 FOR UPDATE",
                tenant_id,
            )
            current = (
                EmailProductionPolicy(tenantId=tenant_id)
                if row is None
                else EmailProductionPolicy.model_validate(
                    json.loads(row["payload"])
                    if isinstance(row["payload"], str)
                    else row["payload"]
                )
            )
            if current.version != expected_version:
                raise CommunicationsConflict("expectedVersion is stale")
            changed = transform(current).model_copy(
                update={"version": current.version + 1, "updatedAt": datetime.now(UTC)}
            )
            previous_json = current.model_dump(mode="json")
            response = changed.model_dump(mode="json")
            await conn.execute(
                """INSERT INTO middleware_email_production_policy(tenant_id,version,payload,updated_at)
                   VALUES($1,$2,$3::jsonb,now())
                   ON CONFLICT(tenant_id) DO UPDATE SET version=EXCLUDED.version,
                     payload=EXCLUDED.payload,updated_at=EXCLUDED.updated_at""",
                tenant_id,
                changed.version,
                json.dumps(response, separators=(",", ":")),
            )
            await conn.execute(
                """INSERT INTO middleware_email_production_audit
                   (tenant_id,action,actor_id,reason,correlation_id,previous_policy,new_policy)
                   VALUES($1,$2,$3,$4,$5,$6::jsonb,$7::jsonb)""",
                tenant_id,
                action,
                actor,
                reason,
                correlation_id,
                json.dumps(previous_json, separators=(",", ":")),
                json.dumps(response, separators=(",", ":")),
            )
            await conn.execute(
                """INSERT INTO middleware_email_production_mutations
                   (tenant_id,action,actor_id,idempotency_key,request_sha256,response_payload)
                   VALUES($1,$2,$3,$4,$5,$6::jsonb)""",
                tenant_id,
                action,
                actor,
                idempotency_key,
                request_sha256,
                json.dumps(response, separators=(",", ":")),
            )
            return changed

    async def reserve_quota(
        self, tenant_id: str, units: int, policy: EmailProductionPolicy
    ) -> QuotaReservation:
        reserved_at = datetime.now(UTC)
        buckets = _quota_buckets(reserved_at)
        limits = {
            "minute": policy.perMinuteLimit,
            "hour": policy.perHourLimit,
            "day": policy.perDayLimit,
        }
        async with self.pool.acquire() as conn, conn.transaction():
            for window, start in buckets.items():
                used = await conn.fetchval(
                    """INSERT INTO middleware_email_quota_buckets
                       (tenant_id,window_kind,bucket_start,used,updated_at)
                       VALUES($1,$2,$3,$4,now())
                       ON CONFLICT(tenant_id,window_kind,bucket_start)
                       DO UPDATE SET used=middleware_email_quota_buckets.used + EXCLUDED.used,
                         updated_at=now()
                       WHERE middleware_email_quota_buckets.used + EXCLUDED.used <= $5
                       RETURNING used""",
                    tenant_id,
                    window,
                    start,
                    units,
                    limits[window],
                )
                if used is None or used > limits[window]:
                    raise EmailProductionRateLimited(
                        f"{window} email quota is exhausted"
                    )
        return QuotaReservation(tenant_id=tenant_id, units=units, reserved_at=reserved_at)

    async def release_quota(self, reservation: QuotaReservation) -> None:
        async with self.pool.acquire() as conn, conn.transaction():
            for window, start in _quota_buckets(reservation.reserved_at).items():
                await conn.execute(
                    """UPDATE middleware_email_quota_buckets
                       SET used=GREATEST(0,used-$4),updated_at=now()
                       WHERE tenant_id=$1 AND window_kind=$2 AND bucket_start=$3""",
                    reservation.tenant_id,
                    window,
                    start,
                    reservation.units,
                )

    async def quota_status(self, tenant_id: str) -> dict[str, int]:
        buckets = _quota_buckets(datetime.now(UTC))
        result: dict[str, int] = {}
        for window, start in buckets.items():
            result[window] = int(
                await self.pool.fetchval(
                    """SELECT COALESCE(used,0) FROM middleware_email_quota_buckets
                       WHERE tenant_id=$1 AND window_kind=$2 AND bucket_start=$3""",
                    tenant_id,
                    window,
                    start,
                )
                or 0
            )
        return result

    async def audit(self, tenant_id: str, limit: int) -> list[dict[str, Any]]:
        rows = await self.pool.fetch(
            """SELECT id,action,actor_id,reason,correlation_id,previous_policy,new_policy,created_at
               FROM middleware_email_production_audit
               WHERE tenant_id=$1 ORDER BY id DESC LIMIT $2""",
            tenant_id,
            limit,
        )
        return [dict(row) for row in rows]


EmailPolicyStore = MemoryEmailProductionPolicyStore | PostgresEmailProductionPolicyStore


def _quota_buckets(moment: datetime) -> dict[str, datetime]:
    value = moment.astimezone(UTC)
    return {
        "minute": value.replace(second=0, microsecond=0),
        "hour": value.replace(minute=0, second=0, microsecond=0),
        "day": value.replace(hour=0, minute=0, second=0, microsecond=0),
    }


def _domain_registry() -> dict[str, dict[str, Any]]:
    try:
        document = json.loads(DOMAIN_REGISTRY_PATH.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise EmailProductionUnavailable("postal domain registry is unavailable") from exc
    domains = document.get("domains")
    if not isinstance(domains, list):
        raise EmailProductionUnavailable("postal domain registry is invalid")
    result: dict[str, dict[str, Any]] = {}
    for item in domains:
        if isinstance(item, dict) and isinstance(item.get("domain"), str):
            result[item["domain"].lower()] = item
    return result


def _request_digest(body: BaseModel) -> str:
    return hashlib.sha256(
        json.dumps(
            body.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()


@dataclass
class EmailProductionControlService:
    store: EmailPolicyStore
    settings: Settings

    async def get(self, tenant_id: str) -> EmailProductionPolicy:
        return await self.store.get(tenant_id)

    def activation_blockers(self, policy: EmailProductionPolicy) -> list[str]:
        blockers: list[str] = []
        now = datetime.now(UTC)
        if policy.authorizationState not in {"AUTHORIZED_NOT_ACTIVE", "ACTIVE"}:
            blockers.append("production_authorization_missing")
        if policy.mode == "SAFE":
            blockers.append("production_mode_safe")
        if not self.settings.production_activation_id:
            blockers.append("production_activation_id_missing")
        if not self.settings.email_delivery_enabled:
            blockers.append("email_delivery_runtime_gate_closed")
        if policy.validFrom and now < policy.validFrom.astimezone(UTC):
            blockers.append("authorization_not_yet_valid")
        if policy.validUntil and now >= policy.validUntil.astimezone(UTC):
            blockers.append("authorization_expired")
        if not policy.approvedDomains:
            blockers.append("approved_domains_empty")
        if not policy.approvedSenders:
            blockers.append("approved_senders_empty")
        if min(policy.perMinuteLimit, policy.perHourLimit, policy.perDayLimit) <= 0:
            blockers.append("quota_not_configured")
        registry = _domain_registry()
        for domain in policy.approvedDomains:
            record = registry.get(domain)
            if record is None:
                blockers.append(f"domain_not_registered:{domain}")
                continue
            if record.get("latest_postal_dns_check") != "pass":
                blockers.append(f"postal_dns_not_pass:{domain}")
            if record.get("dkim_rotation_required") is True:
                blockers.append(f"dkim_rotation_incomplete:{domain}")
            if record.get("post_rotation_recheck_required") is True:
                blockers.append(f"post_rotation_recheck_incomplete:{domain}")
            if record.get("middleware_send_eligible") is not True:
                blockers.append(f"middleware_send_not_eligible:{domain}")
            if record.get("production_ready") is not True:
                blockers.append(f"domain_not_production_ready:{domain}")
        return blockers

    async def authorize(
        self,
        tenant_id: str,
        actor: str,
        correlation_id: str,
        idempotency_key: str,
        body: AuthorizeEmailProduction,
    ) -> EmailProductionPolicy:
        senders = [str(value).lower() for value in body.approvedSenders]
        recipients = [str(value).lower() for value in body.approvedRecipients]
        domains = [value.strip().lower().rstrip(".") for value in body.approvedDomains]
        for sender in senders:
            if sender.rsplit("@", 1)[-1] not in domains:
                raise RequestValidationError(
                    "every approved sender must belong to an approved domain"
                )

        def transform(current: EmailProductionPolicy) -> EmailProductionPolicy:
            return current.model_copy(
                update={
                    "mode": body.mode,
                    "authorizationState": "AUTHORIZED_NOT_ACTIVE",
                    "approvedDomains": domains,
                    "approvedSenders": senders,
                    "recipientScope": body.recipientScope,
                    "approvedRecipients": recipients,
                    "perMinuteLimit": body.perMinuteLimit,
                    "perHourLimit": body.perHourLimit,
                    "perDayLimit": body.perDayLimit,
                    "validFrom": body.validFrom,
                    "validUntil": body.validUntil,
                    "changeId": body.changeId,
                    "approvedBy": actor,
                    "monitoringOwner": body.monitoringOwner,
                    "killSwitchOpen": False,
                }
            )

        return await self.store.mutate(
            tenant_id,
            actor=actor,
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
            action="authorize",
            expected_version=body.expectedVersion,
            reason=body.reason,
            request_sha256=_request_digest(body),
            transform=transform,
        )

    async def activate(
        self,
        tenant_id: str,
        actor: str,
        correlation_id: str,
        idempotency_key: str,
        body: ControlMutation,
    ) -> EmailProductionPolicy:
        current = await self.store.get(tenant_id)
        blockers = self.activation_blockers(current)
        if blockers:
            raise EmailProductionBlocked(
                "production activation blocked: " + ",".join(blockers)
            )

        def transform(policy: EmailProductionPolicy) -> EmailProductionPolicy:
            return policy.model_copy(
                update={"authorizationState": "ACTIVE", "killSwitchOpen": True}
            )

        return await self.store.mutate(
            tenant_id,
            actor=actor,
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
            action="activate",
            expected_version=body.expectedVersion,
            reason=body.reason,
            request_sha256=_request_digest(body),
            transform=transform,
        )

    async def revoke(
        self,
        tenant_id: str,
        actor: str,
        correlation_id: str,
        idempotency_key: str,
        body: ControlMutation,
    ) -> EmailProductionPolicy:
        def transform(policy: EmailProductionPolicy) -> EmailProductionPolicy:
            return policy.model_copy(
                update={
                    "authorizationState": "REVOKED",
                    "mode": "SAFE",
                    "killSwitchOpen": False,
                }
            )

        return await self.store.mutate(
            tenant_id,
            actor=actor,
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
            action="revoke",
            expected_version=body.expectedVersion,
            reason=body.reason,
            request_sha256=_request_digest(body),
            transform=transform,
        )

    async def set_kill_switch(
        self,
        tenant_id: str,
        actor: str,
        correlation_id: str,
        idempotency_key: str,
        body: KillSwitchMutation,
    ) -> EmailProductionPolicy:
        current = await self.store.get(tenant_id)
        if body.open and current.authorizationState != "ACTIVE":
            raise EmailProductionBlocked(
                "kill switch cannot be opened without active authorization"
            )

        def transform(policy: EmailProductionPolicy) -> EmailProductionPolicy:
            return policy.model_copy(update={"killSwitchOpen": body.open})

        return await self.store.mutate(
            tenant_id,
            actor=actor,
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
            action="kill-switch-open" if body.open else "kill-switch-close",
            expected_version=body.expectedVersion,
            reason=body.reason,
            request_sha256=_request_digest(body),
            transform=transform,
        )

    async def guard_request(
        self,
        tenant_id: str,
        request: CreateMessageRequest,
        sender: str,
    ) -> tuple[EmailProductionPolicy, QuotaReservation]:
        policy = await self.store.get(tenant_id)
        now = datetime.now(UTC)
        if not self.settings.email_delivery_enabled:
            raise EmailProductionUnavailable(
                "email delivery runtime gate is closed"
            )
        if policy.authorizationState != "ACTIVE":
            raise EmailProductionBlocked("email production is not active")
        if not policy.killSwitchOpen:
            raise EmailProductionBlocked("email production kill switch is closed")
        if policy.validFrom and now < policy.validFrom.astimezone(UTC):
            raise EmailProductionBlocked("email production authorization is not yet valid")
        if policy.validUntil and now >= policy.validUntil.astimezone(UTC):
            raise EmailProductionBlocked("email production authorization has expired")
        sender_value = sender.lower()
        sender_domain = sender_value.rsplit("@", 1)[-1]
        if sender_domain not in policy.approvedDomains:
            raise EmailProductionBlocked("sender domain is outside production authorization")
        if sender_value not in {str(value).lower() for value in policy.approvedSenders}:
            raise EmailProductionBlocked("sender identity is outside production authorization")
        category = str(request.metadata.get("category") or "transactional").lower()
        recipients = [value.lower() for value in request.to]
        approved_recipients = {
            str(value).lower() for value in policy.approvedRecipients
        }
        if category == "marketing":
            if policy.mode != "CAMPAIGN_PRODUCTION":
                raise EmailProductionBlocked("campaign email is not authorized")
            if policy.recipientScope != "CONSENTED_MARKETING":
                raise EmailProductionBlocked("campaign recipient scope is not authorized")
        else:
            if policy.mode not in {
                "TRANSACTIONAL_CANARY",
                "TRANSACTIONAL_PRODUCTION",
                "CAMPAIGN_PRODUCTION",
            }:
                raise EmailProductionBlocked("transactional email is not authorized")
            if policy.recipientScope == "ALLOWLIST" and any(
                recipient not in approved_recipients for recipient in recipients
            ):
                raise EmailProductionBlocked("recipient is outside production allowlist")
            if policy.mode == "TRANSACTIONAL_CANARY" and policy.recipientScope != "ALLOWLIST":
                raise EmailProductionBlocked("canary mode requires recipient allowlist")
            if policy.recipientScope == "DENY_ALL":
                raise EmailProductionBlocked("recipient scope denies delivery")
        return policy, await self.store.reserve_quota(
            tenant_id, len(recipients), policy
        )


@dataclass
class ProductionGatedCommunicationsService(CommunicationsService):
    production_control: EmailProductionControlService | None = None
    enforce_production_policy: bool = False

    async def submit_message(self, request: CreateMessageRequest, **kwargs):
        if request.channel != "email" or not self.enforce_production_policy:
            return await super().submit_message(request, **kwargs)
        tenant_id = kwargs["tenant_id"]
        idempotency_key = kwargs["idempotency_key"]
        existing = self.store.idempotency.get(
            (tenant_id, "POST /v1/communications/messages", idempotency_key)
        )
        if existing is not None:
            return await super().submit_message(request, **kwargs)
        if self.production_control is None:
            raise EmailProductionUnavailable(
                "email production control service is unavailable"
            )
        if request.from_ is not None:
            sender = request.from_
        elif request.senderIdentityId is not None:
            sender = self.store.sender_identities.get(
                (tenant_id, request.senderIdentityId), ""
            )
        else:
            sender = ""
        if not sender:
            raise RequestValidationError("sender identity is required")
        policy, reservation = await self.production_control.guard_request(
            tenant_id, request, sender
        )
        try:
            message, duplicate = await super().submit_message(request, **kwargs)
        except Exception:
            await self.production_control.store.release_quota(reservation)
            raise
        if duplicate or message.status == "suppressed":
            await self.production_control.store.release_quota(reservation)
        message.metadata.setdefault("productionPolicyVersion", policy.version)
        message.metadata.setdefault("productionMode", policy.mode)
        message.metadata.setdefault("productionChangeId", policy.changeId)
        await self.store.persist()
        return message, duplicate


router = APIRouter(prefix="/platform/v1/email/production", tags=["email-production"])


def _control(request: Request) -> EmailProductionControlService:
    service = request.app.state.runtime.communications
    if not isinstance(service, ProductionGatedCommunicationsService):
        raise EmailProductionUnavailable("email production control is unavailable")
    if service.production_control is None:
        raise EmailProductionUnavailable("email production control is unavailable")
    return service.production_control


async def _operator(
    request: Request, *, mutation: bool
) -> tuple[str, str, str | None, str | None]:
    caller, claims, tenant_id = await authenticated_tenant(request, mutation=mutation)
    if caller.client_id != PRODUCTION_OPERATOR_CLIENT_ID:
        raise AuthorizationError("production operator identity is required")
    actor = claims.get("sub")
    if not isinstance(actor, str) or not actor:
        raise AuthorizationError("production operator subject is required")
    if not mutation:
        return tenant_id, actor, None, None
    correlation_id = required_header(
        request, "X-Correlation-ID", minimum=1, maximum=180
    )
    idempotency_key = required_header(
        request, "Idempotency-Key", minimum=8, maximum=180
    )
    return tenant_id, actor, correlation_id, idempotency_key


@router.get("/status", response_model=EmailProductionPolicy)
async def status(request: Request) -> EmailProductionPolicy:
    tenant_id, _, _, _ = await _operator(request, mutation=False)
    return await _control(request).get(tenant_id)


@router.get("/readiness")
async def readiness(request: Request) -> dict[str, Any]:
    tenant_id, _, _, _ = await _operator(request, mutation=False)
    control = _control(request)
    policy = await control.get(tenant_id)
    blockers = control.activation_blockers(policy)
    return {
        "tenant_id": tenant_id,
        "ready": not blockers,
        "blockers": blockers,
        "policy": policy.model_dump(mode="json"),
    }


@router.get("/quotas")
async def quotas(request: Request) -> dict[str, Any]:
    tenant_id, _, _, _ = await _operator(request, mutation=False)
    control = _control(request)
    policy = await control.get(tenant_id)
    used = await control.store.quota_status(tenant_id)
    return {
        "tenant_id": tenant_id,
        "used": used,
        "limits": {
            "minute": policy.perMinuteLimit,
            "hour": policy.perHourLimit,
            "day": policy.perDayLimit,
        },
    }


@router.get("/audit")
async def audit(
    request: Request, limit: int = Query(50, ge=1, le=200)
) -> dict[str, Any]:
    tenant_id, _, _, _ = await _operator(request, mutation=False)
    return {
        "items": await _control(request).store.audit(tenant_id, limit),
        "next_cursor": None,
    }


@router.post("/authorize", response_model=EmailProductionPolicy)
async def authorize(
    body: AuthorizeEmailProduction, request: Request
) -> EmailProductionPolicy:
    tenant_id, actor, correlation_id, idempotency_key = await _operator(
        request, mutation=True
    )
    assert correlation_id is not None and idempotency_key is not None
    return await _control(request).authorize(
        tenant_id, actor, correlation_id, idempotency_key, body
    )


@router.post("/activate", response_model=EmailProductionPolicy)
async def activate(
    body: ControlMutation, request: Request
) -> EmailProductionPolicy:
    tenant_id, actor, correlation_id, idempotency_key = await _operator(
        request, mutation=True
    )
    assert correlation_id is not None and idempotency_key is not None
    return await _control(request).activate(
        tenant_id, actor, correlation_id, idempotency_key, body
    )


@router.post("/revoke", response_model=EmailProductionPolicy)
async def revoke(
    body: ControlMutation, request: Request
) -> EmailProductionPolicy:
    tenant_id, actor, correlation_id, idempotency_key = await _operator(
        request, mutation=True
    )
    assert correlation_id is not None and idempotency_key is not None
    return await _control(request).revoke(
        tenant_id, actor, correlation_id, idempotency_key, body
    )


@router.post("/kill-switch", response_model=EmailProductionPolicy)
async def kill_switch(
    body: KillSwitchMutation, request: Request
) -> EmailProductionPolicy:
    tenant_id, actor, correlation_id, idempotency_key = await _operator(
        request, mutation=True
    )
    assert correlation_id is not None and idempotency_key is not None
    return await _control(request).set_kill_switch(
        tenant_id, actor, correlation_id, idempotency_key, body
    )
