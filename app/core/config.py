from pathlib import Path
import base64
import json
from urllib.parse import urlsplit

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


VICIDIAL_PRIVATE_HOSTS = frozenset(
    {
        "authorization.internal.codestra.agency",
        "edge.internal.codestra.agency",
    }
)
VICIDIAL_PRIVATE_PORT = 8443
VICIDIAL_ENDPOINT_ADAPTER_PORT = 8444
VICIDIAL_SECRET_ROOT = Path("/run/secrets/vicidial-mtls")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")
    database_url: str = "postgresql+asyncpg://localhost/codestra_middleware"
    database_url_file: str = ""
    redis_url: str = "redis://localhost:6379/2"
    redis_url_file: str = ""
    ingestion_hmac_secret: str = ""
    ingestion_token: str = ""
    middleware_secret: str = ""
    middleware_secret_file: str = ""
    webhook_shared_secret: str = ""
    webhook_shared_secret_file: str = ""
    vicidial_callback_hmac_secret_file: str = ""
    signature_ttl_seconds: int = 300
    request_max_bytes: int = 262144
    database_pool_size: int = 8
    database_max_overflow: int = 4
    database_pool_timeout_seconds: int = 5
    enabled_event_types: str = "vicidial.call.ended"
    allowed_client_instances: str = "vicidial-server-b"
    live_writes_enabled: bool = False
    allow_non_test_campaigns: bool = False
    odoo_delivery_enabled: bool = False
    n8n_delivery_enabled: bool = False
    n8n_event_delivery_enabled: bool = False
    n8n_production_workflows_enabled: bool = False
    automation_actions_enabled: bool = False
    odoo_automation_writes_enabled: bool = False
    vicidial_read_enabled: bool = False
    vicidial_write_enabled: bool = False
    transfer_control_enabled: bool = False
    vicidial_authorization_url: str = ""
    vicidial_edge_url: str = ""
    vicidial_ca_file: str = ""
    vicidial_client_cert_file: str = ""
    vicidial_client_key_file: str = ""
    vicidial_crl_file: str = ""
    callback_dispatch_enabled: bool = False
    messaging_enabled: bool = False
    ai_enrichment_enabled: bool = False
    report_delivery_enabled: bool = False
    outbox_worker_enabled: bool = False
    outbox_max_attempts: int = 5
    outbox_base_delay_seconds: int = 5
    outbox_max_delay_seconds: int = 300
    outbox_lease_seconds: int = 60
    odoo_concurrency: int = 4
    n8n_concurrency: int = 8
    recording_concurrency: int = 2
    reconciliation_concurrency: int = 1
    keycloak_issuer: str = ""
    keycloak_audience: str = ""
    keycloak_jwks_url: str = ""
    keycloak_authorized_parties: str = ""
    keycloak_userinfo_url: str = ""
    provisioning_service_url: str = ""
    provisioning_service_token_url: str = ""
    provisioning_service_client_id: str = ""
    provisioning_service_client_secret_file: str = ""
    provisioning_service_ca_file: str = ""
    odoo_identity_lookup_url: str = ""
    odoo_identity_lookup_hmac_file: str = ""
    maintenance_interval_seconds: int = 30
    automation_allowed_campaigns: str = "TEST_SYN"
    automation_environment: str = "test"
    automation_hmac_secret: str = ""
    environment: str = "preproduction"
    publisher_hmac_keys_file: str = ""
    publisher_canary_enabled: bool = False
    quarantine_encryption_key_file: str = ""
    quarantine_encryption_key_version: str = "v1"
    quarantine_fingerprint_secret_file: str = ""
    quarantine_reviewer_secret_file: str = ""
    quarantine_retention_days: int = 90
    quarantine_retention_policy_version: str = "2026-07-26.1"
    quarantine_store_authenticated_raw: bool = True
    quarantine_rate_limit_per_minute: int = 30
    webphone_staging_provisioning_enabled: bool = False
    webphone_keycloak_enabled: bool = False
    webphone_endpoint_adapter_url: str = ""
    extension_allocator_enabled: bool = False
    telephony_provisioning_enabled: bool = False
    vicidial_provisioning_enabled: bool = False
    postiz_internal_base_url: str = ""
    postiz_client_cert_file: str = ""
    postiz_client_key_file: str = ""
    postiz_ca_file: str = ""
    postiz_api_key_file: str = ""
    postiz_organization_reference: str = ""
    postiz_timeout_seconds: float = 10.0
    postiz_delivery_enabled: bool = False
    postiz_publish_enabled: bool = False
    postiz_media_upload_enabled: bool = False
    postiz_analytics_enabled: bool = False
    pjsip_provisioning_enabled: bool = False
    webphone_session_issuer_enabled: bool = False
    telephony_reconciliation_enabled: bool = False
    telephony_notifications_enabled: bool = False
    telephony_evidence_enabled: bool = False

    def validate_safety(self) -> None:
        production_switches = (
            self.live_writes_enabled,
            self.allow_non_test_campaigns,
            self.n8n_production_workflows_enabled,
            self.vicidial_write_enabled,
            self.messaging_enabled,
            self.outbox_worker_enabled,
            self.telephony_provisioning_enabled,
            self.vicidial_provisioning_enabled,
            self.pjsip_provisioning_enabled,
            self.postiz_publish_enabled,
        )
        if any(production_switches):
            raise ValueError("live writes and non-TEST_SYN campaigns are disabled")

    def load_secret_files(self) -> None:
        """Load runtime secrets without placing their values in environment metadata."""
        mappings = (
            ("database_url", self.database_url_file),
            ("redis_url", self.redis_url_file),
            ("middleware_secret", self.middleware_secret_file),
            # Ingestion deliberately has no legacy shared-secret fallback.
            ("ingestion_hmac_secret", self.vicidial_callback_hmac_secret_file),
        )
        for attribute, filename in mappings:
            if filename:
                path = Path(filename)
                if not path.is_absolute() or not path.is_file():
                    raise ValueError(f"required {attribute} secret file is unavailable")
                value = path.read_text().strip()
                if not value:
                    raise ValueError(f"required {attribute} secret file is empty")
                setattr(self, attribute, value)

    @property
    def postiz_api_key(self) -> str:
        if not self.postiz_api_key_file:
            return ""
        path = Path(self.postiz_api_key_file)
        if not path.is_absolute() or not path.is_file():
            raise ValueError("Postiz API key file is unavailable")
        value = path.read_text().strip()
        if not value:
            raise ValueError("Postiz API key file is empty")
        return value

    @field_validator("vicidial_authorization_url", "vicidial_edge_url")
    @classmethod
    def validate_vicidial_private_url(cls, value: str) -> str:
        if not value:
            return value
        parsed = urlsplit(value)
        if (
            parsed.scheme != "https"
            or parsed.hostname not in VICIDIAL_PRIVATE_HOSTS
            or parsed.port != VICIDIAL_PRIVATE_PORT
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in ("", "/")
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("VICIdial URL must use an approved private HTTPS endpoint")
        return value.rstrip("/")

    @field_validator("webphone_endpoint_adapter_url")
    @classmethod
    def validate_webphone_endpoint_adapter_url(cls, value: str) -> str:
        if not value:
            return value
        parsed = urlsplit(value)
        if (
            parsed.scheme != "https"
            or parsed.hostname != "authorization.internal.codestra.agency"
            or parsed.port != VICIDIAL_ENDPOINT_ADAPTER_PORT
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in ("", "/")
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("webphone endpoint adapter must use private HTTPS")
        return value.rstrip("/")

    @field_validator(
        "vicidial_ca_file",
        "vicidial_client_cert_file",
        "vicidial_client_key_file",
        "vicidial_crl_file",
    )
    @classmethod
    def validate_vicidial_secret_path(cls, value: str) -> str:
        if not value:
            return value
        path = Path(value)
        if not path.is_absolute() or path.parent != VICIDIAL_SECRET_ROOT:
            raise ValueError("VICIdial mTLS files must be direct children of the secret mount")
        return value

    @property
    def vicidial_mtls_configured(self) -> bool:
        return all(
            (
                self.vicidial_authorization_url,
                self.vicidial_edge_url,
                self.vicidial_ca_file,
                self.vicidial_client_cert_file,
                self.vicidial_client_key_file,
            )
        )

    @property
    def allowed_campaigns(self) -> frozenset[str]:
        return frozenset(
            value.strip()
            for value in self.automation_allowed_campaigns.split(",")
            if value.strip()
        )

    @property
    def auth_ready(self) -> bool:
        return bool(self.middleware_secret and self.ingestion_hmac_secret)

    @property
    def webphone_identity_ready(self) -> bool:
        return all(
            (
                self.webphone_staging_provisioning_enabled,
                self.keycloak_issuer,
                self.keycloak_audience,
                self.keycloak_jwks_url,
                self.keycloak_authorized_parties,
                self.keycloak_userinfo_url,
                self.provisioning_service_url,
                self.provisioning_service_token_url,
                self.provisioning_service_client_id,
                self.provisioning_service_client_secret_file,
                self.provisioning_service_ca_file,
            )
        )

    @property
    def publisher_hmac_keys(self) -> dict[str, bytes]:
        if not self.publisher_hmac_keys_file:
            return {}
        path = Path(self.publisher_hmac_keys_file)
        if not path.is_absolute() or not path.is_file():
            raise ValueError("publisher key file unavailable")
        values = json.loads(path.read_text())
        if not isinstance(values, dict) or not values:
            raise ValueError("publisher key file invalid")
        return {key_id: base64.urlsafe_b64decode(value + "===")
                for key_id, value in values.items()}

    @staticmethod
    def _load_binary_secret(filename: str, label: str) -> bytes:
        path = Path(filename)
        if not filename or not path.is_absolute() or not path.is_file():
            raise ValueError(f"{label} file unavailable")
        try:
            value = base64.urlsafe_b64decode(path.read_text().strip() + "===")
        except (ValueError, TypeError) as exc:
            raise ValueError(f"{label} file invalid") from exc
        if len(value) < 32:
            raise ValueError(f"{label} must contain at least 256 bits")
        return value

    @property
    def quarantine_encryption_key(self) -> bytes:
        value = self._load_binary_secret(
            self.quarantine_encryption_key_file, "quarantine encryption key"
        )
        if len(value) != 32:
            raise ValueError("quarantine encryption key must be 256 bits")
        return value

    @property
    def quarantine_fingerprint_secret(self) -> bytes:
        return self._load_binary_secret(
            self.quarantine_fingerprint_secret_file,
            "quarantine fingerprint secret",
        )

    @property
    def quarantine_reviewer_secret(self) -> bytes:
        return self._load_binary_secret(
            self.quarantine_reviewer_secret_file,
            "quarantine reviewer authorization secret",
        )

    @property
    def enabled_events(self) -> frozenset[str]:
        return frozenset(x.strip() for x in self.enabled_event_types.split(",") if x.strip())

    @property
    def ingestion_clients(self) -> frozenset[str]:
        return frozenset(x.strip() for x in self.allowed_client_instances.split(",") if x.strip())


settings = Settings()
settings.load_secret_files()
if settings.database_url.startswith("postgresql://"):
    settings.database_url = settings.database_url.replace(
        "postgresql://", "postgresql+asyncpg://", 1
    )
settings.validate_safety()
