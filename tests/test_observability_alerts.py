from __future__ import annotations

import asyncio
import copy
from datetime import UTC, datetime
from typing import Any

import jwt
from fastapi.testclient import TestClient

from app.commands import (
    CommandPolicy,
    CommandPolicyRegistry,
    CommandService,
    MemoryCommandStore,
)
from app.config import Settings
from app.observability_alert_contract import AlertmanagerWebhook
from app.observability_alerts import AlertPolicy, create_app
from app.replay import MemoryReplayGuard
from app.runtime import Runtime
from app.storage import MemoryInboxStore


class AlertTokenVerifier:
    async def verify(
        self,
        authorization: str,
        *,
        expected_client_id: str,
        required_scope: str,
    ) -> dict[str, Any]:
        assert authorization.startswith("Bearer ")
        return {
            "azp": expected_client_id,
            "sub": f"service-account-{expected_client_id}",
            "scope": required_scope,
            "aud": "middleware-api",
            "tenant_id": "codestra-platform",
        }

    async def ready(self) -> bool:
        return True


def token(client_id: str) -> str:
    return jwt.encode({"azp": client_id}, "unit-test-only", algorithm="HS256")


def policy() -> AlertPolicy:
    return AlertPolicy.model_validate(
        {
            "schema_version": "1.0",
            "policy_id": "codestra-observability-alert-mail-v1",
            "tenant_id": "codestra-platform",
            "receiver": "codestra-observability-email",
            "recipient_policy_id": "codestra-observability-admin-v1",
            "sender_policy_id": "codestra-alert-sender-v1",
            "recipient": "appolon@codestra.co",
            "sender": "alerts@codestra.co",
            "reply_to": "appolon@codestra.co",
            "allowed_environments": ["test"],
            "allowed_severities": ["critical", "warning"],
            "max_alerts_per_request": 20,
            "max_body_bytes": 131072,
            "normal_delivery_path": "middleware-klyrow-adapter",
            "direct_smtp_allowed": False,
            "delivery_enabled_by_default": False,
        }
    )


def settings() -> Settings:
    return Settings.from_env(
        {
            "APP_ENV": "test",
            "ALLOW_IN_MEMORY_STORAGE": "true",
            "EXTERNAL_EFFECTS": "false",
        }
    )


def runtime(active: bool = True) -> Runtime:
    command_store = MemoryCommandStore()
    command_service = CommandService(
        store=command_store,
        policies=CommandPolicyRegistry(
            policies=(
                CommandPolicy(
                    prefix="observability.alert.",
                    target="klyrow-alert-email",
                    capability="OBSERVABILITY_ALERT_EMAIL_DELIVERY",
                    readback_required=True,
                ),
            ),
            capabilities={"OBSERVABILITY_ALERT_EMAIL_DELIVERY": active},
        ),
    )
    return Runtime(
        settings=settings(),
        inbox=MemoryInboxStore(),
        replay=MemoryReplayGuard(),
        tokens=AlertTokenVerifier(),
        commands=command_service,
    )


def webhook() -> dict[str, Any]:
    return {
        "version": "4",
        "groupKey": "{}:{alertname=\"HostDown\"}",
        "truncatedAlerts": 0,
        "status": "firing",
        "receiver": "codestra-observability-email",
        "groupLabels": {"alertname": "HostDown"},
        "commonLabels": {
            "alertname": "HostDown",
            "severity": "critical",
            "service": "node-exporter",
            "environment": "test",
            "host": "37.27.128.39",
        },
        "commonAnnotations": {"summary": "Provider host is down"},
        "externalURL": "https://aler.codestra.media/#/alerts?secret=removed",
        "alerts": [
            {
                "status": "firing",
                "labels": {
                    "alertname": "HostDown",
                    "severity": "critical",
                    "service": "node-exporter",
                    "environment": "test",
                    "host": "37.27.128.39",
                    "owner": "codestra-observability",
                    "release_id": "obs-test-1",
                },
                "annotations": {
                    "summary": "Provider host is down",
                    "description": "The synthetic host target is unavailable.",
                    "runbook_url": (
                        "https://graf.codestra.media/d/runbooks/host-down?token=removed"
                    ),
                    "dashboard_url": (
                        "https://graf.codestra.media/d/host/provider?var=removed"
                    ),
                },
                "startsAt": "2026-09-02T16:00:00Z",
                "endsAt": "2026-09-02T16:00:00Z",
                "generatorURL": "https://prom.codestra.media/graph?g0.expr=up",
                "fingerprint": "abc123def456",
            }
        ],
    }


