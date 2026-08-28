from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping
from urllib.parse import urlparse


FALSE_VALUES = {"0", "false", "no", "off", ""}
TRUE_VALUES = {"1", "true", "yes", "on"}
SHA40 = re.compile(r"^[0-9a-f]{40}$")
IMAGE_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
WEBHOOK_PRODUCERS = (
    "odoo-integration",
    "n8n-automation",
    "vicidial-adapter",
    "telnexa-gateway",
    "klyrow-gateway",
    "kyqra-gateway",
    "postly-adapter",
)


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


def _int(
    env: Mapping[str, str],
    name: str,
    default: int,
    *,
    minimum: int,
    maximum: int,
) -> int:
    try:
        value = int(env.get(name, str(default)))
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be an integer") from exc
    if not minimum <= value <= maximum:
        raise ConfigurationError(f"{name} must be between {minimum} and {maximum}")
    return value


def _secret_env_name(producer_client_id: str) -> str:
    return (
        "WEBHOOK_SECRET_"
        + producer_client_id.upper().replace("-", "_").replace(".", "_")
    )


def _is_absolute_mount_path(path: Path) -> bool:
    value = str(path)
    return (
        path.is_absolute()
        or value.startswith(("/", "\\"))
        or re.match(r"^[A-Za-z]:[\\/]", value) is not None
    )


