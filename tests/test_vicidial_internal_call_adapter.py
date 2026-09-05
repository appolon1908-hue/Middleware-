"""Contract tests for Middleware -> restricted Server B calls; no live call."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from app.calling_contract import CAPABILITY, CLIENT_ID, HANGUP, ORIGINATE, CallingGrant, CallPrincipal
from app.temporal_workflows import CommandExecutionRequest
from app.vicidial_internal_call_adapter import (
    VicidialInternalCallAdapter, VicidialInternalCallError,
    VicidialInternalCallUnknown,
)

SOURCE_SHA = "a" * 40
SECRET = b"synthetic-hmac-value-with-32-bytes-minimum"


@pytest.fixture(autouse=True)
def emulate_root_owned_policy(monkeypatch):
    """CI is non-root; only the fstat ownership observation is synthesized."""
    actual_fstat = os.fstat

    def root_fstat(descriptor):
        value = actual_fstat(descriptor)
        return SimpleNamespace(
            st_mode=value.st_mode, st_uid=0, st_size=value.st_size,
        )

    monkeypatch.setattr("app.calling_contract.os.fstat", root_fstat)


def principal():
    return CallPrincipal(tenant_id="tenant-test", subject="subject-appolon",
                         employee_id="employee-appolon", campaign_id="TEST_SYN",
                         business_unit="business-test", extension="6901")


def policy(path: Path):
    now = datetime.now(UTC)
    grant = CallingGrant(
        authorization_reference="CHG-APPOLON-TEST-0001", principal=principal(),
        destination="internal:TEST_ECHO", caller_id="+12025550123", lead_id=17,
        not_before=now-timedelta(minutes=1), expires_at=now+timedelta(minutes=10),
        source_sha=SOURCE_SHA,
    )
    path.write_text(grant.model_dump_json())
    path.chmod(0o600)
    return grant


def command(grant):
    return CommandExecutionRequest(
        command_id="11111111-1111-5111-8111-111111111111",
        command_type=ORIGINATE, command_version="1.0", target="vicidial-restricted",
        tenant_id="tenant-test", requested_by="subject-appolon",
        correlation_id="correlation-appolon-0001", idempotency_key="originate-appolon-0001",
        capability=CAPABILITY, authenticated_client_id=CLIENT_ID,
        payload={
            "actor": principal().model_dump(mode="json"),
            "originate": {
                "employee_id": "employee-appolon", "campaign": "TEST_SYN",
                "business_unit": "business-test", "destination": "internal:TEST_ECHO",
                "destination_class": "internal_test", "destination_country": "ZZ",
                "destination_timezone": "UTC", "caller_id": "+12025550123",
                "lead_model": "crm.lead", "lead_id": 17, "recording_requested": False,
            },
            "authorization_reference": grant.authorization_reference,
            "policy_sha256": grant.digest(),
        },
    )


def hangup_command(grant):
    original = command(grant)
    return CommandExecutionRequest(
        command_id="22222222-2222-5222-8222-222222222222",
        command_type=HANGUP, command_version="1.0", target="vicidial-restricted",
        tenant_id=original.tenant_id, requested_by=original.requested_by,
        correlation_id=original.correlation_id, idempotency_key="hangup-appolon-0001",
        capability=CAPABILITY, authenticated_client_id=CLIENT_ID,
        payload={
            **original.payload, "origin_operation_id": original.command_id,
            "call_id": "codestra-unique-1", "reason": "Agent hangup",
        },
    )


def environment(tmp_path):
    secret = tmp_path / "hmac"
    secret.write_bytes(SECRET)
    secret.chmod(0o600)
    grant = policy(tmp_path / "policy.json")
    return grant, {
        "CODESTRA_INTERNAL_CALL_POLICY_FILE": str(tmp_path / "policy.json"),
        "VICIDIAL_INTERNAL_CALL_BASE_URL": "https://server-b.internal",
        "VICIDIAL_INTERNAL_CALL_EXPECTED_HOST": "server-b.internal",
        "VICIDIAL_INTERNAL_CALL_HMAC_FILE": str(secret),
        "VICIDIAL_INTERNAL_CALL_SERVICE_IDENTITY": "codestra-middleware",
    }


def test_downstream_contract_lock_matches_adapter_routes():
    lock = json.loads(Path("config/vicidial-internal-call-contract.lock.json").read_text())
    assert lock["tested_sha"] == "170bc10fa135b85a34831799399e469cfc42c373"
    assert lock["protected_release"] is False
    assert lock["routes"] == {
        "originate": VicidialInternalCallAdapter.ORIGINATE_PATH,
        "readback": "/v1/calls/internal/{operation_id}",
        "hangup": "/v1/calls/internal/{operation_id}/hangup",
    }


@pytest.mark.asyncio
async def test_exact_hmac_v2_backend_path_and_body(tmp_path):
    grant, env = environment(tmp_path)
    captured = []

    async def endpoint(request):
        raw = await request.aread()
        captured.append((request, raw))
        return httpx.Response(200, request=request, json={
            "status": "accepted", "operation_id": command(grant).command_id,
            "asterisk_uniqueid": "codestra-unique-1", "created_at": "2026-09-05T19:00:00Z",
            "duplicate": False,
        })

    client = httpx.AsyncClient(transport=httpx.MockTransport(endpoint))
    adapter = VicidialInternalCallAdapter(SimpleNamespace(source_sha=SOURCE_SHA), env, client)
    result = await adapter.execute(command(grant))
    assert result.status == "accepted"
    request, body = captured[0]
    timestamp = request.headers["X-Request-Timestamp"]
    nonce = request.headers["X-Request-Nonce"]
    canonical = "\n".join((
        "v2", "POST", "/v1/calls/internal/originate", "codestra-middleware",
        "telephony:internal-call", timestamp, nonce, command(grant).command_id,
        hashlib.sha256(body).hexdigest(),
    ))
    assert hmac.compare_digest(
        request.headers["X-Request-Signature"],
        hmac.new(SECRET, canonical.encode(), hashlib.sha256).hexdigest(),
    )
    assert request.url.path == "/v1/calls/internal/originate"
    assert json.loads(body)["destination"] == "internal:TEST_ECHO"
    await client.aclose()


@pytest.mark.asyncio
async def test_timeout_is_unknown_and_never_self_retries(tmp_path):
    grant, env = environment(tmp_path)
    attempts = 0
    async def endpoint(request):
        nonlocal attempts
        attempts += 1
        raise httpx.ReadTimeout("synthetic", request=request)
    client = httpx.AsyncClient(transport=httpx.MockTransport(endpoint))
    adapter = VicidialInternalCallAdapter(SimpleNamespace(source_sha=SOURCE_SHA), env, client)
    with pytest.raises(VicidialInternalCallUnknown):
        await adapter.execute(command(grant))
    assert attempts == 1
    await client.aclose()


@pytest.mark.asyncio
async def test_policy_change_after_enqueue_fails_before_network(tmp_path):
    grant, env = environment(tmp_path)
    called = False
    async def endpoint(request):
        nonlocal called
        called = True
        return httpx.Response(500, request=request)
    changed = grant.model_copy(update={"lead_id": 18})
    Path(env["CODESTRA_INTERNAL_CALL_POLICY_FILE"]).write_text(changed.model_dump_json())
    client = httpx.AsyncClient(transport=httpx.MockTransport(endpoint))
    adapter = VicidialInternalCallAdapter(SimpleNamespace(source_sha=SOURCE_SHA), env, client)
    with pytest.raises(VicidialInternalCallError, match="changed"):
        await adapter.execute(command(grant))
    assert called is False
    await client.aclose()


@pytest.mark.parametrize("field,value", [
    ("extension", "6101"), ("campaign_id", "PRODUCTION"),
])
def test_wrong_identity_is_rejected(field, value, tmp_path):
    grant, env = environment(tmp_path)
    request = command(grant)
    actor = request.payload["actor"] | {field: value}
    request = CommandExecutionRequest(**{**request.__dict__, "payload": request.payload | {"actor": actor}})
    adapter = VicidialInternalCallAdapter(SimpleNamespace(source_sha=SOURCE_SHA), env,
                                          httpx.AsyncClient(transport=httpx.MockTransport(lambda r: None)))
    with pytest.raises(VicidialInternalCallError):
        adapter._originate(request)


@pytest.mark.asyncio
@pytest.mark.parametrize("change", [
    "requested_by", "tenant_id", "actor_extension", "destination",
])
async def test_hangup_binding_mismatch_fails_before_network(change, tmp_path):
    grant, env = environment(tmp_path)
    request = hangup_command(grant)
    values = request.__dict__.copy()
    if change == "requested_by":
        values["requested_by"] = "subject-other"
    elif change == "tenant_id":
        values["tenant_id"] = "tenant-other"
    elif change == "actor_extension":
        values["payload"] = request.payload | {
            "actor": request.payload["actor"] | {"extension": "6101"},
        }
    else:
        values["payload"] = request.payload | {
            "originate": request.payload["originate"] | {"destination": "internal:OTHER"},
        }
    request = CommandExecutionRequest(**values)
    called = False

    async def endpoint(http_request):
        nonlocal called
        called = True
        return httpx.Response(200, request=http_request, json={})

    client = httpx.AsyncClient(transport=httpx.MockTransport(endpoint))
    adapter = VicidialInternalCallAdapter(SimpleNamespace(source_sha=SOURCE_SHA), env, client)
    with pytest.raises(VicidialInternalCallError, match="hangup"):
        await adapter.execute(request)
    assert called is False
    await client.aclose()
