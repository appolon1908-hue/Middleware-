from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Any
from uuid import uuid4

import jwt
from fastapi.testclient import TestClient

from app.commands import CommandPolicy, CommandPolicyRegistry, CommandService, MemoryCommandStore
from app.communications import CommunicationsService, MemoryCommunicationsStore
from app.main import create_app
from app.replay import MemoryReplayGuard
from app.runtime import Runtime
from app.security import AuthenticationError, AuthorizationError
from app.storage import MemoryInboxStore


def _token(client_id: str, scopes: list[str], *, tenant_id: str = "tenant-1") -> str:
    return jwt.encode(
        {
            "azp": client_id,
            "scope": " ".join(scopes),
            "aud": "middleware-api",
            "tenant_id": tenant_id,
            "sub": "user-123",
            "iss": "https://auth.codestra.co/realms/codestra",
            "iat": 1_700_000_000,
            "exp": 1_700_000_300,
            "jti": str(uuid4()),
        },
        "test-only-key",
        algorithm="HS256",
    )


class ProductTokenVerifier:
    async def verify(
        self,
        authorization: str,
        *,
        expected_client_id: str,
        required_scope: str,
    ) -> dict[str, Any]:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token:
            raise AuthenticationError("Authorization must be a Bearer token")
        try:
            claims = jwt.decode(
                token,
                options={
                    "verify_signature": False,
                    "verify_exp": False,
                    "verify_aud": False,
                    "verify_iss": False,
                },
            )
        except Exception as exc:
            raise AuthenticationError("invalid bearer token") from exc
        if claims.get("azp") != expected_client_id:
            raise AuthorizationError("token azp does not match producer")
        scopes = set(str(claims.get("scope") or "").split())
        if required_scope not in scopes:
            raise AuthorizationError("required scope is missing")
        return claims

    async def ready(self) -> bool:
        return True


def _runtime(test_settings) -> Runtime:
    commands = CommandService(
        MemoryCommandStore(),
        CommandPolicyRegistry(
            (
                CommandPolicy(
                    prefix="email.",
                    target="klyrow-email",
                    capability="EMAIL_DELIVERY",
                    readback_required=True,
                ),
            ),
            {"EMAIL_DELIVERY": True},
        ),
    )
    store = MemoryCommunicationsStore()
    store.verified_senders.add(("tenant-1", "sender@codestra.co"))
    store.verified_domains.add(("tenant-1", "codestra.co"))
    return Runtime(
        settings=test_settings,
        inbox=MemoryInboxStore(),
        replay=MemoryReplayGuard(),
        tokens=ProductTokenVerifier(),
        commands=commands,
        communications=CommunicationsService(store=store, commands=commands),
    )


def _headers(*, scope: str = "klyrow.middleware.command.write", tenant: str = "tenant-1", key: str = "email-key-1") -> dict[str, str]:
    return {
        "Authorization": "Bearer " + _token("klyrow", [scope], tenant_id=tenant),
        "X-Tenant-ID": tenant,
        "X-Correlation-ID": "email-correlation-1",
        "Idempotency-Key": key,
    }


def _message(**updates: Any) -> dict[str, Any]:
    value: dict[str, Any] = {
        "channel": "email",
        "from": "sender@codestra.co",
        "to": ["person@codestra.co"],
        "content": {"subject": "Hello", "text": "Safe test message"},
        "metadata": {"consent": "granted"},
    }
    value.update(updates)
    return value


def _sign(event: dict[str, Any], path: str = "/api/v1/klyrow/events") -> dict[str, str]:
    body = json.dumps(event, separators=(",", ":"), sort_keys=True).encode()
    timestamp = str(int(time.time()))
    canonical = "\n".join(
        (
            "v1",
            "POST",
            path,
            timestamp,
            event["event_id"],
            "klyrow-gateway",
            hashlib.sha256(body).hexdigest(),
        )
    ).encode()
    signature = hmac.new(
        b"test-secret-value-that-is-at-least-thirty-two-bytes",
        canonical,
        hashlib.sha256,
    ).hexdigest()
    return {
        "Authorization": "Bearer " + _token("klyrow-gateway", ["email.events.publish"]),
        "Content-Type": "application/json",
        "Idempotency-Key": event["event_id"],
        "X-Codestra-Event-Id": event["event_id"],
        "X-Codestra-Event-Type": event["event_type"],
        "X-Codestra-Source": "klyrow-gateway",
        "X-Codestra-Tenant-Id": event["tenant_id"],
        "X-Codestra-Timestamp": timestamp,
        "X-Codestra-Signature": "sha256=" + signature,
        "X-Correlation-Id": event["correlation_id"],
    }


