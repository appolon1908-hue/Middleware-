from __future__ import annotations

import pytest

from app.config import ConfigurationError, Settings
from app.security import AuthorizationError, authorize_tenant, validate_claims


def test_exact_scope_and_azp_are_required() -> None:
    validate_claims(
        {
            "azp": "odoo-integration",
            "scope": "odoo.events.publish other.scope",
            "iat": 100,
            "exp": 400,
        },
        expected_client_id="odoo-integration",
        required_scope="odoo.events.publish",
    )
    with pytest.raises(AuthorizationError):
        validate_claims(
            {"azp": "odoo-integration", "scope": "other.scope"},
            expected_client_id="odoo-integration",
            required_scope="odoo.events.publish",
        )
    with pytest.raises(AuthorizationError):
        validate_claims(
            {"azp": "wrong-client", "scope": "odoo.events.publish"},
            expected_client_id="odoo-integration",
            required_scope="odoo.events.publish",
        )


def test_machine_token_lifetime_is_bounded() -> None:
    with pytest.raises(AuthorizationError):
        validate_claims(
            {
                "azp": "odoo-integration",
                "scope": "odoo.events.publish",
                "iat": 100,
                "exp": 401,
            },
            expected_client_id="odoo-integration",
            required_scope="odoo.events.publish",
        )


def test_tenant_claim_is_mandatory_and_no_wildcards() -> None:
    authorize_tenant({"tenant_id": "tenant-a"}, "tenant-a")
    authorize_tenant({"tenant_ids": ["tenant-a", "tenant-b"]}, "tenant-b")
    with pytest.raises(AuthorizationError):
        authorize_tenant({}, "tenant-a")
    with pytest.raises(AuthorizationError):
        authorize_tenant({"tenant_id": "*"}, "tenant-a")
    with pytest.raises(AuthorizationError):
        authorize_tenant({"tenant_id": "tenant-b"}, "tenant-a")


def test_external_effect_flags_fail_closed() -> None:
    with pytest.raises(ConfigurationError):
        Settings.from_env(
            {
                "APP_ENV": "test",
                "ALLOW_IN_MEMORY_STORAGE": "true",
                "SEND_EVENTS": "true",
            }
        )


def test_staging_cannot_use_in_memory_storage() -> None:
    with pytest.raises(ConfigurationError):
        Settings.from_env(
            {
                "APP_ENV": "staging",
                "ALLOW_IN_MEMORY_STORAGE": "true",
            }
        )


def test_staging_requires_immutable_release_identity() -> None:
    with pytest.raises(ConfigurationError):
        Settings.from_env(
            {
                "APP_ENV": "staging",
                "DATABASE_URL": "postgresql://example.invalid/db",
                "REDIS_URL": "redis://example.invalid/0",
            }
        )
