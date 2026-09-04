from __future__ import annotations

import json
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping
from urllib.parse import urlsplit, urlunsplit

from .vicidial_odoo_projection_errors import ProjectionConfigurationError

_TRUE = frozenset({"1", "true", "yes", "on", "enabled"})
_FALSE = frozenset({"", "0", "false", "no", "off", "disabled"})
_SAFE_DURABLE = re.compile(r"^[A-Za-z0-9_-]{3,64}$")


def parse_bool(value: str | None, *, name: str, default: bool) -> bool:
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in _TRUE:
        return True
    if normalized in _FALSE:
        return False
    raise ProjectionConfigurationError(f"{name} must be an explicit boolean")


def _read_private_text(path: Path, *, minimum_bytes: int = 1) -> str:
    if not path.is_absolute():
        raise ProjectionConfigurationError("secret paths must be absolute")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise ProjectionConfigurationError(f"protected file cannot be opened: {path}") from exc
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode):
            raise ProjectionConfigurationError("protected path is not a regular file")
        if info.st_mode & 0o077:
            raise ProjectionConfigurationError("protected file must be mode 0600 or stricter")
        raw = os.read(descriptor, 65537)
        if len(raw) > 65536:
            raise ProjectionConfigurationError("protected file exceeds 65536 bytes")
    finally:
        os.close(descriptor)
    try:
        value = raw.decode("utf-8").strip()
    except UnicodeDecodeError as exc:
        raise ProjectionConfigurationError("protected file must contain UTF-8 text") from exc
    if len(value.encode("utf-8")) < minimum_bytes:
        raise ProjectionConfigurationError("protected value is too short")
    return value


def _https_origin(value: str) -> str:
    parsed = urlsplit(value.strip())
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise ProjectionConfigurationError(
            "Odoo base URL must be one HTTPS origin without credentials or path"
        )
    return urlunsplit(("https", parsed.netloc, "", "", ""))


