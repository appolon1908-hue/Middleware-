from __future__ import annotations

from fastapi.testclient import TestClient

from app.contracts import ROUTE_BY_PATH, WEBHOOK_ROUTES
from app.main import create_app

from .conftest import make_event, signed_headers


def test_all_contract_routes_are_registered(test_settings, runtime) -> None:
    app = create_app(settings=test_settings, runtime=runtime)
    registered = {
        route.path
        for route in app.routes
        if getattr(route, "methods", None) and "POST" in route.methods
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

        changed = {**event, "data": {"ok": False}}
        changed_body, changed_headers = signed_headers(
            path=path,
            producer=route.producer_client_id,
            scope=route.required_scope,
            event=changed,
        )
        response = client.post(path, content=changed_body, headers=changed_headers)
        assert response.status_code == 409


def test_invalid_signature_is_rejected(test_settings, runtime) -> None:
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


def test_health_ready_version(test_settings, runtime) -> None:
    app = create_app(settings=test_settings, runtime=runtime)
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/ready").json() == {"status": "ready"}
        version = client.get("/version").json()
        assert version["service"] == "middleware-api"
        assert version["environment"] == "test"
