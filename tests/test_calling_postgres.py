"""Real PostgreSQL atomicity tests. Only an explicit disposable local DB is allowed."""
from __future__ import annotations

import asyncio
import os
import unittest
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

import asyncpg

from app.calling_ledger import CallingLedger
from app.commands import (
    AUTHENTICATED_CLIENT_ID_KEY, CommandConflict, CommandNotFound, CommandPolicyRegistry,
    CommandService, PostgresCommandStore,
)
from app.temporal_activities import CommandLedgerWorkflowActivities
from app.temporal_workflows import (
    ActivityResult, CommandExecutionRequest, ReconciliationRequest,
)
from tests.test_calling_contract import grant, originate, principal

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

    async def test_two_worker_activities_acquire_one_durable_dispatch_claim(self):
        operation = await self.reserve()
        for state in ("queued", "dispatching"):
            await self.store.transition(
                operation.tenant_id, operation.command_id, new_state=state,
                actor_id="test-worker", reason="synthetic dispatch setup",
            )
        row = await self.pool.fetchrow(
            "SELECT payload FROM middleware_commands WHERE tenant_id=$1 AND command_id=$2",
            operation.tenant_id, str(operation.command_id),
        )
        payload = row["payload"] if isinstance(row["payload"], dict) else __import__("json").loads(row["payload"])
        client_id = payload.pop(AUTHENTICATED_CLIENT_ID_KEY)
        request = CommandExecutionRequest(**payload, authenticated_client_id=client_id)

        class Adapter:
            def __init__(self):
                self.executions = 0
                self.readbacks = 0
            async def execute(self, _request):
                self.executions += 1
                return ActivityResult("accepted", "synthetic accepted", "provider-id")
            async def readback(self, _request):
                self.readbacks += 1
                return ActivityResult("mismatch", "synthetic pending", "provider-id")

        adapter = Adapter()
        first = CommandLedgerWorkflowActivities(self.store, vicidial_internal=adapter)  # type: ignore[arg-type]
        second = CommandLedgerWorkflowActivities(self.store, vicidial_internal=adapter)  # type: ignore[arg-type]
        await first.execute_command(request)
        await second.execute_command(request)
        self.assertEqual(adapter.executions, 1)
        self.assertEqual(adapter.readbacks, 1)
        state, result_payload = await self.pool.fetchrow(
            "SELECT state,result_payload FROM middleware_command_attempts WHERE tenant_id=$1 AND command_id=$2",
            operation.tenant_id, str(operation.command_id),
        )
        self.assertEqual(state, "dispatching")
        value = result_payload if isinstance(result_payload, dict) else __import__("json").loads(result_payload)
        self.assertEqual(value, {"dispatch_claimed": True})

    async def test_completed_hangup_restart_repairs_origin_without_new_mutation(self):
        original = await self.reserve()
        for state in ("queued", "dispatching", "accepted", "readback_pending",
                      "reconciliation_required"):
            original = await self.store.transition(
                original.tenant_id, original.command_id, new_state=state,
                actor_id="test-worker", reason="synthetic restart boundary",
                provider_operation_id=("codestra-" + "a" * 32)
                if state == "accepted" else None,
            )
        hangup = await self.ledger.hangup(
            principal(), original.command_id, key="hangup-restart-0001",
            expected_version=original.resource_version, reason="Agent hangup",
        )
        fresh_ledger = CallingLedger(self.commands)
        document, observed = await fresh_ledger.get(principal(), hangup.command_id)
        self.assertEqual(document.payload["origin_operation_id"], str(original.command_id))
        self.assertEqual(observed.command_id, hangup.command_id)
        wrong = principal().model_copy(update={"subject": "subject-other"})
        with self.assertRaises(CommandNotFound):
            await fresh_ledger.get(wrong, hangup.command_id)

        for state in ("queued", "dispatching", "accepted", "readback_pending",
                      "reconciliation_required"):
            hangup = await self.store.transition(
                hangup.tenant_id, hangup.command_id, new_state=state,
                actor_id="test-worker", reason="synthetic interrupted hangup",
                provider_operation_id=("codestra-" + "a" * 32)
                if state == "accepted" else None,
            )
        now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        evidence = {
            "operation_id": str(original.command_id),
            "correlation_id": "test-correlation-0001", "dispatch_state": "accepted",
            "asterisk_uniqueid": "codestra-" + "a" * 32,
            "linkedid": "codestra-" + "a" * 32, "call_id": "call-test-1",
            "call_state": "completed", "answered_at": now, "ended_at": now,
            "terminal": True,
            "evidence": {"event_sequence": [{"sequence": 1}],
                         "evidence_source": "ami-lifecycle-gateway"},
            "tenant_id": "tenant-test", "subject": "subject-appolon",
            "employee_id": "employee-appolon", "username": "appolon",
            "extension": "6901", "campaign": "TEST_SYN",
            "authorization_reference": self.grant.authorization_reference,
            "created_at": now, "duration_seconds": 1,
            "talk_duration_seconds": 1, "hangup_cause": "Normal Clearing",
            "hangup_cause_code": 16, "internal_only": True,
            "external_dialing": False, "recording": False,
        }

        class NoMutationAdapter:
            executions = 0
            readbacks = 0
            async def execute(self, _request):
                self.executions += 1
                raise AssertionError("restart recovery must not mutate Server B")
            async def readback(self, _request):
                self.readbacks += 1
                raise AssertionError("completed hangup recovery uses persisted evidence")

        adapter = NoMutationAdapter()
        interrupted = CommandLedgerWorkflowActivities(
            self.store, vicidial_internal=adapter,  # type: ignore[arg-type]
        )
        request = ReconciliationRequest(
            str(hangup.command_id), hangup.tenant_id, "synthetic crash boundary",
        )
        command, _, digest = await interrupted._load_reconciliation_command(request)
        self.assertIsNotNone(command)
        self.assertIsNotNone(digest)
        await interrupted._persist_reconciliation_result(
            request, ActivityResult("matched", "terminal hangup", evidence["asterisk_uniqueid"], evidence),
            digest,  # type: ignore[arg-type]
        )
        self.assertEqual((await self.store.get(original.tenant_id, original.command_id)).state,
                         "reconciliation_required")

        restarted = CommandLedgerWorkflowActivities(
            self.store, vicidial_internal=adapter,  # type: ignore[arg-type]
        )
        await restarted.reconcile_operation(request)
        audit_count = await self.pool.fetchval(
            "SELECT count(*) FROM middleware_command_audit WHERE tenant_id=$1",
            original.tenant_id,
        )
        await restarted.reconcile_operation(request)
        self.assertEqual(await self.pool.fetchval(
            "SELECT count(*) FROM middleware_command_audit WHERE tenant_id=$1",
            original.tenant_id,
        ), audit_count)
        self.assertEqual((await self.store.get(original.tenant_id, original.command_id)).state,
                         "completed")
        self.assertEqual((await self.store.get(hangup.tenant_id, hangup.command_id)).state,
                         "completed")
        self.assertEqual((adapter.executions, adapter.readbacks), (0, 0))
        with self.assertRaises(CommandConflict):
            await self.reserve(originate(idempotency_key="test-originate-after-hangup"))


if __name__ == "__main__":
    unittest.main()
