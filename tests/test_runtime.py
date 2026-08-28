from __future__ import annotations

from dataclasses import replace

from fastapi.testclient import TestClient

from app.contracts import ROUTE_BY_PATH, WEBHOOK_ROUTES
from app.main import create_app
from app.replay import MemoryReplayGuard
from app.runtime import Runtime
from app.storage import MemoryInboxStore

from .conftest import FakeTokenVerifier, make_event, signed_headers


def test_all_contract_routes_are_registered(test_settings, runtime) -> None:
    app = create_app(settings=test_settings, runtime=runtime)
    registered = {
        route.path
        for route in app.routes
        if getattr(route, "methods", None)
        and "POST" in route.methods
        and route.path.startswith("/api/v1/")
    }
    assert registered == {item.path for item in WEBHOOK_ROUTES}


def test_accept_and_idempotent_duplicate(test_settings, runtime) -> None:
    path = "/api/v1/odoo/events"
    route = ROUTE_BY_PATH[path]
    event = make_event(
        producer=route.producer_client_id,
        event_type=sorted(route.event_types)[0],
    )
    body, headers = signed_headers(
        path=path,
        producer=route.producer_client_id,
        scope=route.required_scope,
        event=event,
    )
    app = create_app(settings=test_settings, runtime=runtime)
    with TestClient(app) as client:
        first = client.post(path, content=body, headers=headers)
        assert first.status_code == 202, first.text
        assert first.json()["duplicate"] is False

        second = client.post(path, content=body, headers=headers)
        assert second.status_code == 200, second.text
        assert second.json()["duplicate"] is True


def test_semantically_identical_reformatted_retry_is_duplicate(test_settings, runtime) -> None:
    path = "/api/v1/odoo/events"
    route = ROUTE_BY_PATH[path]
    event = make_event(
        producer=route.producer_client_id,
        event_type=sorted(route.event_types)[0],
    )
    body, headers = signed_headers(
        path=path,
        producer=route.producer_client_id,
        scope=route.required_scope,
        event=event,
    )
    app = create_app(settings=test_settings, runtime=runtime)
    with TestClient(app) as client:
        assert client.post(path, content=body, headers=headers).status_code == 202
        # A producer retry may serialize equivalent JSON differently. Re-sign the new raw body.
        import hashlib
        import hmac
        import json
        import time
        from .conftest import SECRET

        pretty = json.dumps(event, indent=2, sort_keys=False).encode()
        timestamp = str(int(time.time()))
        body_sha = hashlib.sha256(pretty).hexdigest()
        canonical = "\n".join(("v1", "POST", path, timestamp, event["event_id"], route.producer_client_id, body_sha)).encode()
        signature = hmac.new(SECRET, canonical, hashlib.sha256).hexdigest()
        retry_headers = dict(headers)
        retry_headers["X-Codestra-Timestamp"] = timestamp
        retry_headers["X-Codestra-Signature"] = f"sha256={signature}"
        response = client.post(path, content=pretty, headers=retry_headers)
        assert response.status_code == 200, response.text
        assert response.json()["duplicate"] is True


def test_same_event_id_with_changed_payload_conflicts(test_settings, runtime) -> None:
    path = "/api/v1/n8n/results"
    route = ROUTE_BY_PATH[path]
    event = make_event(
        producer=route.producer_client_id,
        event_type=sorted(route.event_types)[0],
    )
    body, headers = signed_headers(
        path=path,
        producer=route.producer_client_id,
        scope=route.required_scope,
        event=event,
    )
    app = create_app(settings=test_settings, runtime=runtime)
    with TestClient(app) as client:
        assert client.post(path, content=body, headers=headers).status_code == 202

        changed = {**event, "payload": {"ok": False}}
        changed_body, changed_headers = signed_headers(
            path=path,
            producer=route.producer_client_id,
            scope=route.required_scope,
            event=changed,
        )
        response = client.post(path, content=changed_body, headers=changed_headers)
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "idempotency_conflict"


def test_invalid_signature_is_rejected_with_canonical_error(test_settings, runtime) -> None:
    path = "/api/v1/vicidial/events"
    route = ROUTE_BY_PATH[path]
    event = make_event(
        producer=route.producer_client_id,
        event_type=sorted(route.event_types)[0],
    )
    body, headers = signed_headers(
        path=path,
        producer=route.producer_client_id,
        scope=route.required_scope,
        event=event,
    )
    headers["X-Codestra-Signature"] = "sha256=" + ("0" * 64)
    app = create_app(settings=test_settings, runtime=runtime)
    with TestClient(app) as client:
        response = client.post(path, content=body, headers=headers)
        assert response.status_code == 401
        error = response.json()["error"]
        assert error["code"] == "webhook_signature_invalid"
        assert error["correlation_id"] == event["correlation_id"]
        assert error["retryable"] is False
        assert error["details"] == {}


