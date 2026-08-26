from __future__ import annotations

import pytest

from app.config import ConfigurationError, Settings
from app.security import AuthorizationError, validate_claims


def test_exact_scope_and_azp_are_required() -> None:
    validate_claims(
        {"azp": "odoo-integration", "scope": "odoo.events.publish other.scope"},
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