@dataclass(frozen=True, slots=True)
class ProjectionSettings:
    enabled: bool
    synthetic_only: bool
    app_env: str
    activation_id: str | None
    nats_url: str | None
    nats_stream: str
    nats_subject_prefix: str
    nats_credentials_file: Path | None
    durable_consumer: str
    state_path: Path
    odoo_base_url: str | None
    tenant_secrets: Mapping[str, bytes]
    default_secret: bytes | None
    batch_size: int = 10
    fetch_timeout_seconds: float = 2.0

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "ProjectionSettings":
        source = os.environ if env is None else env
        enabled = parse_bool(
            source.get("VICIDIAL_ODOO_PROJECTION_ENABLED"),
            name="VICIDIAL_ODOO_PROJECTION_ENABLED",
            default=False,
        )
        synthetic_only = parse_bool(
            source.get("VICIDIAL_ODOO_SYNTHETIC_ONLY"),
            name="VICIDIAL_ODOO_SYNTHETIC_ONLY",
            default=True,
        )
        tenant_secrets: dict[str, bytes] = {}
        tenant_file = source.get("VICIDIAL_ODOO_TENANT_HMAC_SECRETS_FILE", "").strip()
        if tenant_file:
            decoded = json.loads(_read_private_text(Path(tenant_file), minimum_bytes=2))
            if not isinstance(decoded, dict) or not all(
                isinstance(key, str) and key and isinstance(value, str) and len(value.encode()) >= 32
                for key, value in decoded.items()
            ):
                raise ProjectionConfigurationError(
                    "tenant HMAC secret file must map tenant IDs to >=32-byte strings"
                )
            tenant_secrets = {key: value.encode() for key, value in decoded.items()}
        default_secret: bytes | None = None
        secret_file = source.get("VICIDIAL_ODOO_HMAC_SECRET_FILE", "").strip()
        if secret_file:
            default_secret = _read_private_text(Path(secret_file), minimum_bytes=32).encode()
        state_path = Path(
            source.get(
                "VICIDIAL_ODOO_STATE_PATH",
                "/var/lib/codestra-middleware/vicidial-odoo-projection.sqlite3",
            )
        )
        credentials = source.get("NATS_CREDS_FILE", "").strip()
        settings = cls(
            enabled=enabled,
            synthetic_only=synthetic_only,
            app_env=source.get("APP_ENV", "development").strip().lower(),
            activation_id=source.get("VICIDIAL_ODOO_ACTIVATION_ID", "").strip() or None,
            nats_url=source.get("NATS_URL", "").strip() or None,
            nats_stream=source.get("NATS_STREAM", "CODESTRA_EVENTS").strip(),
            nats_subject_prefix=source.get("NATS_SUBJECT_PREFIX", "codestra.events").strip(),
            nats_credentials_file=Path(credentials) if credentials else None,
            durable_consumer=source.get(
                "VICIDIAL_ODOO_DURABLE_CONSUMER",
                "codestra-vicidial-odoo-projection-v1",
            ).strip(),
            state_path=state_path,
            odoo_base_url=(source.get("ODOO_19_BASE_URL", "").strip() or None),
            tenant_secrets=tenant_secrets,
            default_secret=default_secret,
            batch_size=int(source.get("VICIDIAL_ODOO_BATCH_SIZE", "10")),
            fetch_timeout_seconds=float(
                source.get("VICIDIAL_ODOO_FETCH_TIMEOUT_SECONDS", "2")
            ),
        )
        settings.validate(source)
        return settings

    def validate(self, source: Mapping[str, str]) -> None:
        if self.app_env not in {"development", "test", "staging", "production"}:
            raise ProjectionConfigurationError("APP_ENV is not recognized")
        if not self.enabled:
            return
        if not self.state_path.is_absolute():
            raise ProjectionConfigurationError("projection state path must be absolute")
        if not _SAFE_DURABLE.fullmatch(self.durable_consumer):
            raise ProjectionConfigurationError("durable consumer name is invalid")
        if not 1 <= self.batch_size <= 100:
            raise ProjectionConfigurationError("batch size must be between 1 and 100")
        if not 0.1 <= self.fetch_timeout_seconds <= 30:
            raise ProjectionConfigurationError("fetch timeout must be between 0.1 and 30 seconds")
        if not self.nats_url or not self.nats_url.startswith("tls://"):
            raise ProjectionConfigurationError("enabled projection requires a TLS NATS URL")
        if self.nats_credentials_file is None or not self.nats_credentials_file.is_absolute():
            raise ProjectionConfigurationError("enabled projection requires an absolute NATS credentials path")
        if not self.odoo_base_url:
            raise ProjectionConfigurationError("enabled projection requires ODOO_19_BASE_URL")
        _https_origin(self.odoo_base_url)
        if not self.tenant_secrets and not self.default_secret:
            raise ProjectionConfigurationError("enabled projection requires an Odoo HMAC secret file")
        if self.app_env == "staging" and not self.synthetic_only:
            raise ProjectionConfigurationError("staging projection must remain TEST_SYN-only")
        if source.get("PRODUCTION_DIALING", "DISABLED").strip().upper() != "DISABLED":
            raise ProjectionConfigurationError("PRODUCTION_DIALING must remain DISABLED")
        for name in (
            "VICIDIAL_WRITES_ENABLED",
            "EXTERNAL_DIAL_ENABLED",
            "PRODUCTION_CALLBACKS_ENABLED",
            "LIVE_SMS_DELIVERY",
            "LIVE_EMAIL_DELIVERY",
        ):
            if parse_bool(source.get(name), name=name, default=False):
                raise ProjectionConfigurationError(f"{name} must remain disabled")
        if self.app_env == "production":
            if not self.activation_id:
                raise ProjectionConfigurationError(
                    "production projection requires VICIDIAL_ODOO_ACTIVATION_ID"
                )
            if not parse_bool(
                source.get("EXTERNAL_DELIVERY_ENABLED"),
                name="EXTERNAL_DELIVERY_ENABLED",
                default=False,
            ) or not parse_bool(
                source.get("ODOO_WRITE"), name="ODOO_WRITE", default=False
            ):
                raise ProjectionConfigurationError(
                    "production projection requires EXTERNAL_DELIVERY_ENABLED and ODOO_WRITE"
                )

    @property
    def subject(self) -> str:
        return f"{self.nats_subject_prefix}.vicidial.call.lifecycle.>"
