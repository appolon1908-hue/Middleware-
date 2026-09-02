from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime
from pathlib import Path

import asyncpg
import pytest
import pytest_asyncio

from app.commands import (
    CommandConflict,
    CommandEnvelope,
    CommandPolicy,
    CommandPolicyRegistry,
    CommandService,
    PostgresCommandStore,
)
from app.observability_alert_contract import (
    ALERTMANAGER_CLIENT_ID,
    AlertPolicy,
    AlertmanagerAlert,
    build_command,
)
from app.observability_incidents import (
    AlertmanagerStatusItem,
    IncidentConflict,
    IncidentService,
    PostgresIncidentStore,
    incident_identity,
)


DATABASE_URL = os.getenv("DATABASE_URL", "")
RUN = os.getenv("RUNTIME_INTEGRATION_TESTS") == "1"
TENANT_ID = f"observability-incident-integration-{uuid.uuid4()}"
ACTOR_ID = "service-account-alertmanager-service"
GROUP_KEY = '{}:{alertname="IncidentIntegration"}'

pytestmark = pytest.mark.skipif(
    not RUN,
    reason="set RUNTIME_INTEGRATION_TESTS=1 against disposable PostgreSQL/Redis",
)


def policy() -> AlertPolicy:
    return AlertPolicy.model_validate(
        {
            "schema_version": "1.0",
            "policy_id": "observability-incident-integration-v1",
            "tenant_id": TENANT_ID,
            "receiver": "codestra-observability-email",
            "recipient_policy_id": "codestra-observability-admin-v1",
            "sender_policy_id": "codestra-alert-sender-v1",
            "recipient": "integration@example.invalid",
            "sender": "alerts@example.invalid",
            "reply_to": "integration@example.invalid",
            "allowed_environments": ["integration"],
            "allowed_severities": ["critical", "warning", "info"],
            "immediate_severities": ["critical"],
            "grouped_severities": ["warning"],
            "state_only_severities": ["info"],
            "warning_group_wait_seconds": 300,
            "warning_repeat_interval_seconds": 14_400,
            "max_alerts_per_request": 20,
            "max_body_bytes": 131_072,
            "normal_delivery_path": "middleware-klyrow-adapter",
            "direct_smtp_allowed": False,
            "delivery_enabled_by_default": False,
        }
    )


def alert(*, fingerprint: str, severity: str = "critical") -> AlertmanagerAlert:
    return AlertmanagerAlert.model_validate(
        {
            "status": "firing",
            "labels": {
                "alertname": "IncidentIntegration",
                "severity": severity,
                "service": "disposable-ci",
                "environment": "integration",
                "host": "disposable-postgres",
                "codestra_business": "platform",
                "owner": "codestra-observability",
            },
            "annotations": {
                "summary": "Disposable incident integration test",
                "description": "No provider or production traffic is produced.",
                "runbook_url": "https://runbooks.example.invalid/incident-integration",
            },
            "startsAt": "2026-09-02T16:00:00Z",
            "endsAt": "2026-09-02T16:00:00Z",
            "generatorURL": "https://prom.example.invalid/graph",
            "fingerprint": fingerprint,
        }
    )


def services(pool: asyncpg.Pool) -> tuple[CommandService, IncidentService]:
    commands = CommandService(
        store=PostgresCommandStore(pool),
        policies=CommandPolicyRegistry(
            policies=(
                CommandPolicy(
                    prefix="observability.alert.",
                    target="klyrow-alert-email",
                    capability="OBSERVABILITY_ALERT_EMAIL_DELIVERY",
                    readback_required=True,
                ),
            ),
            capabilities={"OBSERVABILITY_ALERT_EMAIL_DELIVERY": True},
        ),
    )
    incidents = IncidentService(
        store=PostgresIncidentStore(commands),
        commands=commands,
        policy=policy(),
        delivery_enabled=True,
    )
    return commands, incidents


@pytest_asyncio.fixture
async def pool() -> asyncpg.Pool:
    assert DATABASE_URL, "DATABASE_URL is required"
    value = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=4)
    async with value.acquire() as conn:
        for migration in sorted(
            Path("migrations").glob("[0-9][0-9][0-9][0-9]_*.sql")
        ):
            await conn.execute(migration.read_text(encoding="utf-8"))
    try:
        yield value
    finally:
        await value.close()