def test_body_and_header_tenant_must_match(test_settings, runtime) -> None:
    path = "/api/v1/telnexa/events"
    route = ROUTE_BY_PATH[path]
    event = make_event(
        producer=route.producer_client_id,
        event_type=sorted(route.event_types)[0],
    )
    body, headers = signed_headers(
        path=path,
        producer=route.producer_client_id,
        scope=route.required_scope,
        event=event,
    )
    headers["X-Codestra-Tenant-Id"] = "other-tenant"
    app = create_app(settings=test_settings, runtime=runtime)
    with TestClient(app) as client:
        response = client.post(path, content=body, headers=headers)
        assert response.status_code == 400


def test_cross_tenant_token_is_rejected(test_settings) -> None:
    class WrongTenantVerifier(FakeTokenVerifier):
        async def verify(self, authorization, *, expected_client_id, required_scope):
            claims = await super().verify(
                authorization,
                expected_client_id=expected_client_id,
                required_scope=required_scope,
            )
            claims["tenant_id"] = "different-tenant"
            return claims

    runtime = Runtime(
        settings=test_settings,
        inbox=MemoryInboxStore(),
        replay=MemoryReplayGuard(),
        tokens=WrongTenantVerifier(),
    )
    path = "/api/v1/klyrow/events"
    route = ROUTE_BY_PATH[path]
    event = make_event(
        producer=route.producer_client_id,
        event_type=sorted(route.event_types)[0],
    )
    body, headers = signed_headers(
        path=path,
        producer=route.producer_client_id,
        scope=route.required_scope,
        event=event,
    )
    app = create_app(settings=test_settings, runtime=runtime)
    with TestClient(app) as client:
        response = client.post(path, content=body, headers=headers)
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "authorization_denied"


def test_actor_schema_fails_closed(test_settings, runtime) -> None:
    path = "/api/v1/kyqra/results"
    route = ROUTE_BY_PATH[path]
    event = make_event(
        producer=route.producer_client_id,
        event_type=sorted(route.event_types)[0],
    )
    event["actor"] = {"type": "root", "id": "x", "unexpected": True}
    body, headers = signed_headers(
        path=path,
        producer=route.producer_client_id,
        scope=route.required_scope,
        event=event,
    )
    app = create_app(settings=test_settings, runtime=runtime)
    with TestClient(app) as client:
        response = client.post(path, content=body, headers=headers)
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "invalid_request"


def test_oversized_body_is_rejected_before_buffering(test_settings, runtime) -> None:
    limited = replace(test_settings, max_request_body_bytes=1024)
    runtime.settings = limited
    path = "/api/v1/postly/events"
    route = ROUTE_BY_PATH[path]
    event = make_event(
        producer=route.producer_client_id,
        event_type=sorted(route.event_types)[0],
        data={"padding": "x" * 2000},
    )
    body, headers = signed_headers(
        path=path,
        producer=route.producer_client_id,
        scope=route.required_scope,
        event=event,
    )
    app = create_app(settings=limited, runtime=runtime)
    with TestClient(app) as client:
        response = client.post(path, content=body, headers=headers)
        assert response.status_code == 413
        assert response.json()["error"]["code"] == "payload_too_large"


def test_health_ready_version(test_settings, runtime) -> None:
    app = create_app(settings=test_settings, runtime=runtime)
    with TestClient(app) as client:
        health = client.get("/health")
        assert health.status_code == 200
        assert health.json() == {
            "status": "ok",
            "service": "middleware-api",
            "component": "api",
        }
        readiness = client.get("/ready")
        assert readiness.status_code == 200
        assert readiness.json()["status"] == "ready"
        assert readiness.json()["components"] == {
            "inbox_store": "ready",
            "replay_guard": "ready",
            "identity_jwks": "ready",
            "command_store": "not_configured",
        }
        assert "checked_at" in readiness.json()
        version = client.get("/version").json()
        assert version["service"] == "middleware-api"
        assert version["environment"] == "test"
        assert version["runtime_profile_id"] == "local-unlocked"
        assert version["schema_head"] == "0003_immutable_event_ledger"


def test_readiness_reports_named_failure_without_dependency_details(
    test_settings,
    runtime,
) -> None:
    class UnavailableReplayGuard(MemoryReplayGuard):
        async def ready(self) -> bool:
            return False

    runtime.replay = UnavailableReplayGuard()
    app = create_app(settings=test_settings, runtime=runtime)
    with TestClient(app) as client:
        response = client.get("/ready")

    assert response.status_code == 503
    value = response.json()
    assert value["status"] == "not_ready"
    assert value["components"]["replay_guard"] == "not_ready"
    assert "redis" not in response.text.lower()
