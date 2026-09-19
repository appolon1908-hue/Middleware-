"""LOCAL_CORE_CONTRACT_TEST: the whole chain, from local source and in process.

Static chain — for the contract operations whose calling client is a concrete
Keycloak service client, the same request is followed through every repository:
Caddy hands the path to Kong; Kong owns exactly one route for it on the
canonical 8095 upstream with the contract's issuer, audience, scope and azp;
Keycloak defines that client as a confidential service account with the
Middleware audience; Middleware registers the operation in the deployed
integration profile and its contract names the same authentication.

In-process chain — the Middleware application itself, with in-memory stores:
an unauthenticated or wrong-client request to a contract route fails closed
(401/422) and still echoes X-Correlation-ID; a hundred identical automation
job claims (same Idempotency-Key, same body) yield one lease and one job.
"""

from __future__ import annotations

import base64
import json
from typing import Any

import httpx
import pytest

from app.automation_policy import AutomationPolicy
from app.automation_v2 import (
    AutomationService,
    MemoryAutomationStore,
    WorkflowRoute,
    WorkflowRouter,
)
from app.commands import CommandPolicyRegistry, CommandService, MemoryCommandStore
from app.core.runtime import RuntimeContainer
from app.main import create_app
from app.models import EventEnvelope
from app.replay import MemoryReplayGuard
from app.storage import MemoryInboxStore
from tests.cross_repo.conftest import load_json

CONCRETE_OPERATIONS = {
    ("POST", "/api/v1/automation/policy-check"): (
        "n8n-automation",
        "n8n.policy.check",
        "n8n-service-jwt",
    ),
    ("POST", "/api/v1/integrations/n8n/results"): (
        "n8n-automation",
        "n8n.results.submit",
        "n8n-service-jwt",
    ),
    ("GET", "/api/v1/integrations/n8n/results/{event_id}"): (
        "n8n-automation",
        "n8n.results.read",
        "n8n-service-jwt",
    ),
    ("GET", "/api/v1/integrations/odoo/campaigns/{campaign_id}"): (
        "odoo-integration",
        "odoo.campaigns.read",
        "odoo-service-jwt",
    ),
    ("POST", "/api/v1/odoo/events"): (
        "odoo-integration",
        "odoo.events.publish",
        "odoo-service-jwt",
    ),
}


@pytest.fixture(scope="module")
def registry():
    from app.application import AppProfile, create_app as build
    from app.router_registry import route_operations

    app = build(profile=AppProfile.INTEGRATION)
    return set(route_operations(app))


def test_static_chain_for_every_concrete_client_operation(matrix, repos, registry):
    rows = {(r["METHOD"], r["PATH"]): r for r in matrix["rows"]}
    clients = {
        doc["clientId"]: doc
        for doc in (
            load_json(p)
            for p in (repos["Keycloak"] / "config" / "clients").glob("*.json")
        )
    }
    kong_policy = {
        r["routeId"]: r
        for r in load_json(repos["Kong"] / "config" / "kong-access-policy.v1.json")[
            "routes"
        ]
    }
    for (method, path), (client_id, scope, auth) in CONCRETE_OPERATIONS.items():
        row = rows[(method, path)]
        # Middleware contract
        assert (
            row["CALLING_CLIENT"] == client_id
            and row["SCOPE"] == scope
            and row["MIDDLEWARE_AUTH"] == auth
        )
        assert (
            row["AUDIENCE"] == "middleware-api"
            and row["UPSTREAM"] == "middleware-integration-api:8095"
        )
        # Caddy → Kong
        assert row["CADDY_TO_KONG"] is True
        # Kong route + authority
        assert (
            row["KONG_ROUTE"] not in ("", "MISSING")
            and row["KONG_UPSTREAM"] == "middleware-integration-api:8095"
        )
        assert (
            row["KONG_SCOPE"] == scope
            and row["KONG_AUDIENCE"] == "middleware-api"
            and row["KONG_AZP"] == client_id
        )
        assert row["KONG_AUTH"] == auth
        policy = kong_policy[row["KONG_ROUTE"]]
        assert (
            policy["requiredScopes"] == [scope]
            and policy["contractExpectedAzp"] == client_id
        )
        assert policy["failurePolicy"] == "FAIL_CLOSED_V1"
        # Keycloak client
        client = clients[client_id]
        assert (
            client["serviceAccountsEnabled"]
            and not client["publicClient"]
            and not client["fullScopeAllowed"]
        )
        assert any(
            m["config"].get("included.custom.audience") == "middleware-api"
            for m in client["protocolMappers"]
        )
        # Middleware registers the operation in the deployed integration profile
        assert (method, path) in registry, (
            f"{method} {path} is not served by the integration profile"
        )
        # Correlation and idempotency carriers agree with what N8N/Odoo send
        assert row["CORRELATION_REQUIRED"] is True
        if method == "POST":
            assert row["IDEMPOTENCY_REQUIRED"] is True and row[
                "IDEMPOTENCY_CARRIER"
            ] in {"Idempotency-Key", "body.event_id"}


# --- in-process Middleware behaviour -------------------------------------------------------


class RouteBoundVerifier:
    """Accepts only a token whose azp is the client the route expects, like Keycloak +
    Kong + the request guard would; everything else is an authentication error."""

    async def verify(
        self, authorization: str, *, expected_client_id: str, required_scope: str
    ) -> dict[str, Any]:
        from app.security import AuthenticationError

        try:
            encoded = authorization.removeprefix("Bearer ").split(".")[1]
            payload = json.loads(
                base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
            )
        except Exception as exc:  # noqa: BLE001
            raise AuthenticationError("malformed token") from exc
        if payload.get("azp") != expected_client_id:
            raise AuthenticationError("authorized party denied")
        return {
            "iss": "https://auth.codestra.co/realms/codestra",
            "aud": "middleware-api",
            "azp": expected_client_id,
            "scope": required_scope,
            "sub": f"service-account-{expected_client_id}",
        }

    async def ready(self) -> bool:
        return True


