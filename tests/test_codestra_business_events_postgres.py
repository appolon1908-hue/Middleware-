"""Exercise inbox races in an explicitly supplied disposable PostgreSQL."""
import asyncio
import importlib.util
import os
from pathlib import Path
import uuid

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.internal.business_events import BusinessEvent, BusinessEventInbox, persist_event

pytestmark = pytest.mark.skipif(not os.getenv("MIDDLEWARE_BUSINESS_POSTGRES_URL"), reason="Requires disposable PostgreSQL")


def test_concurrent_replay_creates_one_durable_inbox_record():
    async def scenario():
        url = os.environ["MIDDLEWARE_BUSINESS_POSTGRES_URL"]
        admin = create_async_engine(url)
        schema = "business_" + uuid.uuid4().hex
        async with admin.begin() as connection:
            await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        engine = create_async_engine(url, connect_args={"server_settings": {"search_path": schema}})
        try:
            # Apply the real migration through its SQL interface.
            spec = importlib.util.spec_from_file_location("business_migration", Path(__file__).parents[1]/"migrations/versions/0061_codestra_business_events.py")
            migration = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(migration)
            statements = []
            class Operations:
                def execute(self, sql):
                    statements.append(sql)
            migration.op = Operations()
            migration.upgrade()
            async with engine.begin() as connection:
                for sql in statements:
                    await connection.execute(text(sql))
            barrier = asyncio.Barrier(2)
            class ConcurrentSession(AsyncSession):
                first_read = True
                async def get(self, *args, **kwargs):
                    value = await super().get(*args, **kwargs)
                    if self.first_read:
                        self.first_read = False
                        await asyncio.wait_for(barrier.wait(), 10)
                    return value
            factory = async_sessionmaker(engine, class_=ConcurrentSession, expire_on_commit=False)
            event = BusinessEvent(id="event", type="klyrow.email.accepted", version=1,
                                  source="klyrow", tenant_id="tenant", correlation_id="correlation",
                                  causation_id="message", occurred_at="2026-09-13T00:00:00Z",
                                  data={"message_id": "message"})
            async def publish():
                async with factory() as db:
                    return await persist_event(db, event)
            results = await asyncio.wait_for(asyncio.gather(publish(), publish()), 20)
            assert results[0] == results[1]
            async with AsyncSession(engine) as db:
                assert await db.scalar(select(func.count()).select_from(BusinessEventInbox)) == 1
        finally:
            await engine.dispose()
            async with admin.begin() as connection:
                await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
            await admin.dispose()
    asyncio.run(scenario())
