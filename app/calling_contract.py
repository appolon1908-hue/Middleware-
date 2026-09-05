"""Odoo calling wire contract and explicit internal-only authorization.

No production account, telephone number, credential or enabled grant is shipped.
A policy is an operator-installed configuration, not a client request.
"""
from __future__ import annotations

import hashlib
import json
import os
import stat
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Literal, Mapping
from uuid import UUID, uuid5
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import (
    AwareDatetime, BaseModel, ConfigDict, Field, StrictBool, StrictInt,
    field_validator, model_validator,
)

CLIENT_ID = "odoo-integration"
INTERNAL_PREFIX = "telephony-internal."
ORIGINATE = INTERNAL_PREFIX + "calls.originate"
HANGUP = INTERNAL_PREFIX + "calls.hangup"
CAPABILITY = "INTERNAL_TELEPHONY_CALLS"
TARGET = "vicidial-restricted"
TERMINAL_CALL_STATES = frozenset({
    "completed", "failed", "missed", "rejected", "cancelled", "transferred",
})
NONTERMINAL_CALL_STATES = frozenset({
    "new", "initiating", "ringing", "offered", "answering", "connected",
    "held", "transferring", "ending",
})
Identity = Annotated[str, Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:@-]*$")]
IdempotencyKey = Annotated[str, Field(min_length=8, max_length=180, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")]
CALL_NAMESPACE = UUID("c20d27c8-a9c8-4eea-b4ef-29c60fc9ab40")


class CallingContractError(ValueError):
    """Safe error: never attach credentials, arbitrary response bodies or PII."""


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CallPrincipal(StrictModel):
    tenant_id: Identity
    subject: Identity
    employee_id: Identity
    campaign_id: Identity
    business_unit: Identity
    extension: Annotated[str, Field(pattern=r"^[0-9]{2,12}$")]

    @classmethod
    def from_claims(cls, claims: Mapping[str, object]) -> CallPrincipal:
        # These values must come from a verified token, never X-Agent-* headers.
        return cls(
            tenant_id=claims.get("tenant_id"), subject=claims.get("sub"),
            employee_id=claims.get("employee_id"), campaign_id=claims.get("campaign_id"),
            business_unit=claims.get("business_unit"), extension=claims.get("extension"),
        )


class OriginateRequest(StrictModel):
    """Preserves the merged Odoo client's field names and adds internal aliases."""
    employee_id: Identity
    campaign: Identity
    business_unit: Identity
    destination: Annotated[str, Field(min_length=3, max_length=96)]
    destination_class: Annotated[str, Field(min_length=1, max_length=40)]
    destination_country: Annotated[str, Field(min_length=2, max_length=2, pattern=r"^[A-Z]{2}$")]
    destination_timezone: Annotated[str, Field(min_length=1, max_length=64)]
    caller_id: Annotated[str, Field(pattern=r"^\+[1-9][0-9]{7,14}$")]
    lead_model: Literal["crm.lead"]
    lead_id: Annotated[StrictInt, Field(gt=0)]
    recording_requested: StrictBool = False
    idempotency_key: IdempotencyKey

    @model_validator(mode="after")
    def validate_destination(self) -> OriginateRequest:
        import re
        if self.destination_class == "internal_test":
            if re.fullmatch(r"internal:[A-Z][A-Z0-9_]{1,39}", self.destination) is None:
                raise ValueError("internal destination must be a named internal alias")
        elif re.fullmatch(r"\+[1-9][0-9]{7,14}", self.destination) is None:
            raise ValueError("external destination must be E.164")
        if self.recording_requested:
            raise ValueError("recording is outside the internal calling contract")
        return self

    @field_validator("destination_timezone")
    @classmethod
    def timezone_exists(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("unknown destination timezone") from exc
        return value

    def assert_principal(self, principal: CallPrincipal) -> None:
        if (self.employee_id, self.campaign, self.business_unit) != (
            principal.employee_id, principal.campaign_id, principal.business_unit,
        ):
            raise CallingContractError("calling_identity_mismatch")

    def payload(self) -> dict:
        return self.model_dump(mode="json", exclude={"idempotency_key"})


class MutationRequest(StrictModel):
    idempotency_key: IdempotencyKey
    expected_version: Annotated[StrictInt, Field(ge=1)]
    reason: Annotated[str, Field(min_length=3, max_length=200, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.: -]*$")]


class CallingGrant(StrictModel):
    """A single call on a single approved lead; no wildcard or PSTN authority."""
    authorization_reference: Identity
    principal: CallPrincipal
    destination: Annotated[str, Field(pattern=r"^internal:[A-Z][A-Z0-9_]{1,39}$")]
    caller_id: Annotated[str, Field(pattern=r"^\+[1-9][0-9]{7,14}$")]
    lead_id: Annotated[StrictInt, Field(gt=0)]
    not_before: AwareDatetime
    expires_at: AwareDatetime
    source_sha: Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")]
    internal_only: Literal[True] = True
    external_dialing: Literal[False] = False
    max_calls: Literal[1] = 1

    @field_validator("internal_only", "external_dialing", "max_calls", mode="before")
    @classmethod
    def literal_types(cls, value, info):
        expected = {"internal_only": True, "external_dialing": False, "max_calls": 1}[info.field_name]
        if type(value) is not type(expected) or value != expected:
            raise ValueError("calling policy literals must have their exact types")
        return value

    @model_validator(mode="after")
    def bounded_window(self) -> CallingGrant:
        duration = (self.expires_at - self.not_before).total_seconds()
        if not 0 < duration <= 3600:
            raise ValueError("calling grant must be bounded to at most one hour")
        return self

    def authorize(self, principal: CallPrincipal, body: OriginateRequest, *, source_sha: str,
                  now: datetime | None = None) -> None:
        current = now or datetime.now(UTC)
        if not self.not_before <= current < self.expires_at:
            raise CallingContractError("calling_grant_expired_or_not_yet_valid")
        if self.source_sha != source_sha or self.principal != principal:
            raise CallingContractError("calling_grant_identity_or_release_mismatch")
        if body.destination_class != "internal_test" or (
            body.destination, body.caller_id, body.lead_id
        ) != (self.destination, self.caller_id, self.lead_id):
            raise CallingContractError("calling_grant_destination_or_lead_mismatch")
        body.assert_principal(principal)

    def digest(self) -> str:
        raw = json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(raw.encode()).hexdigest()


def load_grant(environ: Mapping[str, str] | None = None) -> CallingGrant | None:
    """No policy path means disabled. Read a bounded, root-owned regular file.

    O_NOFOLLOW and fstat check the opened inode, rather than a pre-open pathname.
    Do not use this file to provision users or to activate SIP credentials.
    """
    env = os.environ if environ is None else environ
    name = env.get("CODESTRA_INTERNAL_CALL_POLICY_FILE", "")
    if not name:
        return None
    path = Path(name)
    if not path.is_absolute():
        raise CallingContractError("calling_policy_path_must_be_absolute")
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as stream:
            metadata = os.fstat(stream.fileno())
            if (not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != 0
                    or metadata.st_mode & 0o027 or metadata.st_size > 16_384):
                raise CallingContractError("calling_policy_permissions_or_size_invalid")
            data = stream.read(16_385)
            if len(data) > 16_384:
                raise CallingContractError("calling_policy_too_large")
        return CallingGrant.model_validate_json(data)
    except (OSError, ValueError) as exc:
        raise CallingContractError("calling_policy_unavailable_or_invalid") from exc


def operation_identity(principal: CallPrincipal, key: str) -> UUID:
    # A key cannot create a different request when refreshed access tokens are used.
    return uuid5(CALL_NAMESPACE, json.dumps(
        [CLIENT_ID, principal.tenant_id, principal.subject, key], separators=(",", ":"),
    ))


def principal_payload(principal: CallPrincipal) -> dict:
    return principal.model_dump(mode="json")
