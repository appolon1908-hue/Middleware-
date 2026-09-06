import asyncio
import os
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.v1 import telephony
from app.api.v1.telephony import OriginateCallRequest
from app.core.config import settings
from app.core.webrtc_production_policy import Decision
from app.db.models import AuditEvent, TelephonyCallLifecycle

AGENT_IDENTITY = {
    "campaign_ids": ["TEST_SYN"],
    "endpoint": "6101",
    "vicidial_username": "agent.syn",
    "business_unit_id": "COD",
}


def _request(**overrides) -> OriginateCallRequest:
    # Every call gets a fresh idempotency key by default -- tests that
    # specifically exercise replay pass their own matching key explicitly.
    values = {
        "idempotency_key": f"originate-test-key-{uuid4().hex}",
        "employee_id": "EMP-001",
        "campaign": "TEST_SYN",
        "business_unit": "COD",
        "destination": "+15551234567",
        "destination_class": "mobile",
        "destination_country": "US",
        "destination_timezone": "America/New_York",
        "caller_id": "+15557654321",
        "lead_model": "crm.lead",
        "lead_id": 42,
    }
    values.update(overrides)
    return OriginateCallRequest(**values)


def test_originate_fails_closed_while_policy_is_default_deny(monkeypatch):
    database_url = os.environ.get("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("requires an explicitly provisioned disposable database")
    assert "diag" in database_url or "rehearsal" in database_url
    asyncio.run(_scenario_default_deny(database_url, monkeypatch))


async def _scenario_default_deny(database_url: str, monkeypatch) -> None:
    monkeypatch.setattr(
        telephony,
        "_lookup_agent_assignment",
        AsyncMock(return_value=dict(AGENT_IDENTITY)),
    )
    engine = create_async_engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            response = await telephony.originate_call(_request(), session, None)

        # The checked-in policy file is enabled=false/kill_switch=true, so
        # this must never reach ALLOW no matter how well-formed the request
        # is -- that is the whole point of shipping this endpoint while
        # LIVE_PSTN_DIALING stays false.
        assert response["policy_decision"] != Decision.ALLOW.value
        assert response["dialing"] == "blocked"
        assert response["lifecycle_state"] == "STARTED"
        assert response["call_id"]
        assert response["correlation_id"]

        async with factory() as session:
            lifecycle = (
                await session.execute(
                    select(TelephonyCallLifecycle).where(
                        TelephonyCallLifecycle.correlation_id
                        == response["correlation_id"]
                    )
                )
            ).scalar_one()
            assert lifecycle.destination == "+15551234567"
            assert lifecycle.source_extension == "6101"

            audit = (
                await session.execute(
                    select(AuditEvent).where(
                        AuditEvent.subject == response["call_id"]
                    )
                )
            ).scalar_one()
            assert audit.action == "telephony.calls.originate"
            assert audit.redacted_payload["employee_id"] == "EMP-001"
            assert "destination" not in audit.redacted_payload
    finally:
        await engine.dispose()


def test_originate_is_idempotent_on_replay(monkeypatch):
    database_url = os.environ.get("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("requires an explicitly provisioned disposable database")
    assert "diag" in database_url or "rehearsal" in database_url
    asyncio.run(_scenario_idempotent_replay(database_url, monkeypatch))


async def _scenario_idempotent_replay(database_url: str, monkeypatch) -> None:
    lookup = AsyncMock(return_value=dict(AGENT_IDENTITY))
    monkeypatch.setattr(telephony, "_lookup_agent_assignment", lookup)
    engine = create_async_engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        request = _request(idempotency_key="originate-replay-key-000000001")
        async with factory() as session:
            first = await telephony.originate_call(request, session, None)
        async with factory() as session:
            second = await telephony.originate_call(request, session, None)
        assert first == second
        # The identity lookup (and every check downstream of it) must not
        # run again on replay -- only the first call should have hit it.
        assert lookup.await_count == 1

        async with factory() as session:
            count = await session.scalar(
                select(TelephonyCallLifecycle.id).where(
                    TelephonyCallLifecycle.correlation_id
                    == first["correlation_id"]
                )
            )
            assert count is not None
    finally:
        await engine.dispose()


def test_originate_rejects_production_campaign(monkeypatch):
    database_url = os.environ.get("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("requires an explicitly provisioned disposable database")
    assert "diag" in database_url or "rehearsal" in database_url
    asyncio.run(_scenario_production_campaign_rejected(database_url, monkeypatch))


async def _scenario_production_campaign_rejected(
    database_url: str, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "allow_non_test_campaigns", False)
    engine = create_async_engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        from fastapi import HTTPException

        async with factory() as session:
            with pytest.raises(HTTPException) as exc:
                await telephony.originate_call(
                    _request(campaign="PROD_CAMPAIGN"), session, None
                )
        assert exc.value.status_code == 403
    finally:
        await engine.dispose()


def test_originate_rejects_agent_not_assigned_to_campaign(monkeypatch):
    database_url = os.environ.get("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("requires an explicitly provisioned disposable database")
    assert "diag" in database_url or "rehearsal" in database_url
    asyncio.run(_scenario_unauthorized_campaign(database_url, monkeypatch))


async def _scenario_unauthorized_campaign(database_url: str, monkeypatch) -> None:
    unauthorized_identity = dict(AGENT_IDENTITY)
    unauthorized_identity["campaign_ids"] = ["SOME_OTHER_CAMPAIGN"]
    monkeypatch.setattr(
        telephony,
        "_lookup_agent_assignment",
        AsyncMock(return_value=unauthorized_identity),
    )
    engine = create_async_engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        from fastapi import HTTPException

        async with factory() as session:
            with pytest.raises(HTTPException) as exc:
                await telephony.originate_call(
                    _request(idempotency_key="originate-unauth-key-00000001"),
                    session,
                    None,
                )
        assert exc.value.status_code == 403
    finally:
        await engine.dispose()


def test_originate_rejects_invalid_destination(monkeypatch):
    database_url = os.environ.get("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("requires an explicitly provisioned disposable database")
    assert "diag" in database_url or "rehearsal" in database_url
    asyncio.run(_scenario_invalid_destination(database_url, monkeypatch))


async def _scenario_invalid_destination(database_url: str, monkeypatch) -> None:
    monkeypatch.setattr(
        telephony,
        "_lookup_agent_assignment",
        AsyncMock(return_value=dict(AGENT_IDENTITY)),
    )
    engine = create_async_engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        from fastapi import HTTPException

        async with factory() as session:
            with pytest.raises(HTTPException) as exc:
                await telephony.originate_call(
                    _request(
                        idempotency_key="originate-baddest-key-000000001",
                        destination="not-a-phone-number",
                    ),
                    session,
                    None,
                )
        assert exc.value.status_code == 422
    finally:
        await engine.dispose()
