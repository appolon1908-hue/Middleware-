from __future__ import annotations

import base64
import importlib.util
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "staging_product_auth_read_matrix.py"


def load_module():
    spec = importlib.util.spec_from_file_location("staging_product_auth_read_matrix", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def encoded(value: dict[str, object]) -> str:
    raw = json.dumps(value, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def token(claims: dict[str, object]) -> str:
    return encoded({"alg": "RS256", "typ": "JWT"}) + "." + encoded(claims) + ".signature"


def valid_claims() -> dict[str, object]:
    return {
        "iss": "https://auth.codestra.co/realms/codestra",
        "aud": ["middleware-api"],
        "azp": "moneybee-backend",
        "iat": 1000,
        "exp": 1300,
        "scope": "moneybee.middleware.command.write moneybee.middleware.status.read",
        "tenant_id": "tenant-test",
    }


def test_source_never_posts_a_middleware_command() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert 'route": "/v1/operations/{command_id}"' in source
    assert 'method="GET"' in source
    assert '"command_posts": 0' in source
    assert 'AUTH_MATRIX_COMMAND_POSTS=0' in source
    assert 'provider_calls": 0' in source
    assert '/v1/commands' not in source


def test_token_request_is_the_only_explicit_post() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert source.count('method="POST"') == 1
    assert "grant_type" in source and "client_credentials" in source


def test_product_client_registry_matches_source_policy() -> None:
    module = load_module()
    callers = module._load_policy()
    assert module.EXPECTED_CLIENTS == (
        "moneybee-backend",
        "breero-backend",
        "larim-a-backend",
        "transportation-backend",
        "beyvra-backend",
        "social-codestra",
    )
    for client_id in module.EXPECTED_CLIENTS:
        assert callers[client_id]["compatibility_only"] is False
        assert callers[client_id]["status_scope"].endswith(".middleware.status.read")


def test_valid_claim_shape_requires_short_lived_product_token() -> None:
    module = load_module()
    claims = valid_claims()
    tenant = module.validate_claim_shape(
        claims,
        client_id="moneybee-backend",
        required_scope="moneybee.middleware.status.read",
        now=1100,
    )
    assert tenant == "tenant-test"


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("iss", "https://wrong.invalid/realm", "issuer"),
        ("aud", ["moneybee-api"], "audience"),
        ("azp", "social-codestra", "azp"),
        ("exp", 1401, "lifetime"),
        ("scope", "moneybee.middleware.command.write", "scope"),
        ("tenant_id", "*", "tenant_id"),
    ],
)
def test_invalid_claim_shapes_fail_closed(field: str, value: object, message: str) -> None:
    module = load_module()
    claims = valid_claims()
    claims[field] = value
    with pytest.raises(module.MatrixError, match=message):
        module.validate_claim_shape(
            claims,
            client_id="moneybee-backend",
            required_scope="moneybee.middleware.status.read",
            now=1100,
        )


def test_jwt_decode_and_signature_tamper_do_not_require_secret() -> None:
    module = load_module()
    original = token(valid_claims())
    claims = module.decode_unverified_claims(original)
    assert claims["azp"] == "moneybee-backend"
    changed = module.tamper_signature(original)
    assert changed != original
    assert changed.split(".")[:2] == original.split(".")[:2]


def test_evidence_records_no_tokens_or_secrets() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert '"tokens_recorded"] = False' in source
    assert '"secrets_recorded"] = False' in source
    assert "tenant_sha256" in source
    assert 'record["tenant_id"]' not in source


def test_staging_marker_and_explicit_https_endpoints_are_required() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert 'AUTH_MATRIX_ENVIRONMENT") != "staging"' in source
    assert "AUTH_MATRIX_GATEWAY_BASE_URL" in source
    assert "AUTH_MATRIX_TOKEN_ENDPOINT" in source
    assert "must be an HTTPS URL without embedded credentials" in source