def test_email_message_lifecycle_idempotency_and_timeline(test_settings) -> None:
    app = create_app(settings=test_settings, runtime=_runtime(test_settings))
    with TestClient(app) as client:
        first = client.post(
            "/v1/communications/messages",
            json=_message(),
            headers=_headers(),
        )
        assert first.status_code == 202, first.text
        message = first.json()
        assert message["status"] == "queued"
        replay = client.post(
            "/v1/communications/messages",
            json=_message(),
            headers=_headers(),
        )
        assert replay.status_code == 200
        assert replay.json()["messageId"] == message["messageId"]
        conflict = client.post(
            "/v1/communications/messages",
            json=_message(content={"subject": "Changed", "text": "Changed"}),
            headers=_headers(),
        )
        assert conflict.status_code == 409
        fetched = client.get(
            f"/v1/communications/messages/{message['messageId']}",
            headers=_headers(scope="klyrow.middleware.status.read"),
        )
        assert fetched.status_code == 200
        timeline = client.get(
            f"/v1/communications/messages/{message['messageId']}/events",
            headers=_headers(scope="klyrow.middleware.status.read"),
        )
        assert [item["status"] for item in timeline.json()["items"]] == ["accepted", "queued"]


def test_email_suppression_and_consent_stop_before_provider_command(test_settings) -> None:
    runtime = _runtime(test_settings)
    assert runtime.communications is not None
    runtime.communications.store.suppressions.add(("tenant-1", "blocked@codestra.co"))
    app = create_app(settings=test_settings, runtime=runtime)
    with TestClient(app) as client:
        suppressed = client.post(
            "/v1/communications/messages",
            json=_message(to=["blocked@codestra.co"]),
            headers=_headers(key="suppressed-key"),
        )
        assert suppressed.status_code == 202
        assert suppressed.json()["status"] == "suppressed"
        denied = client.post(
            "/v1/communications/messages",
            json=_message(to=["needs-consent@codestra.co"], metadata={"consent": "denied"}),
            headers=_headers(key="consent-key"),
        )
        assert denied.status_code == 202
        assert denied.json()["failureCode"] == "consent_required"


def test_email_scope_tenant_and_cancellation_guards(test_settings) -> None:
    app = create_app(settings=test_settings, runtime=_runtime(test_settings))
    with TestClient(app) as client:
        wrong_scope = client.post(
            "/v1/communications/messages",
            json=_message(),
            headers=_headers(scope="klyrow.middleware.status.read", key="wrong-scope"),
        )
        assert wrong_scope.status_code == 403
        created = client.post(
            "/v1/communications/messages",
            json=_message(),
            headers=_headers(key="cancel-key"),
        ).json()
        wrong_tenant = client.get(
            f"/v1/communications/messages/{created['messageId']}",
            headers=_headers(scope="klyrow.middleware.status.read", tenant="tenant-2"),
        )
        assert wrong_tenant.status_code == 404
        cancelled = client.post(
            f"/v1/communications/messages/{created['messageId']}/cancel",
            headers=_headers(scope="klyrow.middleware.status.read", key="cancel-key-2"),
        )
        assert cancelled.status_code == 202
        assert cancelled.json()["status"] == "cancelled"
        again = client.post(
            f"/v1/communications/messages/{created['messageId']}/cancel",
            headers=_headers(scope="klyrow.middleware.status.read", key="cancel-key-3"),
        )
        assert again.status_code == 409


def test_klyrow_signed_event_updates_canonical_read_model(test_settings) -> None:
    runtime = _runtime(test_settings)
    app = create_app(settings=test_settings, runtime=runtime)
    with TestClient(app) as client:
        created = client.post(
            "/v1/communications/messages",
            json=_message(),
            headers=_headers(key="callback-key"),
        ).json()
        event_id = str(uuid4())
        event = {
            "event_id": event_id,
            "event_type": "codestra.email.message.delivered",
            "event_version": "1.0",
            "occurred_at": "2026-08-29T12:00:00Z",
            "received_at": "2026-08-29T12:00:01Z",
            "source": "klyrow-gateway",
            "tenant_id": "tenant-1",
            "correlation_id": "email-correlation-1",
            "causation_id": created["messageId"],
            "idempotency_key": event_id,
            "payload": {
                "messageId": created["messageId"],
                "status": "delivered",
                "providerReference": "postal-message-1",
            },
            "metadata": {},
        }
        response = client.post(
            "/api/v1/klyrow/events",
            content=json.dumps(event, separators=(",", ":"), sort_keys=True),
            headers=_sign(event),
        )
        assert response.status_code == 202, response.text
        fetched = client.get(
            f"/v1/communications/messages/{created['messageId']}",
            headers=_headers(scope="klyrow.middleware.status.read"),
        )
        assert fetched.json()["status"] == "delivered"
        assert fetched.json()["providerReference"] == "postal-message-1"
