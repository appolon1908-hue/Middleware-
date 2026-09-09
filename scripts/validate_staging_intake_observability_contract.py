#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_SOURCE = "f6748a58f8d2590520a4f28776770957061cdea1"
EXPECTED_DIGEST = "sha256:695fa3ce3f50ba4d0ae0784976b946a0a683ca731155e4bd3bd9e90a4670b820"
EXPECTED_PROFILE: dict[str, Any] = {
    "profile_id": "codestra-middleware-staging-v1",
    "environment": "staging",
    "database": {
        "scheme": "postgresql",
        "host": "postgresql.middleware-staging.svc.cluster.local",
        "port": 5432,
        "name": "codestra_staging",
        "username": "middleware_staging",
        "sslmode": "verify-full",
    },
    "redis": {
        "scheme": "rediss",
        "host": "redis.middleware-staging.svc.cluster.local",
        "port": 6379,
        "database": 14,
        "username": "middleware-staging",
    },
    "nats": {
        "host": "nats.middleware-staging.svc.cluster.local",
        "port": 4222,
        "stream": "CODESTRA_STAGING_EVENTS",
        "subject_prefix": "codestra.staging.events",
    },
    "temporal": {
        "address": "temporal.middleware-staging.svc.cluster.local:7233",
        "namespace": "codestra-staging",
        "task_queue": "codestra-staging-critical",
    },
    "secret_path_prefix": "/run/secrets/middleware-staging-",
    "production_activation_allowed": False,
}
WEBHOOK_SECRET_NAMES = {
    "WEBHOOK_SECRET_ODOO_INTEGRATION",
    "WEBHOOK_SECRET_N8N_AUTOMATION",
    "WEBHOOK_SECRET_VICIDIAL_ADAPTER",
    "WEBHOOK_SECRET_TELNEXA_GATEWAY",
    "WEBHOOK_SECRET_KLYROW_GATEWAY",
    "WEBHOOK_SECRET_KYQRA_GATEWAY",
    "WEBHOOK_SECRET_POSTLY_ADAPTER",
}


class ContractError(ValueError):
    """The staging contract or one of its bound sources is invalid."""


def require(condition: object, message: str) -> None:
    if not condition:
        raise ContractError(message)


def parse_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        require(
            separator == "=" and bool(key) and key not in values,
            f"invalid or duplicate environment key: {key!r}",
        )
        values[key] = value
    return values


def assert_database_url(value: str) -> None:
    parsed = urlparse(value)
    require(
        parsed.scheme == EXPECTED_PROFILE["database"]["scheme"],
        "database scheme drift",
    )
    require(
        parsed.hostname == EXPECTED_PROFILE["database"]["host"],
        "database host drift",
    )
    require(
        parsed.port == EXPECTED_PROFILE["database"]["port"],
        "database port drift",
    )
    require(
        unquote(parsed.username or "")
        == EXPECTED_PROFILE["database"]["username"],
        "database username drift",
    )
    require(
        parsed.password == "REPLACE_WITH_DATABASE_SECRET",
        "database password placeholder drift",
    )
    require(
        unquote(parsed.path.lstrip("/")) == EXPECTED_PROFILE["database"]["name"],
        "database name drift",
    )
    require(
        parse_qs(parsed.query, strict_parsing=True) == {"sslmode": ["verify-full"]},
        "database TLS policy drift",
    )
    require(not parsed.fragment, "database URL must not contain a fragment")


def assert_redis_url(value: str) -> None:
    parsed = urlparse(value)
    require(
        parsed.scheme == EXPECTED_PROFILE["redis"]["scheme"],
        "Redis scheme drift",
    )
    require(
        parsed.hostname == EXPECTED_PROFILE["redis"]["host"],
        "Redis host drift",
    )
    require(parsed.port == EXPECTED_PROFILE["redis"]["port"], "Redis port drift")
    require(
        unquote(parsed.username or "") == EXPECTED_PROFILE["redis"]["username"],
        "Redis username drift",
    )
    require(
        parsed.password == "REPLACE_WITH_REDIS_SECRET",
        "Redis password placeholder drift",
    )
    require(
        int(parsed.path.lstrip("/")) == EXPECTED_PROFILE["redis"]["database"],
        "Redis database drift",
    )
    require(
        not parsed.query and not parsed.fragment,
        "Redis URL must not contain a query or fragment",
    )