def headers(
    client_id: str = "alertmanager-service",
    *,
    key: str = "alertmanager-webhook-v1",
) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token(client_id)}",
        "Content-Type": "application/json",
        "X-Tenant-ID": "codestra-platform",
        "X-Correlation-ID": "corr-observability-alert-0001",
        "Idempotency-Key": key,
    }


def app(active: bool = True):
    return create_app(
        settings=settings(),
        runtime=runtime(active=active),
        policy=policy(),
        env={
            "OBSERVABILITY_ALERT_EMAIL_DELIVERY": "true" if active else "false",
            "OBSERVABILITY_ALERT_ACTIVATION_ID": "CHG-TEST-OBS-ALERT-01",
        },
    )


def test_firing_alert_is_durable_and_replay_safe() -> None:
    with TestClient(app()) as client:
        response = client.post(
            "/v1/integrations/alertmanager/events",
            json=webhook(),
            headers=headers(),
        )
        assert response.status_code == 202
        body = response.json()
        assert body["recipient_policy_id"] == "codestra-observability-admin-v1"
        assert body["sender_policy_id"] == "codestra-alert-sender-v1"
        assert len(body["operations"]) == 1
        operation = body["operations"][0]
        assert operation["operation_state"] == "persisted"
        assert operation["duplicate"] is False

        replay = client.post(
            "/v1/observability/alerts",
            json=webhook(),
            headers=headers(),
        )
        assert replay.status_code == 200
        assert replay.json()["operations"][0]["duplicate"] is True
        assert (
            replay.json()["operations"][0]["operation_id"]
            == operation["operation_id"]
        )

        detail = client.get(
            operation["status_url"],
            headers=headers(key="alert-status-read-v1"),
        )
        assert detail.status_code == 200
        assert detail.json()["command_type"] == "observability.alert.email.send.v1"
        assert detail.json()["target"] == "klyrow-alert-email"

        events = client.get(
            operation["events_url"],
            headers=headers(key="alert-events-read-v1"),
        )
        assert events.status_code == 200
        assert events.json()["items"][0]["new_state"] == "persisted"


def test_mixed_status_group_processes_each_alert_transition() -> None:
    value = webhook()
    resolved = copy.deepcopy(value["alerts"][0])
    resolved["status"] = "resolved"
    resolved["fingerprint"] = "resolved123456"
    resolved["endsAt"] = "2026-09-02T16:05:00Z"
    value["alerts"].append(resolved)
    with TestClient(app()) as client:
        response = client.post(
            "/v1/integrations/alertmanager/events",
            json=value,
            headers=headers(key="mixed-status-alert-group-v1"),
        )
        assert response.status_code == 202
        assert [item["alert_state"] for item in response.json()["operations"]] == [
            "firing",
            "resolved",
        ]


def test_annotation_urls_are_sanitized_before_command_creation() -> None:
    value = webhook()
    parsed = AlertmanagerWebhook.model_validate(value)
    alert = parsed.alerts[0]
    assert alert.annotations["runbook_url"] == (
        "https://graf.codestra.media/d/runbooks/host-down"
    )
    assert alert.annotations["dashboard_url"] == (
        "https://graf.codestra.media/d/host/provider"
    )


