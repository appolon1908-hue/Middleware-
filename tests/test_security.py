from __future__ import annotations

import pytest

from app.config import ConfigurationError, Settings, WEBHOOK_PRODUCERS
from app.security import (
    AuthorizationError,
    RequestValidationError,
    _parse_timestamp,
    authorize_tenant,
    validate_claims,
)


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
            {"azp": "odoo-integration", "scope": "other.scope", "iat": 100, "exp": 200},
            expected_client_id="odoo-integration",
            required_scope="odoo.events.publish",
        )
    with pytest.raises(AuthorizationError):
        validate_claims(
            {"azp": "wrong-client", "scope": "odoo.events.publish", "iat": 100, "exp": 200},
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


def test_machine_token_timestamp_claims_must_be_numeric_and_finite() -> None:
    for iat, exp in (("100", 200), (100, "200"), (True, 200), (100, False), (float("nan"), 200), (100, float("inf"))):
        with pytest.raises(AuthorizationError):
            validate_claims(
                {
                    "azp": "odoo-integration",
                    "scope": "odoo.events.publish",
                    "iat": iat,
                    "exp": exp,
                },
                expected_client_id="odoo-integration",
                required_scope="odoo.events.publish",
            )


def test_non_finite_webhook_timestamp_is_rejected() -> None:
    for raw in ("nan", "NaN", "inf", "-inf"):
        with pytest.raises(RequestValidationError):
            _parse_timestamp(raw)


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


def test_jetstream_dispatch_requires_matching_gate_and_authorization() -> None:
    with pytest.raises(ConfigurationError):
        Settings.from_env(
            {
                "APP_ENV": "test",
                "ALLOW_IN_MEMORY_STORAGE": "true",
                "OUTBOX_DISPATCH_ENABLED": "true",
            }
        )
    with pytest.raises(ConfigurationError):
        Settings.from_env(
            {
                "APP_ENV": "test",
                "ALLOW_IN_MEMORY_STORAGE": "true",
                "SEND_EVENTS": "true",
                "OUTBOX_DISPATCH_ENABLED": "true",
            }
        )


def test_production_jetstream_dispatch_requires_approved_identity() -> None:
    env = {
        "APP_ENV": "production",
        "DATABASE_URL": "postgresql://middleware.invalid/db",
        "REDIS_URL": "redis://redis.invalid/0",
        "NATS_URL": "tls://nats.invalid:4222",
        "NATS_STREAM": "CODESTRA_EVENTS",
        "NATS_SUBJECT_PREFIX": "codestra.events",
        "NATS_CREDS_FILE": "/run/secrets/middleware-nats.creds",
        "NATS_DISPATCH_MODE": "production",
        "PRODUCTION_ACTIVATION_ID": "CHG-20260828-EVENTS",
        "SEND_EVENTS": "true",
        "OUTBOX_DISPATCH_ENABLED": "true",
        "APP_SOURCE_SHA": "a" * 40,
        "IMAGE_DIGEST": "sha256:" + "b" * 64,
        "BUILD_TIME": "2026-08-28T12:00:00Z",
    }
    for producer in WEBHOOK_PRODUCERS:
        env[
            "WEBHOOK_SECRET_"
            + producer.upper().replace("-", "_").replace(".", "_")
        ] = "x" * 32

    settings = Settings.from_env(env)

    assert settings.outbox_dispatch_enabled is True
    assert settings.production_activation_id == "CHG-20260828-EVENTS"


def test_staging_uses_an_isolated_jetstream_namespace() -> None:
    env = staging_env()
    env.update(
        {
            "NATS_URL": "tls://nats-staging.invalid:4222",
            "NATS_STREAM": "CODESTRA_STAGING_EVENTS",
            "NATS_SUBJECT_PREFIX": "codestra.staging.events",
            "NATS_CREDS_FILE": "/run/secrets/middleware-staging-nats.creds",
            "NATS_DISPATCH_MODE": "isolated",
            "SEND_EVENTS": "true",
            "OUTBOX_DISPATCH_ENABLED": "true",
        }
    )
    for producer in WEBHOOK_PRODUCERS:
        env[
            "WEBHOOK_SECRET_"
            + producer.upper().replace("-", "_").replace(".", "_")
        ] = "x" * 32

    settings = Settings.from_env(env)

    assert settings.nats_dispatch_mode == "isolated"
    assert settings.nats_subject_prefix == "codestra.staging.events"


def test_staging_rejects_production_jetstream_namespace() -> None:
    env = staging_env()
    env.update(
        {
            "NATS_URL": "tls://nats-staging.invalid:4222",
            "NATS_STREAM": "CODESTRA_EVENTS",
            "NATS_SUBJECT_PREFIX": "codestra.events",
            "NATS_CREDS_FILE": "/run/secrets/middleware-staging-nats.creds",
            "NATS_DISPATCH_MODE": "isolated",
            "SEND_EVENTS": "true",
            "OUTBOX_DISPATCH_ENABLED": "true",
        }
    )
    for producer in WEBHOOK_PRODUCERS:
        env[
            "WEBHOOK_SECRET_"
            + producer.upper().replace("-", "_").replace(".", "_")
        ] = "x" * 32

    with pytest.raises(ConfigurationError):
        Settings.from_env(env)


def test_temporal_test_worker_requires_isolated_local_configuration() -> None:
    settings = Settings.from_env(
        {
            "APP_ENV": "test",
            "ALLOW_IN_MEMORY_STORAGE": "true",
            "TEMPORAL_ADDRESS": "127.0.0.1:7233",
            "TEMPORAL_NAMESPACE": "codestra-test",
            "TEMPORAL_TASK_QUEUE": "codestra-test-critical",
            "TEMPORAL_WORKER_MODE": "isolated",
            "TEMPORAL_ALLOW_INSECURE_TEST_CONNECTION": "true",
        }
    )
    assert settings.temporal_worker_mode == "isolated"

    with pytest.raises(ConfigurationError):
        Settings.from_env(
            {
                "APP_ENV": "test",
                "ALLOW_IN_MEMORY_STORAGE": "true",
                "TEMPORAL_ADDRESS": "temporal.example:7233",
                "TEMPORAL_NAMESPACE": "codestra-test",
                "TEMPORAL_TASK_QUEUE": "codestra-test-critical",
                "TEMPORAL_WORKER_MODE": "isolated",
                "TEMPORAL_ALLOW_INSECURE_TEST_CONNECTION": "true",
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


def staging_env() -> dict[str, str]:
    return {
        "APP_ENV": "staging",
        "DATABASE_URL": "postgresql://example.invalid/db",
        "REDIS_URL": "redis://example.invalid/0",
        "APP_SOURCE_SHA": "a" * 40,
        "IMAGE_DIGEST": "sha256:" + "b" * 64,
        "BUILD_TIME": "2026-08-26T23:00:00Z",
    }


def test_staging_requires_immutable_release_identity() -> None:
    with pytest.raises(ConfigurationError):
        Settings.from_env(
            {
                "APP_ENV": "staging",
                "DATABASE_URL": "postgresql://example.invalid/db",
                "REDIS_URL": "redis://example.invalid/0",
            }
        )


def test_staging_requires_every_webhook_secret() -> None:
    env = staging_env()
    with pytest.raises(ConfigurationError):
        Settings.from_env(env)

    for producer in WEBHOOK_PRODUCERS:
        name = "WEBHOOK_SECRET_" + producer.upper().replace("-", "_").replace(".", "_")
        env[name] = "x" * 32
    settings = Settings.from_env(env)
    settings.validate_all_webhook_secrets()


def test_webhook_secret_uses_supplied_environment_mapping() -> None:
    settings = Settings.from_env(
        {
            "APP_ENV": "test",
            "ALLOW_IN_MEMORY_STORAGE": "true",
            "WEBHOOK_SECRET_ODOO_INTEGRATION": "s" * 32,
        }
    )
    assert settings.webhook_secret("odoo-integration") == b"s" * 32


def test_jwks_uri_is_pinned_to_canonical_issuer() -> None:
    with pytest.raises(ConfigurationError):
        Settings.from_env(
            {
                "APP_ENV": "test",
                "ALLOW_IN_MEMORY_STORAGE": "true",
                "KEYCLOAK_JWKS_URI": "http://attacker.invalid/jwks",
            }
        )
