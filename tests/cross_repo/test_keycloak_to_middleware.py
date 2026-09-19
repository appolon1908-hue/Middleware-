"""KEYCLOAK_TO_MIDDLEWARE: the identities Keycloak issues are the ones Middleware verifies.

Two halves. The source half proves the machine clients Middleware, Kong and the
edge contract name exist in Keycloak with the confidential service-account
shape, the Middleware audience and a bounded token lifetime, and that the V3
platform scopes are prepared as optional scopes only. The token half signs real
RS256 tokens with a local key and drives Middleware's ``KeycloakValidator`` —
the same class the request guard uses — through the token contract and its
negative cases (missing audience, wrong azp, expired, scope escalation, wrong
issuer, wrong signature). No Keycloak is contacted.

Known gap (strict xfail, not a pass): the scopes the Middleware/Kong contract
requires from ``n8n-automation`` and ``odoo-integration`` are not issued by
Keycloak's reviewed service-access matrix yet.
"""

from __future__ import annotations

import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from app.core.jwt_auth import JWTAuthError, KeycloakValidator
from tests.cross_repo.conftest import load_json

ISSUER = "https://auth.codestra.co/realms/codestra"
AUDIENCE = "middleware-api"
REQUIRED_CLIENTS = (
    "middleware-api",
    "middleware-worker",
    "n8n-automation",
    "odoo-integration",
    "monitoring-readonly",
)
PLATFORM_SCOPES = (
    "platform.command",
    "platform.command.read",
    "platform.command.replay",
)


def keycloak_clients(repos) -> dict[str, dict]:
    return {
        doc["clientId"]: doc
        for doc in (
            load_json(p)
            for p in sorted((repos["Keycloak"] / "config" / "clients").glob("*.json"))
        )
    }


def audiences(client: dict) -> set[str]:
    return {
        m["config"].get("included.custom.audience")
        for m in client.get("protocolMappers") or []
        if m.get("protocolMapper") == "oidc-audience-mapper"
    }


def hardcoded_scopes(client: dict) -> set[str]:
    return {
        scope
        for m in client.get("protocolMappers") or []
        if m.get("protocolMapper") == "oidc-hardcoded-claim-mapper"
        and m["config"].get("claim.name") == "scope"
        for scope in m["config"].get("claim.value", "").split()
    }


def test_required_machine_clients_exist_once_with_the_service_account_shape(
    repos, summary
):
    clients = keycloak_clients(repos)
    for client_id in REQUIRED_CLIENTS:
        client = clients[client_id]
        assert client["enabled"] is True and client["protocol"] == "openid-connect"
        assert (
            client["serviceAccountsEnabled"] is True and client["publicClient"] is False
        )
        assert (
            client["standardFlowEnabled"] is False
            and client["implicitFlowEnabled"] is False
        )
        assert (
            client["directAccessGrantsEnabled"] is False
            and client["fullScopeAllowed"] is False
        )
        assert int(client["attributes"]["access.token.lifespan"]) <= 300
        assert client["redirectUris"] == [] and client["webOrigins"] == []
    assert summary["KEYCLOAK_CLIENTS"].count("n8n-automation") == 1
    for client_id in (
        "middleware-worker",
        "n8n-automation",
        "odoo-integration",
        "monitoring-readonly",
    ):
        assert AUDIENCE in audiences(clients[client_id]), client_id
    assert "kong-gateway" in clients and AUDIENCE in audiences(clients["kong-gateway"])
    matrix = load_json(
        repos["Keycloak"] / "config" / "contracts" / "service-access-matrix.json"
    )
    assert matrix["issuer"] == ISSUER
    assert matrix["tokenPolicy"]["maximumAccessTokenLifetimeSeconds"] <= 300
    assert (
        matrix["tokenPolicy"]["fullScopeAllowed"] is False
        and matrix["tokenPolicy"]["refreshTokensAllowed"] is False
    )
    assert set(matrix["tokenPolicy"]["requiredClaims"]) >= {
        "iss",
        "sub",
        "aud",
        "azp",
        "iat",
        "exp",
        "jti",
        "scope",
    }


def test_no_client_issues_wildcard_scopes_or_platform_scopes_by_default(repos):
    for client_id, client in keycloak_clients(repos).items():
        scopes = hardcoded_scopes(client)
        assert not any(s in ("*", "") or s.endswith("*") for s in scopes), client_id
        assert not (
            set(client.get("defaultClientScopes") or ()) & set(PLATFORM_SCOPES)
        ), client_id
        assert not (scopes & set(PLATFORM_SCOPES)), client_id


def test_platform_v3_scopes_are_prepared_as_optional_scopes_only(repos, summary):
    for name in PLATFORM_SCOPES + ("metrics.read",):
        doc = load_json(repos["Keycloak"] / "config" / "client-scopes" / f"{name}.json")
        assert (
            doc["attributes"]["include.in.token.scope"] == "true"
            and doc["protocolMappers"] == []
        )
    for entry in summary["V3_PENDING_ROUTES"]:
        assert entry["KEYCLOAK_SCOPE_ISSUED_BY"] == [], (
            "V3 scopes are attached to no client until the contract is frozen"
        )
    monitoring = keycloak_clients(repos)["monitoring-readonly"]
    assert monitoring["optionalClientScopes"] == ["health.read", "metrics.read"]