@pytest.mark.asyncio
async def test_incident_command_and_notification_commit_atomically(
    pool: asyncpg.Pool,
) -> None:
    commands, incidents = services(pool)
    item = alert(fingerprint="incident-atomic-0001")

    first = await incidents.ingest(
        group_key=GROUP_KEY,
        alert=item,
        actor_id=ACTOR_ID,
        correlation_id="incident-correlation-0001",
        source_deployment="alertmanager-disposable-ci",
        request_idempotency_key="incident-request-0001",
    )
    assert first.operation is not None
    assert first.notification_status == "queued"
    assert first.duplicate is False
    assert await incidents.store.ready() is True
    assert await commands.store.ready() is True

    replay = await incidents.ingest(
        group_key=GROUP_KEY,
        alert=item,
        actor_id=ACTOR_ID,
        correlation_id="incident-correlation-0001",
        source_deployment="alertmanager-disposable-ci",
        request_idempotency_key="different-transport-key-0001",
    )
    assert replay.duplicate is True
    assert replay.operation is not None
    assert replay.operation.command_id == first.operation.command_id

    async with pool.acquire() as conn:
        counts = {
            table: await conn.fetchval(
                f"SELECT count(*) FROM {table} WHERE tenant_id=$1",  # noqa: S608
                TENANT_ID,
            )
            for table in (
                "middleware_observability_incidents",
                "middleware_observability_incident_events",
                "middleware_observability_incident_audit",
                "middleware_observability_notification_intents",
                "middleware_commands",
                "middleware_command_audit",
                "middleware_outbox",
            )
        }
    assert counts == {table: 1 for table in counts}

    acknowledged = await incidents.store.mutate(
        TENANT_ID,
        first.incident.incident_id,
        action="acknowledge",
        actor_id="service-account-observability-operator",
        correlation_id="incident-correlation-ack-0001",
        idempotency_key="incident-acknowledge-0001",
        expected_version=1,
        reason="disposable integration acknowledgement",
    )
    assert acknowledged.state == "acknowledged"
    assert acknowledged.resource_version == 2

    silenced = await incidents.store.ingest_status(
        policy=policy(),
        item=AlertmanagerStatusItem.model_validate(
            {
                "groupKey": GROUP_KEY,
                "fingerprint": item.fingerprint,
                "startsAt": "2026-09-02T16:00:00Z",
                "state": "silenced",
                "silencedBy": ["disposable-silence-1"],
                "inhibitedBy": [],
            }
        ),
        actor_id=ACTOR_ID,
        correlation_id="incident-correlation-status-0001",
        source_deployment="alertmanager-disposable-ci",
        request_idempotency_key="incident-status-request-0001",
        observed_at=datetime(2026, 9, 2, 16, 1, tzinfo=UTC),
    )
    assert silenced.state == "silenced"
    firing = await incidents.store.ingest_status(
        policy=policy(),
        item=AlertmanagerStatusItem.model_validate(
            {
                "groupKey": GROUP_KEY,
                "fingerprint": item.fingerprint,
                "startsAt": "2026-09-02T16:00:00Z",
                "state": "firing",
                "silencedBy": [],
                "inhibitedBy": [],
            }
        ),
        actor_id=ACTOR_ID,
        correlation_id="incident-correlation-status-0002",
        source_deployment="alertmanager-disposable-ci",
        request_idempotency_key="incident-status-request-0002",
        observed_at=datetime(2026, 9, 2, 16, 2, tzinfo=UTC),
    )
    assert firing.state == "firing"
    with pytest.raises(IncidentConflict):
        await incidents.store.ingest_status(
            policy=policy(),
            item=AlertmanagerStatusItem.model_validate(
                {
                    "groupKey": GROUP_KEY,
                    "fingerprint": item.fingerprint,
                    "startsAt": "2026-09-02T16:00:00Z",
                    "state": "silenced",
                    "silencedBy": ["stale-silence-1"],
                    "inhibitedBy": [],
                }
            ),
            actor_id=ACTOR_ID,
            correlation_id="incident-correlation-status-stale",
            source_deployment="alertmanager-disposable-ci",
            request_idempotency_key="incident-status-request-stale",
            observed_at=datetime(2026, 9, 2, 16, 0, tzinfo=UTC),
        )
    timeline = await incidents.store.list_timeline(
        TENANT_ID,
        first.incident.incident_id,
        limit=10,
        after_event_id=None,
    )
    assert [event.event_type for event in timeline] == [
        "firing",
        "acknowledge",
        "silenced",
        "firing",
    ]
    assert timeline[-1].occurred_at == datetime(2026, 9, 2, 16, 2, tzinfo=UTC)

    async with pool.acquire() as conn:
        with pytest.raises(asyncpg.PostgresError):
            await conn.execute(
                "UPDATE middleware_observability_incident_events SET actor_id='tamper' "
                "WHERE tenant_id=$1",
                TENANT_ID,
            )