def test_invalid_later_alert_does_not_partially_persist_batch() -> None:
    value = webhook()
    denied = copy.deepcopy(value["alerts"][0])
    denied["fingerprint"] = "denied123456"
    denied["labels"]["environment"] = "production"
    value["alerts"].append(denied)
    active_runtime = runtime()
    with TestClient(
        create_app(
            settings=settings(),
            runtime=active_runtime,
            policy=policy(),
            env={
                "OBSERVABILITY_ALERT_EMAIL_DELIVERY": "true",
                "OBSERVABILITY_ALERT_ACTIVATION_ID": "CHG-TEST-OBS-ALERT-01",
            },
        )
    ) as client:
        response = client.post(
            "/v1/integrations/alertmanager/events",
            json=value,
            headers=headers(key="all-or-nothing-alert-group-v1"),
        )
        assert response.status_code == 403
    assert active_runtime.commands is not None
    assert (
        asyncio.run(
            active_runtime.commands.list_operations(
                "codestra-platform",
                limit=100,
            )
        )
        == []
    )


def test_same_identity_with_changed_payload_is_a_conflict() -> None:
    changed = copy.deepcopy(webhook())
    changed["alerts"][0]["annotations"]["summary"] = (
        "Different semantic payload"
    )
    with TestClient(app()) as client:
        first = client.post(
            "/v1/observability/alerts",
            json=webhook(),
            headers=headers(),
        )
        assert first.status_code == 202
        second = client.post(
            "/v1/observability/alerts",
            json=changed,
            headers=headers(),
        )
        assert second.status_code == 409
        assert second.json()["code"] == "command_conflict"


def test_sensitive_annotations_are_rejected() -> None:
    value = webhook()
    value["alerts"][0]["annotations"]["authorization"] = "Bearer secret"
    with TestClient(app()) as client:
        response = client.post(
            "/v1/observability/alerts",
            json=value,
            headers=headers(),
        )
        assert response.status_code == 400
        assert response.json()["code"] == "invalid_request"


def test_alert_delivery_capability_defaults_fail_closed() -> None:
    with TestClient(app(active=False)) as client:
        response = client.post(
            "/v1/observability/alerts",
            json=webhook(),
            headers=headers(),
        )
        assert response.status_code == 403
        assert response.json()["code"] == "capability_disabled"
        capabilities = client.get("/capabilities")
        assert capabilities.status_code == 200
        assert capabilities.json()["OBSERVABILITY_ALERT_EMAIL_DELIVERY"] is False
        assert capabilities.json()["direct_smtp_allowed"] is False


def test_delivery_callback_uses_durable_inbox_and_is_replay_safe() -> None:
    with TestClient(app()) as client:
        accepted = client.post(
            "/v1/observability/alerts",
            json=webhook(),
            headers=headers(),
        )
        operation_id = accepted.json()["operations"][0]["operation_id"]
        delivery = {
            "event_id": "delivery-event-0001",
            "operation_id": operation_id,
            "status": "delivered",
            "provider_message_id": operation_id,
            "occurred_at": datetime(
                2026,
                9,
                2,
                16,
                5,
                tzinfo=UTC,
            ).isoformat(),
            "safe_metadata": {"provider_status": "delivered"},
        }
        delivery_headers = headers(
            "klyrow-alert-adapter",
            key="delivery-event-0001",
        )
        first = client.post(
            "/v1/observability/alert-delivery-events",
            json=delivery,
            headers=delivery_headers,
        )
        assert first.status_code == 202
        assert first.json()["status"] == "accepted"
        assert first.json()["authoritative_completion"] == "provider-readback"

        replay = client.post(
            "/v1/observability/alert-delivery-events",
            json=delivery,
            headers=delivery_headers,
        )
        assert replay.status_code == 200
        assert replay.json()["duplicate"] is True


def test_wrong_caller_and_environment_are_denied() -> None:
    with TestClient(app()) as client:
        wrong_caller = client.post(
            "/v1/observability/alerts",
            json=webhook(),
            headers=headers("kong-gateway"),
        )
        assert wrong_caller.status_code == 403

        production = webhook()
        production["alerts"][0]["labels"]["environment"] = "production"
        production["commonLabels"]["environment"] = "production"
        wrong_environment = client.post(
            "/v1/observability/alerts",
            json=production,
            headers=headers(key="environment-test-key"),
        )
        assert wrong_environment.status_code == 403
