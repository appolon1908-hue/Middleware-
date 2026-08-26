from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping


FALSE_VALUES = {"0", "false", "no", "off", ""}
TRUE_VALUES = {"1", "true", "yes", "on"}


class ConfigurationError(RuntimeError):
    """Raised when runtime configuration is unsafe or incomplete."""


def _bool(env: Mapping[str, str], name: str, default: bool = False) -> bool:
    raw = env.get(name)
    if raw is None:
        return default
    value = raw.strip().lower()
    if value in TRUE_VALUES:
        return True
    if value in FALSE_VALUES:
        return False
    raise ConfigurationError(f"{name} must be an explicit boolean")


@dataclass(frozen=True)
class Settings:
    app_env: str
    app_version: str
    issuer: str
    jwks_uri: str
    audience: str
    database_url: str | None
    redis_url: str | None
    allow_in_memory_storage: bool
    webhook_max_clock_skew_seconds: int
    webhook_replay_retention_seconds: int
    outbox_dispatch_enabled: bool
    external_effects: dict[str, bool]

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "Settings":
        source = os.environ if env is None else env
        issuer = source.get(
            "KEYCLOAK_ISSUER",
            "https://auth.codestra.co/realms/codestra",
        ).rstrip("/")
        jwks = source.get(
            "KEYCLOAK_JWKS_URI",
            f"{issuer}/protocol/openid-connect/certs",
        )
        effects = {
            name: _bool(source, name, False)
            for name in (
                "SEND_EVENTS",
                "ENABLE_EXTERNAL_DELIVERY",
                "LIVE_WRITE",
                "LIVE_WRITES",
                "ODOO_WRITE",
                "CALLBACK_DISPATCH",
                "N8N_DELIVERY_ENABLED",
                "VICIDIAL_WRITES_ENABLED",
                "EXTERNAL_DIAL_ENABLED",
                "PRODUCTION_CALLBACKS_ENABLED",
                "N8N_PRODUCTION_WORKFLOWS_ENABLED",
                "FORM_ODOO_DELIVERY_ENABLED",
                "CRAWLER_ODOO_DELIVERY_ENABLED",
                "SCRAPPER_ODOO_DELIVERY_ENABLED",
                "CRAWLER_EXTERNAL_CONTACT_ENABLED",
                "SCRAPPER_EXTERNAL_CONTACT_ENABLED",
                "SMS_DELIVERY_ENABLED",
                "EMAIL_DELIVERY_ENABLED",
                "SOCIAL_DELIVERY_ENABLED",
                "CRAWLER_EXECUTION_ENABLED",
                "SCRAPPER_EXECUTION_ENABLED",
            )
        }
        try:
            skew = int(source.get("WEBHOOK_MAX_CLOCK_SKEW_SECONDS", "300"))
            retention = int(source.get("WEBHOOK_REPLAY_RETENTION_SECONDS", "86400"))
        except ValueError as exc:
            raise ConfigurationError("webhook timing controls must be integers") from exc
        if not 1 <= skew <= 300:
            raise ConfigurationError("WEBHOOK_MAX_CLOCK_SKEW_SECONDS must be 1..300")
        if retention < 86400:
            raise ConfigurationError("WEBHOOK_REPLAY_RETENTION_SECONDS must be >= 86400")
        settings = cls(
            app_env=source.get("APP_ENV", "development").strip().lower(),
            app_version=source.get("APP_VERSION", "0.1.0"),
            issuer=issuer,
            jwks_uri=jwks,
            audience=source.get("MIDDLEWARE_AUDIENCE", "middleware-api"),
            database_url=source.get("DATABASE_URL") or None,
            redis_url=source.get("REDIS_URL") or None,
            allow_in_memory_storage=_bool(source, "ALLOW_IN_MEMORY_STORAGE", False),
            webhook_max_clock_skew_seconds=skew,
            webhook_replay_retention_seconds=retention,
            outbox_dispatch_enabled=_bool(source, "OUTBOX_DISPATCH_ENABLED", False),
            external_effects=effects,
        )
        settings.validate()
        return settings

    def validate(self) -> None:
        if self.issuer != "https://auth.codestra.co/realms/codestra":
            raise ConfigurationError("KEYCLOAK_ISSUER must remain canonical")
        if self.audience != "middleware-api":
            raise ConfigurationError("MIDDLEWARE_AUDIENCE must be middleware-api")
        enabled = sorted(name for name, value in self.external_effects.items() if value)
        if enabled:
            raise ConfigurationError(
                "external effects must remain disabled in intake-runtime-v1: "
                + ", ".join(enabled)
            )
        if self.outbox_dispatch_enabled:
            raise ConfigurationError(
                "OUTBOX_DISPATCH_ENABLED must remain false until a separate reviewed activation"
            )
        if self.allow_in_memory_storage:
            if self.app_env not in {"test", "development"}:
                raise ConfigurationError(
                    "ALLOW_IN_MEMORY_STORAGE is allowed only in test/development"
                )
        elif not self.database_url or not self.redis_url:
            raise ConfigurationError(
                "DATABASE_URL and REDIS_URL are required unless explicitly using "
                "in-memory storage in test/development"
            )

    def webhook_secret(self, producer_client_id: str) -> bytes:
        name = (
            "WEBHOOK_SECRET_"
            + producer_client_id.upper().replace("-", "_").replace(".", "_")
        )
        value = os.environ.get(name)
        if not value:
            raise ConfigurationError(f"missing webhook secret for {producer_client_id}: {name}")
        secret = value.encode("utf-8")
        if len(secret) < 32:
            raise ConfigurationError(f"{name} must contain at least 32 bytes")
        return secret