def test_kong_and_middleware_agree_with_keycloak_on_issuer_and_audience(
    repos, shared_rows
):
    authority = load_json(
        repos["Kong"] / "config" / "kong-middleware-authority.v2.json"
    )
    for route in authority["routes"]:
        assert route["issuer"] == ISSUER
        assert route["audience"] in {AUDIENCE, "codestra-callback-api"}
    assert {row["AUDIENCE"] for row in shared_rows} == {
        AUDIENCE,
        "codestra-callback-api",
    }


@pytest.mark.xfail(
    strict=True,
    reason="KEYCLOAK_SCOPE_GAP: Keycloak's reviewed service-access matrix does not issue the scopes the Middleware/Kong contract requires from n8n-automation (n8n.policy.check, n8n.results.submit, n8n.results.read) and odoo-integration (odoo.campaigns.read); closing it is a Keycloak owner decision",
)
def test_concrete_service_clients_issue_the_scopes_the_contract_requires(
    repos, shared_rows
):
    clients = keycloak_clients(repos)
    gaps = []
    for row in shared_rows:
        client = clients.get(row["CALLING_CLIENT"])
        if client is None:
            continue
        if row["SCOPE"] not in hardcoded_scopes(client):
            gaps.append(
                f"{row['CALLING_CLIENT']} lacks {row['SCOPE']} for {row['METHOD']} {row['PATH']}"
            )
    assert gaps == []


@pytest.mark.xfail(
    strict=True,
    reason="KEYCLOAK_CLIENT_GAP: the edge contract names calling clients Keycloak does not define (callback-ui, github-app, n8n-operations-automation, observability-collector); creating them is a Keycloak owner decision",
)
def test_every_concrete_calling_client_in_the_contract_exists_in_keycloak(summary):
    assert summary["KEYCLOAK_UNKNOWN_CLIENT_IDS"] == []


# --- token contract against Middleware's own validator ---------------------------------


@pytest.fixture
def signing_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
def validator(signing_key, monkeypatch):
    class SigningKey:
        key = signing_key.public_key()

    class JWKClient:
        def __init__(self, *_args, **_kwargs):
            pass

        def get_signing_key_from_jwt(self, _token):
            return SigningKey()

    monkeypatch.setattr(jwt, "PyJWKClient", JWKClient)
    return KeycloakValidator(
        issuer=ISSUER,
        audience=AUDIENCE,
        jwks_url="https://auth.codestra.co/realms/codestra/protocol/openid-connect/certs",
        authorized_parties=frozenset({"odoo-integration"}),
        required_scopes=frozenset({"odoo.events.publish"}),
    )


def claims(now: int) -> dict:
    return {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "azp": "odoo-integration",
        "sub": "service-account-odoo-integration",
        "iat": now,
        "exp": now + 300,
        "jti": "jti-1",
        "scope": "odoo.delivery.result.publish odoo.events.publish",
        "typ": "Bearer",
    }


def test_keycloak_shaped_token_passes_middleware_validation(validator, signing_key):
    now = int(time.time())
    token = jwt.encode(claims(now), signing_key, algorithm="RS256")
    accepted = validator.validate(token)
    assert (
        accepted["azp"] == "odoo-integration"
        and "odoo.events.publish" in accepted["scope"].split()
    )
    assert accepted["exp"] - accepted["iat"] <= 300


@pytest.mark.parametrize(
    "mutation, reason",
    [
        (lambda c: c.pop("aud"), "missing audience"),
        (lambda c: c.__setitem__("aud", "codestra-odoo"), "wrong audience"),
        (lambda c: c.__setitem__("azp", "n8n-automation"), "wrong azp"),
        (lambda c: c.__setitem__("exp", c["iat"] - 1), "expired token"),
        (
            lambda c: c.__setitem__("scope", "odoo.delivery.result.publish"),
            "missing required scope",
        ),
        (
            lambda c: c.__setitem__(
                "iss", "https://auth-staging.codestra.co/realms/codestra"
            ),
            "wrong issuer",
        ),
        (lambda c: c.pop("exp"), "no expiry"),
    ],
)
def test_token_contract_negative_cases_are_rejected(
    validator, signing_key, mutation, reason
):
    now = int(time.time())
    payload = claims(now)
    mutation(payload)
    token = jwt.encode(payload, signing_key, algorithm="RS256")
    with pytest.raises(JWTAuthError):
        validator.validate(token)


def test_scope_escalation_by_claim_is_not_authorization(validator, signing_key):
    """A token that carries an extra scope Keycloak would never issue is still only as
    authorized as the scope the route requires; azp binding stays exact."""
    now = int(time.time())
    payload = claims(now)
    payload["scope"] = "odoo.events.publish platform.command platform.admin"
    accepted = validator.validate(jwt.encode(payload, signing_key, algorithm="RS256"))
    assert accepted["azp"] == "odoo-integration"
    strict = KeycloakValidator(
        issuer=ISSUER,
        audience=AUDIENCE,
        jwks_url=validator.jwks_url,
        authorized_parties=frozenset({"monitoring-readonly"}),
        required_scopes=frozenset({"metrics.read"}),
    )
    with pytest.raises(JWTAuthError):
        strict.validate(jwt.encode(payload, signing_key, algorithm="RS256"))


def test_wrong_signature_and_malformed_tokens_are_rejected(validator, signing_key):
    now = int(time.time())
    untrusted = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    with pytest.raises(JWTAuthError):
        validator.validate(jwt.encode(claims(now), untrusted, algorithm="RS256"))
    with pytest.raises(JWTAuthError):
        validator.validate("not.a.jwt")
    unsigned = jwt.encode(claims(now), "", algorithm="none")
    with pytest.raises(JWTAuthError):
        validator.validate(unsigned)
