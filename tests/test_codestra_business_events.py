import asyncio

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.api.internal.business_events import (
    BusinessEventInbox, business_identity, router,
)
from app.db.session import get_session


def event():
    return {"id": "evt_example", "type": "klyrow.usage.daily", "version": 1,
            "source": "klyrow", "tenant_id": "tnt_a", "correlation_id": "cor_a",
            "causation_id": "usage:tnt_a:2026-09-12", "occurred_at": "2026-09-13T00:00:00Z",
            "data": {"date": "2026-09-12", "unit": "accepted_message", "quantity": 5,
                     "snapshot_at": "2026-09-13T00:00:00Z"}}


def test_durable_business_event_replay_conflict_and_tenant_boundaries(tmp_path):
    engine = create_async_engine("sqlite+aiosqlite:///"+str(tmp_path/"events.db"))
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async def initialize():
        async with engine.begin() as connection:
            await connection.run_sync(BusinessEventInbox.__table__.create)
    asyncio.run(initialize())
    app = FastAPI()
    app.include_router(router)
    async def session():
        async with factory() as db:
            yield db
    app.dependency_overrides[get_session] = session
    app.dependency_overrides[business_identity] = lambda: {"tenant_id": "tnt_a", "scope": "klyrow.events.write"}
    headers = {"Idempotency-Key": "evt_example", "X-Correlation-Id": "cor_a"}
    with TestClient(app) as client:
        first = client.post("/internal/v1/events/klyrow", json=event(), headers=headers)
        assert first.status_code == 202, first.text
        assert client.post("/internal/v1/events/klyrow", json=event(), headers=headers).json() == first.json()
        other = event()
        other["data"]["quantity"] = 99
        assert client.post("/internal/v1/events/klyrow", json=other, headers=headers).status_code == 409
        other["tenant_id"] = "tnt_b"
        assert client.post("/internal/v1/events/klyrow", json=other, headers=headers).status_code == 403
        assert client.post("/internal/v1/events/klyrow", json=event()).status_code == 409
        assert client.post("/internal/v1/events/klyrow", content='x'*65537,
                           headers={**headers, "Content-Type": "application/json"}).status_code == 413
    async def verify():
        async with factory() as db:
            rows = list((await db.scalars(select(BusinessEventInbox))).all())
            assert len(rows) == 1
            assert rows[0].payload["data"]["quantity"] == 5
        await engine.dispose()
    asyncio.run(verify())


def test_service_authentication_is_required():
    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as client:
        assert client.post("/internal/v1/events/klyrow", json=event()).status_code == 401