@pytest.mark.asyncio
async def test_command_conflict_rolls_back_incident_projection(
    pool: asyncpg.Pool,
) -> None:
    commands, incidents = services(pool)
    item = alert(fingerprint="incident-rollback-0001")
    expected = build_command(
        policy=policy(),
        alert=item,
        group_key=GROUP_KEY,
        receiver=policy().receiver,
        actor=ACTOR_ID,
        correlation_id="incident-correlation-rollback-0001",
        incident_id=incident_identity(TENANT_ID, item.fingerprint),
    )
    changed_payload = expected.model_dump(mode="python")
    changed_payload["payload"]["content"]["subject"] = "Conflicting durable command"
    conflicting = CommandEnvelope.model_validate(changed_payload)
    await commands.submit(
        conflicting,
        authenticated_subject=ACTOR_ID,
        authenticated_client_id=ALERTMANAGER_CLIENT_ID,
    )

    with pytest.raises(CommandConflict):
        await incidents.ingest(
            group_key=GROUP_KEY,
            alert=item,
            actor_id=ACTOR_ID,
            correlation_id="incident-correlation-rollback-0001",
            source_deployment="alertmanager-disposable-ci",
            request_idempotency_key="incident-request-rollback-0001",
        )

    async with pool.acquire() as conn:
        assert (
            await conn.fetchval(
                "SELECT count(*) FROM middleware_observability_incidents "
                "WHERE tenant_id=$1 AND incident_id=$2",
                TENANT_ID,
                incident_identity(TENANT_ID, item.fingerprint),
            )
            == 0
        )
        assert (
            await conn.fetchval(
                "SELECT count(*) FROM middleware_observability_incident_events "
                "WHERE tenant_id=$1 AND incident_id=$2",
                TENANT_ID,
                incident_identity(TENANT_ID, item.fingerprint),
            )
            == 0
        )


@pytest.mark.asyncio
async def test_warning_repeat_uses_persisted_schedule(
    pool: asyncpg.Pool,
) -> None:
    _, incidents = services(pool)
    item = alert(fingerprint="incident-warning-repeat-0001", severity="warning")
    first = await incidents.ingest(
        group_key=GROUP_KEY,
        alert=item,
        actor_id=ACTOR_ID,
        correlation_id="incident-warning-repeat-correlation-0001",
        source_deployment="alertmanager-disposable-ci",
        request_idempotency_key="incident-warning-repeat-request-0001",
    )
    assert first.operation is not None
    assert first.notification_status == "scheduled"
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE middleware_observability_notification_intents
            SET scheduled_at=now() - interval '14401 seconds'
            WHERE tenant_id=$1 AND incident_id=$2
            """,
            TENANT_ID,
            first.incident.incident_id,
        )

    repeated = await incidents.ingest(
        group_key=GROUP_KEY,
        alert=item,
        actor_id=ACTOR_ID,
        correlation_id="incident-warning-repeat-correlation-0002",
        source_deployment="alertmanager-disposable-ci",
        request_idempotency_key="incident-warning-repeat-request-0002",
    )
    assert repeated.operation is not None
    assert repeated.operation.command_id != first.operation.command_id
    assert repeated.notification_status == "queued"
    replay = await incidents.ingest(
        group_key=GROUP_KEY,
        alert=item,
        actor_id=ACTOR_ID,
        correlation_id="incident-warning-repeat-correlation-0002",
        source_deployment="alertmanager-disposable-ci",
        request_idempotency_key="incident-warning-repeat-request-0002",
    )
    assert replay.duplicate is True
    assert replay.operation is not None
    assert replay.operation.command_id == repeated.operation.command_id

    async with pool.acquire() as conn:
        assert (
            await conn.fetchval(
                "SELECT count(*) FROM middleware_observability_notification_intents "
                "WHERE tenant_id=$1 AND incident_id=$2",
                TENANT_ID,
                first.incident.incident_id,
            )
            == 2
        )
        assert (
            await conn.fetchval(
                "SELECT count(*) FROM middleware_observability_incident_events "
                "WHERE tenant_id=$1 AND incident_id=$2 "
                "AND event_type='notification_repeat'",
                TENANT_ID,
                first.incident.incident_id,
            )
            == 1
        )