@dataclass(frozen=True)
class Settings:
    app_env: str
    app_version: str
    source_sha: str
    image_digest: str
    schema_head: str
    build_time: str
    issuer: str
    jwks_uri: str
    jwks_timeout_seconds: int
    audience: str
    database_url: str | None
    redis_url: str | None
    nats_url: str | None
    nats_stream: str
    nats_subject_prefix: str
    nats_credentials_file: Path | None
    production_activation_id: str | None
    production_dialing: str
    allow_in_memory_storage: bool
    max_request_body_bytes: int
    webhook_max_clock_skew_seconds: int
    webhook_replay_retention_seconds: int
    webhook_secrets: dict[str, bytes]
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
                "LIVE_SMS_DELIVERY",
                "LIVE_EMAIL_DELIVERY",
                "UNRESTRICTED_CRAWLING",
            )
        }
        webhook_secrets = {
            producer: source.get(_secret_env_name(producer), "").encode("utf-8")
            for producer in WEBHOOK_PRODUCERS
        }
        settings = cls(
            app_env=source.get("APP_ENV", "development").strip().lower(),
            app_version=source.get("APP_VERSION", "0.1.0").strip(),
            source_sha=source.get("APP_SOURCE_SHA", "unknown").strip(),
            image_digest=source.get("IMAGE_DIGEST", "unknown").strip(),
            schema_head=source.get("SCHEMA_HEAD", "0001_runtime").strip(),
            build_time=source.get("BUILD_TIME", "unknown").strip(),
            issuer=issuer,
            jwks_uri=jwks,
            jwks_timeout_seconds=_int(
                source,
                "JWKS_TIMEOUT_SECONDS",
                3,
                minimum=1,
                maximum=10,
            ),
            audience=source.get("MIDDLEWARE_AUDIENCE", "middleware-api"),
            database_url=source.get("DATABASE_URL") or None,
            redis_url=source.get("REDIS_URL") or None,
            nats_url=source.get("NATS_URL") or None,
            nats_stream=source.get("NATS_STREAM", "CODESTRA_EVENTS").strip(),
            nats_subject_prefix=source.get(
                "NATS_SUBJECT_PREFIX",
                "codestra.events",
            ).strip(),
            nats_credentials_file=(
                Path(source["NATS_CREDS_FILE"])
                if source.get("NATS_CREDS_FILE")
                else None
            ),
            production_activation_id=(
                source.get("PRODUCTION_ACTIVATION_ID", "").strip() or None
            ),
            production_dialing=source.get(
                "PRODUCTION_DIALING",
                "DISABLED",
            ).strip(),
            allow_in_memory_storage=_bool(source, "ALLOW_IN_MEMORY_STORAGE", False),
            max_request_body_bytes=_int(
                source,
                "MAX_REQUEST_BODY_BYTES",
                1_048_576,
                minimum=1_024,
                maximum=10_485_760,
            ),
            webhook_max_clock_skew_seconds=_int(
                source,
                "WEBHOOK_MAX_CLOCK_SKEW_SECONDS",
                300,
                minimum=1,
                maximum=300,
            ),
            webhook_replay_retention_seconds=_int(
                source,
                "WEBHOOK_REPLAY_RETENTION_SECONDS",
                86_400,
                minimum=86_400,
                maximum=2_592_000,
            ),
            webhook_secrets=webhook_secrets,
            outbox_dispatch_enabled=_bool(source, "OUTBOX_DISPATCH_ENABLED", False),
            external_effects=effects,
        )
        settings.validate()
        return settings

    def validate(self) -> None:
        if self.app_env not in {"development", "test", "staging", "production"}:
            raise ConfigurationError("APP_ENV is not recognized")
        if self.issuer != "https://auth.codestra.co/realms/codestra":
            raise ConfigurationError("KEYCLOAK_ISSUER must remain canonical")
        if self.jwks_uri != f"{self.issuer}/protocol/openid-connect/certs":
            raise ConfigurationError("KEYCLOAK_JWKS_URI must match the canonical issuer")
        if self.audience != "middleware-api":
            raise ConfigurationError("MIDDLEWARE_AUDIENCE must be middleware-api")
        enabled = {
            name for name, value in self.external_effects.items() if value
        }
        unsupported_enabled = sorted(enabled - {"SEND_EVENTS"})
        if unsupported_enabled:
            raise ConfigurationError(
                "provider and business effects are not implemented by this runtime: "
                + ", ".join(unsupported_enabled)
            )
        if self.production_dialing != "DISABLED":
            raise ConfigurationError(
                "PRODUCTION_DIALING must remain DISABLED"
            )
        if self.outbox_dispatch_enabled != ("SEND_EVENTS" in enabled):
            raise ConfigurationError(
                "OUTBOX_DISPATCH_ENABLED and SEND_EVENTS must be enabled or disabled together"
            )
        if self.outbox_dispatch_enabled:
            if self.app_env != "production":
                raise ConfigurationError(
                    "JetStream dispatch is allowed only after production authorization"
                )
            if not self.production_activation_id or not re.fullmatch(
                r"[A-Z0-9][A-Z0-9._/-]{7,127}",
                self.production_activation_id,
            ):
                raise ConfigurationError(
                    "PRODUCTION_ACTIVATION_ID must identify the approved activation"
                )
            parsed_nats = urlparse(self.nats_url or "")
            if parsed_nats.scheme != "tls" or not parsed_nats.hostname:
                raise ConfigurationError(
                    "NATS_URL must use tls:// with a hostname when dispatch is enabled"
                )
            if not re.fullmatch(r"[A-Z][A-Z0-9_]{2,63}", self.nats_stream):
                raise ConfigurationError("NATS_STREAM is invalid")
            if not re.fullmatch(
                r"[a-z0-9]+(?:\.[a-z0-9_-]+)+",
                self.nats_subject_prefix,
            ):
                raise ConfigurationError("NATS_SUBJECT_PREFIX is invalid")
            if (
                self.nats_credentials_file is None
                or not _is_absolute_mount_path(self.nats_credentials_file)
            ):
                raise ConfigurationError(
                    "NATS_CREDS_FILE must be an absolute mounted credential path"
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
        if self.schema_head != "0001_runtime":
            raise ConfigurationError("SCHEMA_HEAD must be 0001_runtime for intake-runtime-v1")
        if self.app_env in {"staging", "production"}:
            if not SHA40.fullmatch(self.source_sha):
                raise ConfigurationError("APP_SOURCE_SHA must be an exact 40-character SHA")
            if not IMAGE_DIGEST.fullmatch(self.image_digest):
                raise ConfigurationError("IMAGE_DIGEST must be an immutable sha256 digest")
            if self.build_time in {"", "unknown"}:
                raise ConfigurationError("BUILD_TIME is required in staging/production")
            self.validate_all_webhook_secrets()

    def validate_all_webhook_secrets(self) -> None:
        for producer in WEBHOOK_PRODUCERS:
            secret = self.webhook_secrets.get(producer, b"")
            name = _secret_env_name(producer)
            if len(secret) < 32:
                raise ConfigurationError(
                    f"{name} must be configured with at least 32 bytes"
                )

    def webhook_secret(self, producer_client_id: str) -> bytes:
        if producer_client_id not in WEBHOOK_PRODUCERS:
            raise ConfigurationError(f"unknown webhook producer: {producer_client_id}")
        secret = self.webhook_secrets.get(producer_client_id, b"")
        name = _secret_env_name(producer_client_id)
        if len(secret) < 32:
            raise ConfigurationError(f"{name} must contain at least 32 bytes")
        return secret
