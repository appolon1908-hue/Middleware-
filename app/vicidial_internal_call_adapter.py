"""Restricted Middleware client for the Server B internal-call executor."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import ssl
import stat
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx
from .calling_contract import (
    CAPABILITY, CLIENT_ID, HANGUP, ORIGINATE, TARGET, CallLifecycleEvidence,
    CallPrincipal, CallingContractError, OriginateRequest, load_grant,
)
from .config import ConfigurationError, Settings
from .temporal_workflows import ActivityResult, CommandExecutionRequest


class VicidialInternalCallError(RuntimeError):
    """Safe deterministic failure; never includes response bodies or secrets."""


class VicidialInternalCallUnknown(VicidialInternalCallError):
    """The mutation may have reached Server B and must only be read back."""


class VicidialInternalCallAdapter:
    ORIGINATE_PATH = "/v1/calls/internal/originate"

    def __init__(self, settings: Settings, env: Mapping[str, str] | None = None,
                 client: httpx.AsyncClient | None = None) -> None:
        self.settings = settings
        self.env = os.environ if env is None else env
        self._client = client

    def _required(self, name: str) -> str:
        value = self.env.get(name, "").strip()
        if not value:
            raise ConfigurationError(f"{name} is required for bounded VICIdial calls")
        return value

    def _origin(self) -> str:
        value = self._required("VICIDIAL_INTERNAL_CALL_BASE_URL").rstrip("/")
        parsed = urlsplit(value)
        if (parsed.scheme != "https" or not parsed.hostname or parsed.username
                or parsed.password or parsed.query or parsed.fragment or parsed.path):
            raise ConfigurationError("VICIDIAL internal-call URL must be an HTTPS origin")
        if parsed.hostname != self._required("VICIDIAL_INTERNAL_CALL_EXPECTED_HOST"):
            raise ConfigurationError("VICIDIAL internal-call host is not the pinned private ingress")
        return value

    def _secret(self) -> bytes:
        path = Path(self._required("VICIDIAL_INTERNAL_CALL_HMAC_FILE"))
        if not path.is_absolute() or path.is_symlink():
            raise ConfigurationError("VICIDIAL HMAC secret path is unsafe")
        try:
            descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
            with os.fdopen(descriptor, "rb") as stream:
                metadata = os.fstat(stream.fileno())
                value = stream.read(4097).strip()
        except OSError as exc:
            raise ConfigurationError("VICIDIAL HMAC secret is unavailable") from exc
        if (not stat.S_ISREG(metadata.st_mode) or metadata.st_mode & 0o077
                or len(value) < 32 or len(value) > 4096):
            raise ConfigurationError("VICIDIAL HMAC secret permissions or length are invalid")
        return value

    def _headers(self, method: str, path: str, body: bytes, scope: str,
                 idempotency_key: str = "") -> dict[str, str]:
        identity = self._required("VICIDIAL_INTERNAL_CALL_SERVICE_IDENTITY")
        timestamp = str(int(time.time()))
        nonce = secrets.token_urlsafe(24)
        scopes = " ".join(sorted({scope}))
        canonical = "\n".join((
            "v2", method.upper(), path, identity, scopes, timestamp, nonce,
            idempotency_key, hashlib.sha256(body).hexdigest(),
        ))
        signature = hmac.new(self._secret(), canonical.encode(), hashlib.sha256).hexdigest()
        headers = {
            "Accept": "application/json", "X-Service-Identity": identity,
            "X-Service-Scopes": scopes, "X-Request-Timestamp": timestamp,
            "X-Request-Nonce": nonce, "X-Request-Signature": signature,
            "X-Signature-Version": "v2",
        }
        if body:
            headers["Content-Type"] = "application/json"
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        return headers

    def _client_or_create(self) -> httpx.AsyncClient:
        if self._client is not None:
            return self._client
        ca = self._required("VICIDIAL_INTERNAL_CALL_CA_FILE")
        cert = self._required("VICIDIAL_INTERNAL_CALL_MTLS_CERT_FILE")
        key = self._required("VICIDIAL_INTERNAL_CALL_MTLS_KEY_FILE")
        context = ssl.create_default_context(cafile=ca)
        context.load_cert_chain(cert, key)
        self._client = httpx.AsyncClient(
            base_url=self._origin(), verify=context, trust_env=False,
            follow_redirects=False, timeout=httpx.Timeout(8, connect=3),
        )
        return self._client

    async def _request(self, method: str, path: str, *, document: dict | None = None,
                       scope: str, idempotency_key: str = "") -> dict[str, Any]:
        body = (json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
                if document is not None else b"")
        request = self._client_or_create().build_request(
            method, self._origin() + path, content=body,
            headers=self._headers(method, path, body, scope, idempotency_key),
        )
        try:
            response = await self._client_or_create().send(request, stream=True)
            if int(response.headers.get("content-length", "0") or 0) > 65_536:
                raise VicidialInternalCallError("Server B response exceeded the bounded size")
            chunks = bytearray()
            async for chunk in response.aiter_bytes():
                chunks.extend(chunk)
                if len(chunks) > 65_536:
                    raise VicidialInternalCallError(
                        "Server B response exceeded the bounded size"
                    )
            raw = bytes(chunks)
        except (httpx.TimeoutException, httpx.TransportError):
            raise VicidialInternalCallUnknown(
                "Server B mutation/readback outcome is unknown"
            ) from None
        finally:
            if 'response' in locals():
                await response.aclose()
        if len(raw) > 65_536:
            raise VicidialInternalCallError("Server B response exceeded the bounded size")
        if response.status_code >= 500:
            raise VicidialInternalCallUnknown("Server B did not return a conclusive outcome")
        if response.status_code >= 400:
            raise VicidialInternalCallError(f"Server B rejected the bounded request ({response.status_code})")
        try:
            value = json.loads(raw)
        except (ValueError, UnicodeError) as exc:
            raise VicidialInternalCallUnknown("Server B response was malformed") from exc
        if not isinstance(value, dict):
            raise VicidialInternalCallUnknown("Server B response was malformed")
        return value

    def _originate(self, request: CommandExecutionRequest) -> tuple[CallPrincipal, OriginateRequest, dict]:
        if (request.target, request.command_type, request.command_version,
                request.capability, request.authenticated_client_id) != (
                TARGET, ORIGINATE, "1.0", CAPABILITY, CLIENT_ID):
            raise VicidialInternalCallError("command provenance is outside bounded calling")
        if set(request.payload) != {"actor", "originate", "authorization_reference", "policy_sha256"}:
            raise VicidialInternalCallError("calling payload shape is not canonical")
        try:
            principal = CallPrincipal.model_validate(request.payload["actor"])
            body = OriginateRequest.model_validate(request.payload["originate"] | {
                "idempotency_key": request.idempotency_key,
            })
        except (KeyError, TypeError, ValueError):
            raise VicidialInternalCallError("calling identity or request is invalid") from None
        grant = load_grant(self.env)
        if grant is None or grant.digest() != request.payload["policy_sha256"]:
            raise VicidialInternalCallError("dispatch-time calling policy is unavailable or changed")
        try:
            grant.authorize(principal, body, source_sha=self.settings.source_sha)
        except CallingContractError as exc:
            raise VicidialInternalCallError(
                "dispatch-time calling policy rejected the command"
            ) from exc
        if (principal.extension != "6901" or principal.campaign_id != "TEST_SYN"
                or body.destination != "internal:TEST_ECHO"):
            raise VicidialInternalCallError("identity or route is outside Appolon internal calling")
        return principal, body, {
            "operation_id": request.command_id, "correlation_id": request.correlation_id,
            "tenant_id": principal.tenant_id, "subject": principal.subject,
            "employee_id": principal.employee_id, "username": "appolon",
            "extension": "6901", "campaign": "TEST_SYN",
            "destination": "internal:TEST_ECHO", "internal_only": True,
            "external_dialing": False, "recording_requested": False,
            "authorization_reference": grant.authorization_reference,
        }

    async def execute(self, request: CommandExecutionRequest) -> ActivityResult:
        if request.command_type == ORIGINATE:
            _, _, document = self._originate(request)
            value = await self._request("POST", self.ORIGINATE_PATH, document=document,
                                        scope="telephony:internal-call",
                                        idempotency_key=request.command_id)
            if value.get("operation_id") != request.command_id or value.get("status") not in {"accepted", "dispatch_unknown"}:
                raise VicidialInternalCallUnknown("Server B originate acknowledgement was invalid")
            return ActivityResult(value["status"], "bounded originate submitted",
                                  value.get("asterisk_uniqueid"))
        if request.command_type == HANGUP:
            if request.target != TARGET or request.capability != CAPABILITY or request.authenticated_client_id != CLIENT_ID:
                raise VicidialInternalCallError("hangup provenance is outside bounded calling")
            original = str(request.payload.get("origin_operation_id", ""))
            if not original or set(request.payload) != {"actor", "originate", "origin_operation_id", "call_id", "authorization_reference", "policy_sha256", "reason"}:
                raise VicidialInternalCallError("hangup payload shape is not canonical")
            value = await self._request("POST", f"/v1/calls/internal/{original}/hangup",
                                        document={}, scope="telephony:internal-call-hangup",
                                        idempotency_key=original + ":hangup")
            return ActivityResult("accepted", "bounded same-call hangup submitted",
                                  str(value.get("asterisk_uniqueid") or request.payload["call_id"]))
        raise VicidialInternalCallError("unsupported bounded calling command")

    async def readback(self, request: CommandExecutionRequest) -> ActivityResult:
        original = (request.command_id if request.command_type == ORIGINATE
                    else str(request.payload.get("origin_operation_id", "")))
        value = await self._request("GET", f"/v1/calls/internal/{original}",
                                    scope="telephony:internal-call-read")
        try:
            evidence = CallLifecycleEvidence.model_validate(value)
            actor = CallPrincipal.model_validate(request.payload["actor"])
        except (KeyError, TypeError, ValueError):
            raise VicidialInternalCallError("Server B evidence contract is invalid") from None
        if (evidence.operation_id != original or evidence.correlation_id != request.correlation_id
                or evidence.tenant_id != request.tenant_id or evidence.subject != actor.subject
                or evidence.employee_id != actor.employee_id or evidence.extension != actor.extension
                or evidence.campaign != actor.campaign_id or evidence.internal_only is not True
                or evidence.external_dialing is not False):
            raise VicidialInternalCallError("Server B evidence binding mismatch")
        terminal = evidence.terminal and evidence.call_state in {
            "completed", "failed", "missed", "rejected", "cancelled", "transferred",
        }
        if terminal and (not evidence.ended_at or not evidence.linkedid
                         or evidence.duration_seconds is None or not evidence.evidence):
            raise VicidialInternalCallError("Server B terminal evidence is incomplete")
        return ActivityResult("matched" if terminal else "mismatch",
                              "terminal call evidence verified" if terminal else "call remains nonterminal or unknown",
                              evidence.asterisk_uniqueid,
                              evidence.model_dump(mode="json"))
