from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from app.vicidial_odoo_projection import (
    ProjectionConfigurationError,
    ProjectionSettings,
)

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = (
    ROOT
    / "deploy"
    / "vicidial-odoo-projection"
    / "compose.override.example.yml"
)


def _enabled_staging_env(tmp_path: Path) -> dict[str, str]:
    secret = tmp_path / "odoo-call-event-hmac"
    secret.write_text("s" * 32, encoding="utf-8")
    secret.chmod(0o600)
    return {
        "APP_ENV": "staging",
        "RUNTIME_PROFILE_ID": "codestra-middleware-staging-v1",
        "VICIDIAL_ODOO_PROJECTION_ENABLED": "true",
        "VICIDIAL_ODOO_SYNTHETIC_ONLY": "true",
        "VICIDIAL_ODOO_STATE_PATH": str(tmp_path / "projection.sqlite3"),
        "VICIDIAL_ODOO_DURABLE_CONSUMER": (
            "codestra-vicidial-odoo-staging-v1"
        ),
        "NATS_URL": (
            "tls://nats.middleware-staging.svc.cluster.local:4222"
        ),
        "NATS_STREAM": "CODESTRA_STAGING_EVENTS",
        "NATS_SUBJECT_PREFIX": "codestra.staging.events",
        "NATS_CREDS_FILE": "/run/secrets/nats-vicidial-odoo.creds",
        "ODOO_19_BASE_URL": "https://odoo-staging.internal.codestra",
        "VICIDIAL_ODOO_HMAC_SECRET_FILE": str(secret),
        "PRODUCTION_DIALING": "DISABLED",
    }


def test_enabled_projection_is_bound_to_registered_staging_profile(
    tmp_path: Path,
) -> None:
    settings = ProjectionSettings.from_env(_enabled_staging_env(tmp_path))
    assert settings.runtime_profile_id == "codestra-middleware-staging-v1"
    assert settings.nats_stream == "CODESTRA_STAGING_EVENTS"
    assert settings.subject == (
        "codestra.staging.events.vicidial.call.lifecycle.>"
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        (
            "NATS_URL",
            "tls://nats.middleware-production.svc.cluster.local:4222",
        ),
        ("NATS_STREAM", "CODESTRA_EVENTS"),
        ("NATS_SUBJECT_PREFIX", "codestra.events"),
    ],
)
def test_staging_projection_rejects_production_nats_identity(
    tmp_path: Path,
    field: str,
    value: str,
) -> None:
    env = _enabled_staging_env(tmp_path)
    env[field] = value
    with pytest.raises(
        ProjectionConfigurationError,
        match="must match the selected runtime profile",
    ):
        ProjectionSettings.from_env(env)


def test_projection_rejects_environment_profile_mismatch(
    tmp_path: Path,
) -> None:
    env = _enabled_staging_env(tmp_path)
    env["RUNTIME_PROFILE_ID"] = "codestra-middleware-production-v1"
    with pytest.raises(
        ProjectionConfigurationError,
        match="environment does not match APP_ENV",
    ):
        ProjectionSettings.from_env(env)


def test_projection_rejects_cross_environment_durable_consumer(
    tmp_path: Path,
) -> None:
    env = _enabled_staging_env(tmp_path)
    env["VICIDIAL_ODOO_DURABLE_CONSUMER"] = (
        "codestra-vicidial-odoo-production-v1"
    )
    with pytest.raises(
        ProjectionConfigurationError,
        match="environment-scoped",
    ):
        ProjectionSettings.from_env(env)


def test_worker_compose_prepares_state_and_disables_api_healthcheck() -> None:
    document = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    services = document["services"]
    initializer = services["vicidial-odoo-projection-state-init"]
    worker = services["vicidial-odoo-projection"]

    assert initializer["user"] == "0:0"
    assert initializer["cap_drop"] == ["ALL"]
    assert set(initializer["cap_add"]) == {
        "CHOWN",
        "DAC_OVERRIDE",
        "FOWNER",
    }
    command = "\n".join(initializer["command"])
    assert "chown 65532:65532 /state" in command
    assert "chmod 0700 /state" in command
    assert "stat -c '%u:%g:%a' /state" in command

    assert worker["user"] == "65532:65532"
    assert worker["healthcheck"] == {"disable": True}
    assert worker["depends_on"] == {
        "vicidial-odoo-projection-state-init": {
            "condition": "service_completed_successfully"
        }
    }
    assert (
        "vicidial_odoo_projection_state:/var/lib/codestra-middleware"
        in worker["volumes"]
    )