def main() -> None:
    contract = json.loads((ROOT / "contracts/staging-intake-observability-runtime.v1.json").read_text())
    require(contract["schema_version"] == "1.1", "contract schema version drift")
    release = contract["immutable_release"]
    require(release["source_sha"] == EXPECTED_SOURCE, "release source drift")
    require(release["image_digest"] == EXPECTED_DIGEST, "release digest drift")
    require(
        release["image_reference"].endswith("@" + EXPECTED_DIGEST),
        "release image is not digest-bound",
    )
    require(
        re.fullmatch(r"sha256:[0-9a-f]{64}", release["image_digest"]),
        "release digest is invalid",
    )
    require(
        release["schema_head"] == "0003_immutable_event_ledger",
        "release schema head drift",
    )

    profiles = json.loads((ROOT / "config/runtime-profiles.v1.json").read_text())
    require(profiles["schema_version"] == "1.0", "profile schema version drift")
    matches = [item for item in profiles["profiles"] if item["profile_id"] == EXPECTED_PROFILE["profile_id"]]
    require(matches == [EXPECTED_PROFILE], "staging runtime profile drift")
    embedded = release["embedded_runtime_profile"]
    require(embedded == {
        "profile_id": EXPECTED_PROFILE["profile_id"],
        "database_host": EXPECTED_PROFILE["database"]["host"],
        "database_name": EXPECTED_PROFILE["database"]["name"],
        "database_username": EXPECTED_PROFILE["database"]["username"],
        "database_sslmode": EXPECTED_PROFILE["database"]["sslmode"],
        "redis_host": EXPECTED_PROFILE["redis"]["host"],
        "redis_username": EXPECTED_PROFILE["redis"]["username"],
        "redis_database": EXPECTED_PROFILE["redis"]["database"],
        "redis_tls_required": True,
        "production_activation_allowed": False,
    }, "embedded runtime profile drift")

    runtime = contract["runtime"]
    require(runtime["environment"] == "staging", "runtime environment drift")
    require(
        runtime["profile_id"] == EXPECTED_PROFILE["profile_id"],
        "runtime profile binding drift",
    )
    require(
        runtime["allow_in_memory_storage"] is False,
        "in-memory storage must remain disabled",
    )
    require(runtime["host_ports_published"] is False, "host ports must not publish")
    require(runtime["private_network_only"] is True, "runtime must remain private")
    require(
        runtime["dependencies"]
        == ["postgresql-tls", "redis-tls", "keycloak-jwks"],
        "runtime dependency binding drift",
    )
    require(runtime["nats_dispatch_mode"] == "disabled", "NATS dispatch enabled")
    require(
        runtime["temporal_worker_mode"] == "disabled",
        "Temporal worker enabled",
    )
    require(runtime["outbox_dispatch_enabled"] is False, "outbox dispatch enabled")
    require(runtime["production_dialing"] == "DISABLED", "production dialing enabled")
    require(
        runtime["production_activation_configured"] is False,
        "production activation configured",
    )

    endpoints = contract["authenticated_read_endpoints"]
    expected_endpoints = {
        ("GET", "/metrics", "monitoring-readonly", "metrics.read", "middleware-api", False),
        ("GET", "/v1/runtime/safety", "monitoring-readonly", "health.read", "middleware-api", False),
    }
    actual = {(e["method"], e["path"], e["client_id"], e["scope"], e["audience"], e["public_exposure"]) for e in endpoints}
    require(
        actual == expected_endpoints and len(endpoints) == 2,
        "authenticated read endpoint policy drift",
    )
    require(
        contract["token_policy"]["maximum_lifetime_seconds"] == 300,
        "token lifetime policy drift",
    )
    require(
        contract["token_policy"]["minimum_independent_tokens"] == 2,
        "independent token policy drift",
    )
    require(
        contract["token_policy"]["token_values_in_logs_or_artifacts"] is False,
        "token values may enter evidence",
    )
    effects = contract["runtime_recognized_external_effects"]
    require(
        bool(effects) and all(value is False for value in effects.values()),
        "runtime external effect is enabled",
    )
    require(contract["dispatch_controls"] == {
        "OUTBOX_DISPATCH_ENABLED": False,
        "NATS_DISPATCH_MODE": "disabled",
        "TEMPORAL_WORKER_MODE": "disabled",
        "PRODUCTION_DIALING": "DISABLED",
    }, "dispatch control drift")
    require(
        all(
            value is False
            for value in contract["defense_in_depth_compatibility_flags"].values()
        ),
        "compatibility effect is enabled",
    )
    require(
        contract["evidence"]["checksum_state"] == "PENDING_RUNTIME_EXECUTION",
        "runtime checksum evidence was asserted from source",
    )
    require(
        contract["evidence"]["prometheus_target_state"] == "pending",
        "Prometheus evidence was asserted from source",
    )
    require(
        contract["evidence"]["blackbox_target_state"] == "pending",
        "blackbox evidence was asserted from source",
    )
    require(contract["production_authorized"] is False, "production authorized")

    env = parse_env(ROOT / "config/environments/staging.intake-observability.runtime.env.example")
    require(env["APP_ENV"] == "staging", "environment template is not staging")
    require(
        env["RUNTIME_PROFILE_ID"] == EXPECTED_PROFILE["profile_id"],
        "environment profile drift",
    )
    require(env["APP_SOURCE_SHA"] == EXPECTED_SOURCE, "environment source drift")
    require(env["IMAGE_DIGEST"] == EXPECTED_DIGEST, "environment digest drift")
    require(env["SCHEMA_HEAD"] == release["schema_head"], "environment schema drift")
    require(
        env["ALLOW_IN_MEMORY_STORAGE"] == "false",
        "environment permits in-memory storage",
    )
    assert_database_url(env["DATABASE_URL"])
    assert_redis_url(env["REDIS_URL"])
    require(env["NATS_URL"] == "", "NATS URL must remain unset")
    require(
        env["NATS_STREAM"] == EXPECTED_PROFILE["nats"]["stream"],
        "NATS stream drift",
    )
    require(
        env["NATS_SUBJECT_PREFIX"] == EXPECTED_PROFILE["nats"]["subject_prefix"],
        "NATS subject drift",
    )
    require(env["NATS_DISPATCH_MODE"] == "disabled", "NATS dispatch enabled")
    require(env["TEMPORAL_ADDRESS"] == "", "Temporal address must remain unset")
    require(
        env["TEMPORAL_NAMESPACE"] == EXPECTED_PROFILE["temporal"]["namespace"],
        "Temporal namespace drift",
    )
    require(
        env["TEMPORAL_TASK_QUEUE"] == EXPECTED_PROFILE["temporal"]["task_queue"],
        "Temporal task queue drift",
    )
    require(
        env["TEMPORAL_WORKER_MODE"] == "disabled",
        "Temporal worker enabled",
    )
    require(env["PRODUCTION_DIALING"] == "DISABLED", "production dialing enabled")
    for name in effects:
        require(env[name] == "false", f"environment effect enabled: {name}")
    require(env["OUTBOX_DISPATCH_ENABLED"] == "false", "outbox dispatch enabled")
    for name in contract["defense_in_depth_compatibility_flags"]:
        require(env[name] == "false", f"compatibility effect enabled: {name}")
    require(
        WEBHOOK_SECRET_NAMES.issubset(env),
        "environment webhook secret placeholders are incomplete",
    )
    require(
        all(
            len(env[name]) >= 32 and env[name].startswith("REPLACE_WITH_")
            for name in WEBHOOK_SECRET_NAMES
        ),
        "environment webhook secret placeholder is unsafe",
    )

    factory_source = (ROOT / "app/appolon_factory.py").read_text()
    security_source = (ROOT / "app/security.py").read_text()
    require('@app.get("/metrics")' in factory_source, "metrics route is missing")
    require('required_scope="metrics.read"' in factory_source, "metrics scope drift")
    require(
        '@app.get("/v1/runtime/safety", response_model=RuntimeSafetyReadback)'
        in factory_source,
        "runtime safety route is missing",
    )
    require(
        'required_scope="health.read"' in factory_source,
        "runtime safety scope drift",
    )
    require(
        "expires_at - issued_at > 300" in security_source,
        "token lifetime enforcement is missing",
    )
    print("MIDDLEWARE_STAGING_INTAKE_OBSERVABILITY_CONTRACT=PASS")


if __name__ == "__main__":
    main()
