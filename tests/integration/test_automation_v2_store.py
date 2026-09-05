from __future__ import annotations

import asyncio
import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import asyncpg
import pytest
import pytest_asyncio

from app.automation_policy import AutomationPolicy
from app.automation_v2 import (
    AutomationConflict,
    AutomationService,
    JobClaimRequest,
    PostgresAutomationStore,
    WorkflowRouter,
)
from app.models import EventEnvelope
from app.storage import PostgresInboxStore, canonical_payload_sha256


DATABASE_URL = os.getenv("DATABASE_URL", "")
RUN = os.getenv("RUNTIME_INTEGRATION_TESTS") == "1"

pytestmark = pytest.mark.skipif(
    not RUN,
    reason="set RUNTIME_INTEGRATION_TESTS=1 against disposable PostgreSQL/Redis",
)


class UnusedCommands:
    policies = type("Policies", (), {"policies": (), "capabilities": {}})()


@pytest_asyncio.fixture
async def automation_pool() -> asyncpg.Pool:
    assert DATABASE_URL, "DATABASE_URL is required"
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=8)
    root = [
        path.read_text(encoding="utf-8")
        for path in sorted(Path("migrations").glob("[0-9][0-9][0-9][0-9]_*.sql"))
    ]
    automation = [
        path.read_text(encoding="utf-8")
        for path in sorted(Path("migrations/automation").glob("[0-9][0-9][0-9][0-9]_*.sql"))
    ]
    async with pool.acquire() as conn:
        await conn.execute("DROP TABLE IF EXISTS middleware_automation_replay_requests CASCADE")
        await conn.execute("DROP TABLE IF EXISTS middleware_automation_reconciliation_runs CASCADE")
        await conn.execute("DROP TABLE IF EXISTS middleware_automation_dead_letters CASCADE")
        await conn.execute("DROP TABLE IF EXISTS middleware_automation_approvals CASCADE")
        await conn.execute("DROP TABLE IF EXISTS middleware_automation_job_steps CASCADE")
        await conn.execute("DROP TABLE IF EXISTS middleware_automation_dispatch_outbox CASCADE")
        await conn.execute("DROP TABLE IF EXISTS middleware_automation_audit CASCADE")
        await conn.execute("DROP TABLE IF EXISTS middleware_automation_jobs CASCADE")
        await conn.execute("DROP TABLE IF EXISTS middleware_automation_schema_migrations CASCADE")
        await conn.execute("DROP TABLE IF EXISTS middleware_outbox_attempt_events CASCADE")
        await conn.execute("DROP TABLE IF EXISTS middleware_control_mutations CASCADE")
        await conn.execute("DROP TABLE IF EXISTS middleware_control_audit CASCADE")
        await conn.execute("DROP TABLE IF EXISTS middleware_operation_mutations CASCADE")
        await conn.execute("DROP TABLE IF EXISTS middleware_event_ledger CASCADE")
        await conn.execute("DROP TABLE IF EXISTS middleware_reconciliation_audit CASCADE")
        await conn.execute("DROP TABLE IF EXISTS middleware_outbox CASCADE")
        await conn.execute("DROP TABLE IF EXISTS middleware_inbox CASCADE")
        await conn.execute("DROP TABLE IF EXISTS middleware_schema_migrations CASCADE")
        await conn.execute("DROP TABLE IF EXISTS middleware_command_audit CASCADE")
        await conn.execute("DROP TABLE IF EXISTS middleware_command_attempts CASCADE")
        await conn.execute("DROP TABLE IF EXISTS middleware_commands CASCADE")
        for migration in root + automation:
            await conn.execute(migration)
    try:
        yield pool
    finally:
        await pool.close()


def envelope() -> EventEnvelope:
    now = datetime.now(UTC)
    return EventEnvelope(
        event_id="event-email-delivered-atomic-0001",
        event_type="codestra.email.message.delivered",
        event_version="1.0",
        occurred_at=now,
        received_at=now,
        source="klyrow-gateway",
        tenant_id="tenant-integration",
        correlation_id="correlation-integration-0001",
        causation_id="causation-integration-0001",
        idempotency_key="event-email-delivered-atomic-0001",
        payload={"message_id": "message-integration-1", "status": "delivered"},
        metadata={},
    )


@pytest.mark.asyncio
async def test_event_job_and_dispatch_are_atomic_and_idempotent(automation_pool: asyncpg.Pool) -> None:
    inbox = PostgresInboxStore(automation_pool)
    store = PostgresAutomationStore(automation_pool, owns_pool=False)
    service = AutomationService(
        store=store,
        policy=AutomationPolicy.from_path(),
        workflow_router=WorkflowRouter.load(),
        commands=UnusedCommands(),
        umbrella_controls={},
    )
    item = envelope()
    semantic = canonical_payload_sha256(item.model_dump(mode="json"))
    body_sha = hashlib.sha256(json.dumps(item.model_dump(mode="json"), sort_keys=True).encode()).hexdigest()

    accepted = await service.accept_event(
        inbox,
        item,
        producer_client_id=item.source,
        body_sha256=body_sha,
        semantic_sha256=semantic,
    )
    assert accepted.duplicate is False
    duplicate = await service.accept_event(
        inbox,
        item,
        producer_client_id=item.source,
        body_sha256=body_sha,
        semantic_sha256=semantic,
    )
    assert duplicate.duplicate is True

    async with automation_pool.acquire() as conn:
        counts = {
            "inbox": await conn.fetchval("SELECT count(*) FROM middleware_inbox"),
            "ledger": await conn.fetchval("SELECT count(*) FROM middleware_event_ledger"),
            "event_outbox": await conn.fetchval("SELECT count(*) FROM middleware_outbox"),
            "jobs": await conn.fetchval("SELECT count(*) FROM middleware_automation_jobs"),
            "dispatch": await conn.fetchval("SELECT count(*) FROM middleware_automation_dispatch_outbox"),
        }
        wake = await conn.fetchrow(
            "SELECT payload FROM middleware_automation_dispatch_outbox WHERE tenant_id=$1",
            item.tenant_id,
        )
        job = await conn.fetchrow(
            "SELECT job_id,workflow_key,workflow_version FROM middleware_automation_jobs WHERE tenant_id=$1",
            item.tenant_id,
        )
    assert counts == {"inbox": 1, "ledger": 1, "event_outbox": 1, "jobs": 1, "dispatch": 1}
    assert wake is not None and job is not None
    wake_payload = json.loads(wake["payload"]) if isinstance(wake["payload"], str) else dict(wake["payload"])

    async def claim(execution_id):
        return await store.claim(
            JobClaimRequest(
                tenant_id=item.tenant_id,
                correlation_id=item.correlation_id,
                idempotency_key=f"claim-{execution_id}",
                job_id=job["job_id"],
                delivery_token=wake_payload["delivery_token"],
                workflow_key=job["workflow_key"],
                workflow_version=job["workflow_version"],
                execution_id=execution_id,
            ),
            client_id="n8n-messaging-automation",
        )

    outcomes = await asyncio.gather(claim(uuid4()), claim(uuid4()), return_exceptions=True)
    assert sum(not isinstance(value, Exception) for value in outcomes) == 1
    assert sum(isinstance(value, AutomationConflict) for value in outcomes) == 1
