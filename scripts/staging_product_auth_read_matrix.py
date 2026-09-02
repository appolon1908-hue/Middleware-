#!/usr/bin/env python3
"""Read-only Keycloak -> Kong -> Middleware product authentication matrix.

This harness never submits a command. It obtains short-lived service tokens and
uses only GET /v1/operations/{random_uuid} probes, so a successful auth path ends
at a not-found read rather than a durable command or provider effect.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import ssl
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
CALLER_POLICY = ROOT / "config" / "control-plane-callers.v1.json"
CANONICAL_ISSUER = "https://auth.codestra.co/realms/codestra"
CANONICAL_AUDIENCE = "middleware-api"
EXPECTED_CLIENTS = (
    "moneybee-backend",
    "breero-backend",
    "larim-a-backend",
    "transportation-backend",
    "beyvra-backend",
    "social-codestra",
)


class MatrixError(RuntimeError):
    pass


@dataclass(frozen=True)
class ProbeResult:
    name: str
    expected_status: int
    actual_status: int
    error_code: str | None

    @property
    def passed(self) -> bool:
        return self.actual_status == self.expected_status

    def as_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "expected_status": self.expected_status,
            "actual_status": self.actual_status,
            "error_code": self.error_code,
            "passed": self.passed,
        }


def _require_https(value: str, label: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        raise MatrixError(f"{label} must be an HTTPS URL without embedded credentials")
    return value.rstrip("/")


def _secret_env(client_id: str) -> str:
    return "AUTH_MATRIX_SECRET_" + client_id.upper().replace("-", "_")


def _load_policy() -> dict[str, dict[str, Any]]:
    try:
        value = json.loads(CALLER_POLICY.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MatrixError(f"cannot load caller policy: {exc}") from exc
    if value.get("issuer") != CANONICAL_ISSUER or value.get("audience") != CANONICAL_AUDIENCE:
        raise MatrixError("caller policy issuer/audience drift")
    if value.get("token_exchange") is not False or value.get("original_bearer_required") is not True:
        raise MatrixError("caller policy must preserve original bearer with token exchange disabled")
    callers = value.get("callers")
    if not isinstance(callers, dict):
        raise MatrixError("caller policy has no caller registry")
    missing = [client_id for client_id in EXPECTED_CLIENTS if client_id not in callers]
    if missing:
        raise MatrixError("caller policy is missing product client(s): " + ", ".join(missing))
    return callers


def _selected_clients() -> tuple[str, ...]:
    raw = os.environ.get("AUTH_MATRIX_CLIENTS", ",".join(EXPECTED_CLIENTS))
    selected = tuple(item.strip() for item in raw.split(",") if item.strip())
    if not selected:
        raise MatrixError("AUTH_MATRIX_CLIENTS selected no clients")
    unknown = [item for item in selected if item not in EXPECTED_CLIENTS]
    if unknown:
        raise MatrixError("unsupported AUTH_MATRIX_CLIENTS value(s): " + ", ".join(unknown))
    if len(set(selected)) != len(selected):
        raise MatrixError("AUTH_MATRIX_CLIENTS contains duplicates")
    return selected


def _decode_segment(segment: str) -> dict[str, Any]:
    try:
        padding = "=" * ((4 - len(segment) % 4) % 4)
        raw = base64.urlsafe_b64decode(segment + padding)
        value = json.loads(raw)
    except (ValueError, json.JSONDecodeError) as exc:
        raise MatrixError("access token payload is not valid JWT JSON") from exc
    if not isinstance(value, dict):
        raise MatrixError("access token payload is not an object")
    return value


def decode_unverified_claims(token: str) -> dict[str, Any]:
    parts = token.split(".")
    if len(parts) != 3 or not all(parts):
        raise MatrixError("token endpoint did not return a JWT access token")
    return _decode_segment(parts[1])


def _audience_contains(claim: Any, expected: str) -> bool:
    if isinstance(claim, str):
        return claim == expected
    if isinstance(claim, list):
        return expected in claim
    return False


def validate_claim_shape(
    claims: dict[str, Any],
    *,
    client_id: str,
    required_scope: str,
    now: int | None = None,
) -> str:
    current = int(time.time()) if now is None else now
    if claims.get("iss") != CANONICAL_ISSUER:
        raise MatrixError(f"{client_id}: issuer drift")
    if not _audience_contains(claims.get("aud"), CANONICAL_AUDIENCE):
        raise MatrixError(f"{client_id}: middleware-api audience missing")
    if claims.get("azp") != client_id:
        raise MatrixError(f"{client_id}: azp mismatch")
    iat = claims.get("iat")
    exp = claims.get("exp")
    if not isinstance(iat, int) or not isinstance(exp, int) or exp <= iat or exp - iat > 300:
        raise MatrixError(f"{client_id}: access-token lifetime exceeds reviewed policy")
    if exp <= current:
        raise MatrixError(f"{client_id}: token is already expired")
    scopes = set(str(claims.get("scope", "")).split())
    if required_scope not in scopes:
        raise MatrixError(f"{client_id}: required status scope missing")
    tenant_id = claims.get("tenant_id")
    if not isinstance(tenant_id, str) or not tenant_id.strip() or tenant_id.strip() == "*":
        raise MatrixError(f"{client_id}: authoritative tenant_id claim is missing or unsafe")
    return tenant_id.strip()


def _http_json(
    request: Request,
    *,
    timeout: float,
    context: ssl.SSLContext,
    allow_http_error: bool = False,
) -> tuple[int, dict[str, Any]]:
    try:
        with urlopen(request, timeout=timeout, context=context) as response:
            raw = response.read(131072)
            status = response.status
    except HTTPError as exc:
        if not allow_http_error:
            raise MatrixError(f"HTTP request failed with status {exc.code}") from exc
        raw = exc.read(131072)
        status = exc.code
    except (URLError, TimeoutError, OSError) as exc:
        raise MatrixError(f"HTTPS request failed: {type(exc).__name__}") from exc
    if not raw:
        return status, {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return status, {}
    return status, value if isinstance(value, dict) else {}


def acquire_token(
    *,
    token_endpoint: str,
    client_id: str,
    client_secret: str,
    timeout: float,
    context: ssl.SSLContext,
) -> str:
    payload = urlencode(
        {
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
        }
    ).encode("ascii")
    request = Request(
        token_endpoint,
        data=payload,
        method="POST",
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "User-Agent": "codestra-staging-auth-matrix/1.0",
        },
    )
    status, body = _http_json(request, timeout=timeout, context=context)
    if status != 200:
        raise MatrixError(f"{client_id}: token endpoint returned {status}")
    token = body.get("access_token")
    if not isinstance(token, str) or not token:
        raise MatrixError(f"{client_id}: token endpoint response has no access_token")
    return token


def _error_code(body: dict[str, Any]) -> str | None:
    error = body.get("error")
    if isinstance(error, dict) and isinstance(error.get("code"), str):
        return error["code"]
    if isinstance(error, str):
        return error
    return None


def operation_probe(
    *,
    gateway_base_url: str,
    token: str | None,
    tenant_id: str | None,
    operation_id: uuid.UUID,
    timeout: float,
    context: ssl.SSLContext,
    name: str,
    expected_status: int,
) -> ProbeResult:
    headers = {
        "Accept": "application/json",
        "User-Agent": "codestra-staging-auth-matrix/1.0",
    }
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    if tenant_id is not None:
        headers["X-Tenant-ID"] = tenant_id
    request = Request(
        f"{gateway_base_url}/v1/operations/{operation_id}",
        method="GET",
        headers=headers,
    )
    status, body = _http_json(
        request,
        timeout=timeout,
        context=context,
        allow_http_error=True,
    )
    return ProbeResult(
        name=name,
        expected_status=expected_status,
        actual_status=status,
        error_code=_error_code(body),
    )


def tamper_signature(token: str) -> str:
    parts = token.split(".")
    if len(parts) != 3 or not parts[2]:
        raise MatrixError("cannot tamper non-JWT token")
    replacement = "A" if parts[2][0] != "A" else "B"
    parts[2] = replacement + parts[2][1:]
    return ".".join(parts)


def _tenant_fingerprint(tenant_id: str) -> str:
    return hashlib.sha256(tenant_id.encode("utf-8")).hexdigest()


def main() -> int:
    os.umask(0o077)
    if os.environ.get("AUTH_MATRIX_ENVIRONMENT") != "staging":
        raise SystemExit("AUTH_MATRIX_ENVIRONMENT=staging is required")
    try:
        gateway_base_url = _require_https(
            os.environ.get("AUTH_MATRIX_GATEWAY_BASE_URL", ""),
            "AUTH_MATRIX_GATEWAY_BASE_URL",
        )
        token_endpoint = _require_https(
            os.environ.get("AUTH_MATRIX_TOKEN_ENDPOINT", ""),
            "AUTH_MATRIX_TOKEN_ENDPOINT",
        )
        timeout = float(os.environ.get("AUTH_MATRIX_TIMEOUT_SECONDS", "10"))
        if not 0 < timeout <= 30:
            raise MatrixError("AUTH_MATRIX_TIMEOUT_SECONDS must be >0 and <=30")
        callers = _load_policy()
        selected = _selected_clients()
    except (MatrixError, ValueError) as exc:
        print(json.dumps({"status": "FAIL", "phase": "configuration", "error": str(exc)}))
        return 2

    output_dir = Path(
        os.environ.get(
            "AUTH_MATRIX_EVIDENCE_DIR",
            "/tmp/codestra-staging-auth-matrix-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ"),
        )
    )
    output_dir.mkdir(parents=True, exist_ok=False, mode=0o700)
    context = ssl.create_default_context()
    operation_id = uuid.uuid4()
    evidence: dict[str, Any] = {
        "schema_version": "1.0",
        "environment": "staging",
        "started_at": datetime.now(UTC).isoformat(),
        "gateway_origin": gateway_base_url,
        "token_origin": f"{urlparse(token_endpoint).scheme}://{urlparse(token_endpoint).netloc}",
        "operation_id": str(operation_id),
        "method": "GET",
        "route": "/v1/operations/{command_id}",
        "command_posts": 0,
        "provider_calls": 0,
        "clients": [],
    }

    all_passed = True
    try:
        missing = operation_probe(
            gateway_base_url=gateway_base_url,
            token=None,
            tenant_id=None,
            operation_id=operation_id,
            timeout=timeout,
            context=context,
            name="missing_bearer_denied",
            expected_status=401,
        )
        evidence["missing_bearer_probe"] = missing.as_dict()
        all_passed &= missing.passed

        for client_id in selected:
            secret_name = _secret_env(client_id)
            secret = os.environ.get(secret_name)
            if not secret:
                raise MatrixError(f"{client_id}: required secret environment {secret_name} is missing")
            policy = callers[client_id]
            status_scope = policy.get("status_scope")
            if not isinstance(status_scope, str) or not status_scope:
                raise MatrixError(f"{client_id}: status scope missing from source policy")

            token = acquire_token(
                token_endpoint=token_endpoint,
                client_id=client_id,
                client_secret=secret,
                timeout=timeout,
                context=context,
            )
            claims = decode_unverified_claims(token)
            tenant_id = validate_claim_shape(
                claims,
                client_id=client_id,
                required_scope=status_scope,
            )
            valid = operation_probe(
                gateway_base_url=gateway_base_url,
                token=token,
                tenant_id=tenant_id,
                operation_id=operation_id,
                timeout=timeout,
                context=context,
                name="valid_original_bearer_reaches_middleware_read",
                expected_status=404,
            )
            tampered = operation_probe(
                gateway_base_url=gateway_base_url,
                token=tamper_signature(token),
                tenant_id=tenant_id,
                operation_id=operation_id,
                timeout=timeout,
                context=context,
                name="tampered_signature_denied",
                expected_status=401,
            )
            wrong_tenant = tenant_id + "-auth-matrix-negative"
            tenant_denied = operation_probe(
                gateway_base_url=gateway_base_url,
                token=token,
                tenant_id=wrong_tenant,
                operation_id=operation_id,
                timeout=timeout,
                context=context,
                name="tenant_mismatch_denied",
                expected_status=403,
            )
            record = {
                "client_id": client_id,
                "required_status_scope": status_scope,
                "issuer": claims.get("iss"),
                "audience_verified_locally": _audience_contains(claims.get("aud"), CANONICAL_AUDIENCE),
                "azp": claims.get("azp"),
                "token_lifetime_seconds": int(claims["exp"]) - int(claims["iat"]),
                "tenant_sha256": _tenant_fingerprint(tenant_id),
                "probes": [valid.as_dict(), tampered.as_dict(), tenant_denied.as_dict()],
            }
            client_passed = all(item["passed"] for item in record["probes"])
            record["passed"] = client_passed
            evidence["clients"].append(record)
            all_passed &= client_passed
            token = ""  # discard the live bearer before the next iteration

    except MatrixError as exc:
        evidence["runtime_error"] = str(exc)
        all_passed = False

    evidence["completed_at"] = datetime.now(UTC).isoformat()
    evidence["status"] = "PASS" if all_passed else "FAIL"
    evidence["tokens_recorded"] = False
    evidence["secrets_recorded"] = False
    evidence_path = output_dir / "auth-matrix-evidence.json"
    evidence_path.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"AUTH_MATRIX_STATUS={evidence['status']}")
    print(f"AUTH_MATRIX_EVIDENCE={evidence_path}")
    print("AUTH_MATRIX_COMMAND_POSTS=0")
    print("AUTH_MATRIX_PROVIDER_CALLS=0")
    print("AUTH_MATRIX_TOKENS_RECORDED=NO")
    return 0 if all_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
