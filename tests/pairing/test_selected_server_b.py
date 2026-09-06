"""Paired-source test against an exact checked-out Server B implementation.

The test imports Server B itself. Only its AMI transport is synthetic; HTTP
authentication, routes, policy enforcement, idempotency, audit, and SQLite
persistence are the selected source's real implementations.
"""
from __future__ import annotations

import os
import sqlite3
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from app.vicidial_internal_call_adapter import VicidialInternalCallAdapter
from app.calling_contract import CallPrincipal, CallingGrant
from tests.test_vicidial_internal_call_adapter import SECRET, SOURCE_SHA, command, environment


SERVER_B_SHA = "9ac8ef4840f78ba4ad9b816e4e409298505103ce"
SERVER_B_ROOT_VALUE = os.environ.get("CODESTRA_SELECTED_SERVER_B_ROOT")
SERVER_B_ROOT = Path(SERVER_B_ROOT_VALUE) if SERVER_B_ROOT_VALUE else None

pytestmark = pytest.mark.skipif(
    SERVER_B_ROOT is None or not SERVER_B_ROOT.is_dir(),
    reason="set CODESTRA_SELECTED_SERVER_B_ROOT to the exact Server B checkout",
)


@pytest.mark.asyncio
async def test_real_selected_server_b_hmac_routes_policy_and_persistence(tmp_path):
    assert os.environ.get("CODESTRA_SELECTED_SERVER_B_SHA") == SERVER_B_SHA
    assert SERVER_B_ROOT is not None
    sys.path.insert(0, str(SERVER_B_ROOT / "vicidial" / "src"))
    sys.path.insert(0, str(SERVER_B_ROOT / "vicidial" / "tests"))
    try:
        from codestra_vicidial.app import create_app
        from codestra_vicidial.repository import MemoryRepository
        from codestra_vicidial.security import RequestAuthenticator
        from codestra_vicidial.service import AdapterService, FeatureFlags
        from codestra_vicidial.state import StateStore
        from test_internal_calling import executor, seed_connected

        server_root = tmp_path / "server-b"
        middleware_root = tmp_path / "middleware"
        server_root.mkdir()
        middleware_root.mkdir()
        server, ami, lifecycle = executor(server_root)
        auth = RequestAuthenticator(
            "codestra-middleware", SECRET, frozenset({"127.0.0.1"}),
        )
        app = create_app(
            AdapterService(
                MemoryRepository(),
                StateStore(tmp_path / "adapter-state.sqlite3"),
                FeatureFlags(),
            ),
            auth,
            internal_call_executor=server,
        )

        _, env = environment(middleware_root)
        actor = CallPrincipal(
            tenant_id="tenant-test", subject="subject-appolon",
            employee_id="employee-appolon", campaign_id="TEST_SYN",
            business_unit="synthetic-unit", extension="6901",
        )
        now = datetime.now(UTC)
        grant = CallingGrant(
            authorization_reference="CHG-APPOLON-INTERNAL-0001",
            principal=actor, destination="internal:TEST_ECHO",
            caller_id="+12025550123", lead_id=17,
            not_before=now - timedelta(minutes=1),
            expires_at=now + timedelta(minutes=10), source_sha=SOURCE_SHA,
        )
        Path(env["CODESTRA_INTERNAL_CALL_POLICY_FILE"]).write_text(
            grant.model_dump_json()
        )
        client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, client=("127.0.0.1", 50000)),
            base_url="https://server-b.internal",
        )
        adapter = VicidialInternalCallAdapter(
            SimpleNamespace(source_sha=SOURCE_SHA), env, client,
        )

        base = command(grant)
        request = type(base)(**{
            **base.__dict__,
            "payload": {
                **base.payload,
                "actor": actor.model_dump(mode="json"),
                "originate": {
                    **base.payload["originate"],
                    "business_unit": "synthetic-unit",
                },
            },
        })
        accepted = await adapter.execute(request)
        assert accepted.status == "accepted"
        assert len(ami.actions) == 1
        duplicate = await adapter.execute(request)
        assert duplicate.status == "accepted"
        assert len(ami.actions) == 1

        seed_connected(lifecycle, accepted.provider_operation_id)
        pending = await adapter.readback(request)
        assert pending.status == "mismatch"

        with sqlite3.connect(server.state_path) as db:
            call = db.execute(
                "SELECT operation_id,state FROM internal_calls"
            ).fetchone()
        assert call == (request.command_id, "accepted")
        with sqlite3.connect(server.audit_path) as db:
            outcomes = db.execute(
                "SELECT outcome FROM audit WHERE operation='internal-call.originate' "
                "ORDER BY sequence"
            ).fetchall()
        assert outcomes == [("requested",), ("accepted",), ("requested",), ("duplicate",)]
        await client.aclose()
    finally:
        del sys.path[:2]