def bearer(client_id: str) -> str:
    def segment(value: dict[str, Any]) -> str:
        return (
            base64.urlsafe_b64encode(json.dumps(value, separators=(",", ":")).encode())
            .rstrip(b"=")
            .decode()
        )

    return f"Bearer {segment({'alg': 'RS256'})}.{segment({'azp': client_id})}.sig"


def route() -> WorkflowRoute:
    return WorkflowRoute(
        event_type="codestra.email.message.delivered",
        workflow_key="klyrow.email.delivery-reconcile.v1",
        workflow_family="messaging.email",
        workflow_version=1,
        client_id="n8n-messaging-automation",
        max_attempts=3,
        external_effect=False,
    )


def envelope() -> EventEnvelope:
    from datetime import UTC, datetime

    return EventEnvelope.model_construct(
        event_id="event-core-contract-0001",
        event_type="codestra.email.message.delivered",
        event_version="1.0",
        occurred_at=datetime(2026, 9, 19, 12, 0, tzinfo=UTC),
        received_at=datetime(2026, 9, 19, 12, 0, 1, tzinfo=UTC),
        source="klyrow-gateway",
        tenant_id="tenant-1",
        correlation_id="corr-core-contract-0001",
        causation_id="cause-core-contract-0001",
        idempotency_key="event-core-contract-0001",
        payload={"message_id": "m-1"},
        metadata={},
    )


@pytest.fixture
def local_app(test_settings):
    commands = CommandService(
        store=MemoryCommandStore(), policies=CommandPolicyRegistry.load()
    )
    store = MemoryAutomationStore()
    automation = AutomationService(
        store=store,
        policy=AutomationPolicy.from_path(),
        workflow_router=WorkflowRouter.load(),
        commands=commands,
        umbrella_controls=test_settings.umbrella_controls,
    )
    runtime = RuntimeContainer(
        settings=test_settings,
        inbox=MemoryInboxStore(),
        replay=MemoryReplayGuard(),
        tokens=RouteBoundVerifier(),
        commands=commands,
        automation=automation,
    )
    return create_app(settings=test_settings, runtime=runtime), store


@pytest.mark.asyncio
async def test_unauthenticated_and_wrong_client_requests_fail_closed_with_correlation_echo(
    local_app,
):
    app, _ = local_app
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            anonymous = await client.get(
                "/v2/automation/capabilities/crm",
                headers={
                    "X-Correlation-ID": "corr-anon-1",
                    "X-Tenant-ID": "tenant-1",
                    "X-Request-ID": "req-anon-1",
                },
            )
            assert anonymous.status_code == 401, anonymous.text
            assert anonymous.headers.get("x-correlation-id") == "corr-anon-1"
            wrong = await client.get(
                "/v2/automation/capabilities/crm",
                headers={
                    "Authorization": bearer("odoo-integration"),
                    "X-Correlation-ID": "corr-wrong-1",
                    "X-Tenant-ID": "tenant-1",
                    "X-Request-ID": "req-wrong-1",
                },
            )
            assert wrong.status_code in {401, 403}, wrong.text
            assert wrong.headers.get("x-correlation-id") == "corr-wrong-1"
            # The automation surface answers every failure with the one error envelope.
            for response in (anonymous, wrong):
                error = response.json()["error"]
                assert set(error) >= {"code", "message", "correlation_id", "retryable"}
                assert error["correlation_id"] == response.headers["x-correlation-id"]
                assert error["retryable"] is False
            # A missing required header is refused before any work, with the same envelope.
            missing = await client.get(
                "/v2/automation/capabilities/crm",
                headers={"X-Correlation-ID": "corr-missing-1"},
            )
            assert (
                missing.status_code == 400
                and missing.json()["error"]["code"] == "automation_invalid"
            )


@pytest.mark.asyncio
async def test_one_hundred_identical_requests_produce_one_operation(local_app):
    app, store = local_app
    selected = route()
    event = envelope()
    await store.enqueue_event(event, selected, source_client_id=event.source)
    [(tenant_id, job_id)] = list(store.jobs)
    delivery_token = store.dispatches[(tenant_id, job_id)]["delivery_token"]
    body = {
        "tenant_id": event.tenant_id,
        "correlation_id": event.correlation_id,
        "idempotency_key": "idem-core-contract-claim-0001",
        "job_id": str(job_id),
        "delivery_token": delivery_token,
        "workflow_key": selected.workflow_key,
        "workflow_version": 1,
        "execution_id": "00000000-0000-4000-8000-000000000101",
    }
    headers = {
        "Authorization": bearer(selected.client_id),
        "X-Tenant-ID": event.tenant_id,
        "X-Correlation-ID": event.correlation_id,
        "X-Request-ID": "request-core-contract-0001",
        "Idempotency-Key": body["idempotency_key"],
    }
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            responses = [
                await client.post(
                    "/v2/automation/jobs/claim", json=body, headers=headers
                )
                for _ in range(100)
            ]
    statuses = {r.status_code for r in responses}
    assert statuses == {200}, [r.text for r in responses if r.status_code != 200][:2]
    leases = {r.json()["lease_token"] for r in responses}
    assert len(leases) == 1, "every identical claim must return the same lease"
    assert len(store.jobs) == 1 and len(store.dispatches) == 1
    assert all(
        r.headers.get("x-correlation-id") == event.correlation_id for r in responses
    )
