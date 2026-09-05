"""Real PostgreSQL atomicity tests. Only an explicit disposable local DB is allowed."""
from __future__ import annotations

import asyncio
import os
import unittest
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

import asyncpg

from app.calling_ledger import CallingLedger
from app.commands import CommandConflict, CommandPolicyRegistry, CommandService, PostgresCommandStore
from test_calling_contract import grant, originate, principal

DATABASE = os.getenv("CALLING_TEST_DATABASE_URL", "")


@unittest.skipUnless(DATABASE, "disposable calling PostgreSQL URL was not supplied")
class CallingPostgresTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        parsed = urlparse(DATABASE)
        self.assertIn(parsed.hostname, {"127.0.0.1", "localhost"})
        self.assertEqual(parsed.path, "/middleware_test_calling")
        self.schema = "calling_test_" + uuid4().hex
        self.admin = await asyncpg.connect(DATABASE)
        await self.admin.execute(f'CREATE SCHEMA "{self.schema}"')
        self.pool = await asyncpg.create_pool(DATABASE, min_size=1, max_size=5,
                                             server_settings={"search_path": self.schema + ",public"})
        try:
            async with self.pool.acquire() as connection:
                for migration in sorted(Path("migrations").glob("[0-9][0-9][0-9][0-9]_*.sql")):
                    await connection.execute(migration.read_text())
        except Exception:
            await self.pool.close()
            await self.admin.execute(f'DROP SCHEMA "{self.schema}" CASCADE')
            await self.admin.close()
            raise
        self.store = PostgresCommandStore(self.pool)
        self.commands = CommandService(self.store, CommandPolicyRegistry.load())
        self.ledger = CallingLedger(self.commands)
        self.grant = grant()

    async def asyncTearDown(self):
        await self.pool.close()
        await self.admin.execute(f'DROP SCHEMA "{self.schema}" CASCADE')
        await self.admin.close()

    async def counts(self):
        return tuple([await self.pool.fetchval(f"SELECT count(*) FROM {table}")
                      for table in ["middleware_commands", "middleware_command_audit", "middleware_outbox"]])

    async def reserve(self, body=None, ledger=None):
        return await (ledger or self.ledger).originate(principal(), body or originate(), "test-correlation-0001", self.grant)

    async def test_command_audit_and_outbox_commit_together(self):
        command = await self.reserve()
        self.assertEqual(await self.counts(), (1, 1, 1))
        row = await self.pool.fetchrow("SELECT command_id,destination FROM middleware_outbox")
        self.assertEqual(str(row["command_id"]), str(command.command_id))
        self.assertEqual(row["destination"], "temporal-command")

    async def test_two_facades_serialize_distinct_keys(self):
        results = await asyncio.gather(self.reserve(), self.reserve(
            originate(idempotency_key="test-originate-0002"), CallingLedger(self.commands)), return_exceptions=True)
        self.assertEqual(sum(isinstance(result, CommandConflict) for result in results), 1)
        self.assertEqual(await self.counts(), (1, 1, 1))

    async def test_concurrent_retries_are_one_command_and_one_outbox(self):
        results = await asyncio.gather(*[self.reserve(ledger=CallingLedger(self.commands)) for _ in range(8)])
        self.assertEqual(len({result.command_id for result in results}), 1)
        self.assertEqual(await self.counts(), (1, 1, 1))

    async def test_restart_reconstructs_binding_and_replay(self):
        first = await self.reserve()
        fresh = CallingLedger(self.commands)
        _, observed = await fresh.get(principal(), first.command_id)
        self.assertEqual(observed.command_id, first.command_id)
        replay = await fresh.replay(principal(), originate(), "test-correlation-0001")
        self.assertTrue(replay.duplicate)
        with self.assertRaises(CommandConflict):
            await fresh.replay(principal(), originate(destination="internal:OTHER"), "test-correlation-0001")

    async def test_outbox_failure_rolls_back_and_does_not_consume_grant(self):
        await self.pool.execute("""
            CREATE FUNCTION reject_calling_test_outbox() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN RAISE EXCEPTION 'synthetic outbox failure'; END $$;
            CREATE TRIGGER reject_calling_test_outbox BEFORE INSERT ON middleware_outbox
            FOR EACH ROW EXECUTE FUNCTION reject_calling_test_outbox();
        """)
        with self.assertRaises(asyncpg.PostgresError):
            await self.reserve()
        self.assertEqual(await self.counts(), (0, 0, 0))
        await self.pool.execute("DROP TRIGGER reject_calling_test_outbox ON middleware_outbox")
        await self.reserve()
        self.assertEqual(await self.counts(), (1, 1, 1))


if __name__ == "__main__":
    unittest.main()
