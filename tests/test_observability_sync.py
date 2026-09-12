from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.adapters.odoo.results import _observability_body
from app.api.v1.observability_sync import (
    IncidentState,
    KpiSnapshot,
    _projection_hash,
    _safe_payload,
)
from app.monitoring.auth import Principal


def _principal():
    return Principal(
        subject="collector",
        tenant="tenant-a",
        roles=frozenset({"monitoring_collector"}),
        campaigns=frozenset(),
        services=frozenset({"prometheus"}),
        client="prometheus",
    )


def _kpi_payload():
    value = {
        "event_id": "kpi-tenant-a-1",
        "schema_version": "kyyow.observability.kpi.v1",
        "tenant_id": "tenant-a",
        "metric_code": "sms.delivery_rate",
        "service_id": "middleware",
        "environment": "production",
        "period_reference": "2026-09-12T12:00:00Z",
        "period_start": "2026-09-12T12:00:00+00:00",
        "period_end": "2026-09-12T13:00:00+00:00",
        "value": 99.1,
        "unit": "percent",
        "dimensions": {"route": "primary"},
        "source": "prometheus",
        "source_revision": 1,
        "source_payload_hash": "sha256:" + "a" * 64,
        "observed_at": "2026-09-12T13:00:00+00:00",
        "reconciliation_state": "accepted",
        "correlation_id": "corr-kpi-1",
    }
    normalized = {
        **value,
        "period_start": "2026-09-12T12:00:00Z",
        "period_end": "2026-09-12T13:00:00Z",
        "observed_at": "2026-09-12T13:00:00Z",
    }
    value["projection_hash"] = "sha256:" + _projection_hash(normalized)
    return value


def _incident_payload():
    value = {
        "event_id": "incident-tenant-a-1",
        "schema_version": "kyyow.observability.incident.v1",
        "tenant_id": "tenant-a",
        "incident_id": "incident-1",
        "fingerprint": "fp-1",
        "alertname": "MiddlewareOdooDelivery",
        "group_key": "tenant-a/middleware",
        "severity": "critical",
        "state": "firing",
        "service_id": "middleware",
        "environment": "production",
        "host": "node-1",
        "summary": "Odoo delivery is failing",
        "labels": {"service": "middleware", "severity": "critical"},
        "first_seen_at": "2026-09-12T13:00:00+00:00",
        "last_seen_at": "2026-09-12T13:00:00+00:00",
        "resolved_at": None,
        "source_deployment": "middleware:abc123",
        "resource_version": 1,
        "source_payload_hash": "sha256:" + "b" * 64,
        "observed_at": "2026-09-12T13:00:00+00:00",
        "correlation_id": "corr-incident-1",
    }
    normalized = {
        **value,
        "first_seen_at": "2026-09-12T13:00:00Z",
        "last_seen_at": "2026-09-12T13:00:00Z",
        "observed_at": "2026-09-12T13:00:00Z",
    }
    value["projection_hash"] = "sha256:" + _projection_hash(normalized)
    return value


def test_kpi_payload_is_canonicalized_before_hash_verification():
    body = KpiSnapshot.model_validate(_kpi_payload())
    safe = _safe_payload(body, _principal(), "kpi-idempotency-key")
    assert safe["period_start"] == "2026-09-12T12:00:00Z"
    assert safe["observed_at"] == "2026-09-12T13:00:00Z"
    assert safe["projection_hash"] == body.projection_hash


def test_sensitive_observability_dimensions_are_rejected():
    payload = _kpi_payload()
    payload["dimensions"] = {"api_token": "must-not-enter-odoo"}
    with pytest.raises(ValidationError):
        KpiSnapshot.model_validate(payload)


def test_non_resolved_incident_cannot_have_resolution_time():
    payload = _incident_payload()
    payload["resolved_at"] = "2026-09-12T13:01:00Z"
    with pytest.raises(ValidationError):
        IncidentState.model_validate(payload)


def test_odoo_transport_binding_uses_durable_delivery_identity():
    delivery_id = uuid4()
    delivery = SimpleNamespace(
        standard_result_json={
            "operation": "observability.kpis.create",
            "idempotency_key": "source-key",
        },
        result_public_id=delivery_id,
    )
    event = SimpleNamespace(
        payload_json=_kpi_payload(),
        original_event_id="kpi-tenant-a-1",
    )
    payload = _observability_body(delivery, event)
    assert payload["idempotency_key"] == str(delivery_id)
    assert payload["causation_id"] == event.original_event_id
