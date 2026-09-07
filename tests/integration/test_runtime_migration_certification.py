"""Real migration tests on independently created, localhost-only disposable DBs."""
from __future__ import annotations

import asyncio
import os
import re
from urllib.parse import unquote, urlsplit, urlunsplit
from uuid import uuid4

import pytest

from scripts import migrate_runtime as runner
from scripts.production_migration_authority import validate_authority

pytestmark = pytest.mark.skipif(
    os.getenv("RUNTIME_INTEGRATION_TESTS") != "1", reason="disposable PostgreSQL only"
)


@pytest.mark.parametrize("predecessor", [None, "0056_klyrow_delivery_events"])
def test_real_fresh_and_predecessor_migrations(predecessor, monkeypatch):
    import asyncpg

    async def scenario():
        # Validate again here so this test is safe even with --noconftest.
        base = os.environ["DATABASE_URL"]
        parsed = urlsplit(base)
        assert os.getenv("RUNTIME_INTEGRATION_ALLOW_DISPOSABLE") == "YES"
        assert parsed.scheme in {"postgres", "postgresql"}
        assert parsed.hostname in {"localhost", "127.0.0.1"}
        assert not parsed.query and not parsed.fragment
        assert re.fullmatch(r"middleware_test_[A-Za-z0-9_]+", unquote(parsed.path.lstrip("/")))
        name = "middleware_test_migration_" + uuid4().hex
        url = urlunsplit((parsed.scheme, parsed.netloc, "/" + name, "", ""))
        admin = await asyncpg.connect(base)
        created = False
        try:
            await admin.execute(f'CREATE DATABASE "{name}"')
            created = True
            monkeypatch.setenv("DATABASE_URL", url)
            head, graph, _ = validate_authority(runner.ROOT)
            monkeypatch.setenv("SCHEMA_HEAD", head)
            if predecessor:
                await runner.upgrade_alembic(runner.database_urls(url)[1], predecessor)
            await runner.main()
            await runner.main()  # Re-running must be idempotent.
            await runner.main(verify_only=True)
            conn = await asyncpg.connect(url)
            try:
                assert await conn.fetchval("SELECT version_num FROM public.alembic_version") == head
                assert await conn.fetchval("SELECT count(*) FROM public.middleware_schema_migrations") == 10
                assert await conn.fetchval("SELECT count(*) FROM public.middleware_automation_schema_migrations") == 1
                assert await conn.fetchval("SELECT count(*) FROM public.platform_services") == 0
                assert await conn.fetchval("SELECT count(*) FROM public.middleware_automation_jobs") == 0
                # A second runner cannot race the migration session.
                await conn.fetchval("SELECT pg_advisory_lock($1)", runner.MIGRATION_LOCK)
                with pytest.raises(runner.MigrationError, match="in progress"):
                    await runner.main()
                await conn.fetchval("SELECT pg_advisory_unlock($1)", runner.MIGRATION_LOCK)
                # The correct version label is insufficient when an actual table is absent.
                await conn.execute("DROP TABLE public.platform_provisioning_audit")
                with pytest.raises(runner.MigrationError, match="catalog table"):
                    await runner.main(verify_only=True)
            finally:
                await conn.close()
        finally:
            if created:
                await admin.execute(f'DROP DATABASE "{name}" WITH (FORCE)')
            await admin.close()

    asyncio.run(scenario())
