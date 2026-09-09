#!/usr/bin/env python3
from __future__ import annotations

import ast
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
GOVERNED_READ_PATHS = {"/metrics", "/v1/runtime/safety"}
EXPECTED_INCLUDED_ROUTERS = {
    "n8n_control_plane_router": "n8n_control_plane",
    "operations_dashboard_router": "operations_dashboard",
    "operations_router": "operations",
    "control_api_router": "control_api",
    "compatibility_api_router": "compatibility_api",
    "domain_api_router": "domain_api",
    "webhook_api_router": "webhook_api",
}
EXPECTED_NESTED_ROUTER_INCLUDES = {
    "n8n_control_plane": {"v2_router"},
    "operations_dashboard": set(),
    "operations": set(),
    "control_api": set(),
    "compatibility_api": set(),
    "domain_api": {"calling_router"},
    "webhook_api": set(),
    "telephony_api": set(),
}
ROUTE_REGISTRATION_METHODS = {
    "add_api_route",
    "add_route",
    "api_route",
    "get",
    "head",
    "options",
    "patch",
    "post",
    "put",
    "route",
    "trace",
    "websocket",
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


def authenticated_get_routes(source: str) -> dict[str, tuple[str, str]]:
    """Extract route authentication bindings from executable Python syntax."""
    try:
        tree = ast.parse(source, filename="app/appolon_factory.py")
    except SyntaxError as error:
        raise ContractError("application factory is not valid Python") from error

    factories = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "create_app"
    ]
    require(len(factories) == 1, "application factory definition is not unique")

    def attribute_path(node: ast.expr) -> list[str] | None:
        parts: list[str] = []
        current = node
        while isinstance(current, ast.Attribute):
            parts.append(current.attr)
            current = current.value
        if not isinstance(current, ast.Name):
            return None
        parts.append(current.id)
        return list(reversed(parts))

    def static_string(node: ast.expr) -> str | None:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            left = static_string(node.left)
            right = static_string(node.right)
            if left is not None and right is not None:
                return left + right
        if isinstance(node, ast.JoinedStr):
            values: list[str] = []
            for item in node.values:
                if not isinstance(item, ast.Constant) or not isinstance(item.value, str):
                    return None
                values.append(item.value)
            return "".join(values)
        return None

    def route_pattern(node: ast.expr) -> str | None:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return re.escape(node.value)
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            left = route_pattern(node.left)
            right = route_pattern(node.right)
            if left is not None and right is not None:
                return left + right
        if isinstance(node, ast.JoinedStr):
            parts: list[str] = []
            for item in node.values:
                if isinstance(item, ast.Constant) and isinstance(item.value, str):
                    parts.append(re.escape(item.value))
                elif isinstance(item, ast.FormattedValue):
                    parts.append(".*")
                else:
                    return None
            return "".join(parts)
        if isinstance(node, (ast.Name, ast.Attribute, ast.Subscript)):
            return ".*"
        return None

    def router_prefix(module_tree: ast.Module) -> str:
        prefixes: list[str] = []
        for statement in module_tree.body:
            if not isinstance(statement, (ast.Assign, ast.AnnAssign)):
                continue
            targets = statement.targets if isinstance(statement, ast.Assign) else [statement.target]
            if not any(isinstance(target, ast.Name) and target.id == "router" for target in targets):
                continue
            value = statement.value
            if not (
                isinstance(value, ast.Call)
                and isinstance(value.func, ast.Name)
                and value.func.id == "APIRouter"
            ):
                continue
            prefix_values = [
                static_string(keyword.value)
                for keyword in value.keywords
                if keyword.arg == "prefix"
            ]
            if len(prefix_values) > 1 or any(item is None for item in prefix_values):
                raise ContractError("included router prefix is dynamic or ambiguous")
            prefix_value = prefix_values[0] if prefix_values else ""
            if prefix_value is None:
                raise ContractError("included router prefix is dynamic or ambiguous")
            prefixes.append(prefix_value)
        require(len(prefixes) == 1, "included router definition is not unique")
        return prefixes[0]

    def registered_paths(
        module_tree: ast.Module,
        *,
        prefix: str = "",
        allow_webhook_dynamic: bool = False,
    ) -> list[str]:
        paths: list[str] = []
        webhook_registrations = 0
        for candidate in ast.walk(module_tree):
            if (
                not isinstance(candidate, ast.Call)
                or not isinstance(candidate.func, ast.Attribute)
                or candidate.func.attr not in ROUTE_REGISTRATION_METHODS
                or not candidate.args
            ):
                continue
            receiver = attribute_path(candidate.func.value)
            if receiver is None or not (
                receiver[0] == "app"
                or receiver[-1] == "router"
                or receiver[-1].endswith("_router")
            ):
                continue
            path = static_string(candidate.args[0])
            if path is not None and path.startswith("/"):
                paths.append(prefix.rstrip("/") + path)
                continue
            methods = [
                keyword.value
                for keyword in candidate.keywords
                if keyword.arg == "methods"
            ]
            if (
                allow_webhook_dynamic
                and receiver == ["app"]
                and candidate.func.attr == "add_api_route"
                and attribute_path(candidate.args[0]) == ["route", "path"]
                and len(methods) == 1
                and isinstance(methods[0], (ast.List, ast.Tuple))
                and len(methods[0].elts) == 1
                and isinstance(methods[0].elts[0], ast.Constant)
                and methods[0].elts[0].value == "POST"
            ):
                webhook_registrations += 1
                continue
            pattern = route_pattern(candidate.args[0])
            if pattern is None:
                raise ContractError("route registration path cannot be proven safe")
            prefixed_pattern = re.escape(prefix.rstrip("/")) + pattern
            require(
                not any(
                    re.fullmatch(prefixed_pattern, governed) is not None
                    for governed in GOVERNED_READ_PATHS
                ),
                "dynamic route registration may shadow a governed GET route",
            )
        require(
            webhook_registrations == (1 if allow_webhook_dynamic else 0),
            "dynamic webhook route registration is missing or ambiguous",
        )
        return paths

    imported_routers: dict[str, str] = {}
    for statement in tree.body:
        if not isinstance(statement, ast.ImportFrom) or statement.level != 1:
            continue
        for imported in statement.names:
            alias = imported.asname
            if alias in EXPECTED_INCLUDED_ROUTERS and imported.name == "router":
                if statement.module != EXPECTED_INCLUDED_ROUTERS[alias]:
                    raise ContractError(f"included router import drift: {alias}")
                require(alias not in imported_routers, f"duplicate router import: {alias}")
                imported_routers[alias] = statement.module
    require(
        imported_routers == EXPECTED_INCLUDED_ROUTERS,
        "application factory included-router imports are incomplete",
    )
    rebound_router_names = {
        candidate.id
        for candidate in ast.walk(tree)
        if isinstance(candidate, ast.Name)
        and isinstance(candidate.ctx, (ast.Store, ast.Del))
        and candidate.id in EXPECTED_INCLUDED_ROUTERS
    }
    require(not rebound_router_names, "included router binding is reassigned")

    include_calls = [
        candidate
        for candidate in ast.walk(factories[0])
        if isinstance(candidate, ast.Call)
        and attribute_path(candidate.func) == ["app", "include_router"]
    ]
    included_names: list[str] = []
    for call in include_calls:
        if (
            len(call.args) != 1
            or not isinstance(call.args[0], ast.Name)
            or call.args[0].id not in EXPECTED_INCLUDED_ROUTERS
        ):
            raise ContractError("application factory includes an unapproved router")
        included_names.append(call.args[0].id)
    require(
        len(included_names) == len(EXPECTED_INCLUDED_ROUTERS)
        and set(included_names) == set(EXPECTED_INCLUDED_ROUTERS),
        "application factory included-router calls are incomplete or duplicated",
    )

    def authentication_binding(node: ast.AsyncFunctionDef) -> tuple[str, str]:
        request_arguments = [
            argument.arg
            for argument in (*node.args.posonlyargs, *node.args.args)
            if argument.arg == "request"
        ]
        require(
            request_arguments == ["request"],
            "governed GET route request binding is missing or ambiguous",
        )
        statements = list(node.body)
        if (
            statements
            and isinstance(statements[0], ast.Expr)
            and isinstance(statements[0].value, ast.Constant)
            and isinstance(statements[0].value.value, str)
        ):
            statements = statements[1:]
        if not statements:
            raise ContractError("governed GET route body is empty")
        first = statements[0]
        if not isinstance(first, ast.Expr) or not isinstance(first.value, ast.Await):
            raise ContractError(
                "governed GET route must authenticate before executing its body"
            )
        call = first.value.value
        if not isinstance(call, ast.Call) or attribute_path(call.func) != [
            "request",
            "app",
            "state",
            "runtime",
            "tokens",
            "verify",
        ]:
            raise ContractError(
                "governed GET route does not await the runtime token verifier"
            )
        if len(call.args) != 1 or not isinstance(call.args[0], ast.Call):
            raise ContractError(
                "governed GET route does not verify its Authorization header"
            )
        header_call = call.args[0]
        if (
            attribute_path(header_call.func) != ["request", "headers", "get"]
            or len(header_call.args) != 2
            or not all(isinstance(item, ast.Constant) for item in header_call.args)
            or [
                item.value
                for item in header_call.args
                if isinstance(item, ast.Constant)
            ]
            != ["Authorization", ""]
        ):
            raise ContractError(
                "governed GET route does not verify its Authorization header"
            )
        require(
            all(keyword.arg is not None for keyword in call.keywords),
            "governed GET route authentication uses expanded keywords",
        )
        keywords = {item.arg: item.value for item in call.keywords if item.arg}
        require(
            set(keywords) == {"expected_client_id", "required_scope"},
            "governed GET route authentication keywords are not exact",
        )
        client = keywords["expected_client_id"]
        scope = keywords["required_scope"]
        if (
            not isinstance(client, ast.Constant)
            or not isinstance(client.value, str)
            or not isinstance(scope, ast.Constant)
            or not isinstance(scope.value, str)
        ):
            raise ContractError(
                "governed GET route authentication binding is not static"
            )
        return client.value, scope.value

    routes: dict[str, tuple[str, str]] = {}
    for node in factories[0].body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        paths: list[str] = []
        for decorator in node.decorator_list:
            if (
                isinstance(decorator, ast.Call)
                and isinstance(decorator.func, ast.Attribute)
                and isinstance(decorator.func.value, ast.Name)
                and decorator.func.value.id == "app"
                and decorator.func.attr == "get"
                and decorator.args
                and isinstance(decorator.args[0], ast.Constant)
                and isinstance(decorator.args[0].value, str)
            ):
                paths.append(decorator.args[0].value)
        paths = [path for path in paths if path in GOVERNED_READ_PATHS]
        if not paths:
            continue
        require(
            len(node.decorator_list) == 1,
            "governed GET route has a handler-replacing decorator",
        )
        for path in paths:
            require(path not in routes, f"duplicate GET route in app factory: {path}")
            if not isinstance(node, ast.AsyncFunctionDef):
                raise ContractError(
                    f"governed GET route must be asynchronous: {path}"
                )
            routes[path] = authentication_binding(node)

    all_registered_paths = registered_paths(tree, allow_webhook_dynamic=True)
    router_modules = [*EXPECTED_INCLUDED_ROUTERS.values(), "telephony_api"]
    for module_name in router_modules:
        module_path = ROOT / "app" / f"{module_name}.py"
        try:
            module_tree = ast.parse(
                module_path.read_text(encoding="utf-8"),
                filename=module_path.relative_to(ROOT).as_posix(),
            )
        except (OSError, SyntaxError) as error:
            raise ContractError(
                f"included router source is unavailable or invalid: {module_name}"
            ) from error
        all_registered_paths.extend(
            registered_paths(module_tree, prefix=router_prefix(module_tree))
        )
        nested_calls = [
            candidate
            for candidate in ast.walk(module_tree)
            if isinstance(candidate, ast.Call)
            and attribute_path(candidate.func) == ["router", "include_router"]
        ]
        nested_names = [
            call.args[0].id
            for call in nested_calls
            if len(call.args) == 1 and isinstance(call.args[0], ast.Name)
        ]
        require(
            len(nested_names) == len(nested_calls)
            and set(nested_names) == EXPECTED_NESTED_ROUTER_INCLUDES[module_name],
            f"included router graph drift: {module_name}",
        )
    for path in GOVERNED_READ_PATHS:
        require(
            all_registered_paths.count(path) == 1,
            f"governed GET route registration is missing or ambiguous: {path}",
        )
    return routes


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
    webhook_contract = json.loads(
        (ROOT / "config/api-webhook-contracts.json").read_text(encoding="utf-8")
    )
    webhook_paths = [
        item.get("path")
        for item in webhook_contract.get("webhooks", [])
        if isinstance(item, dict)
    ]
    require(
        webhook_paths
        and len(webhook_paths) == len(set(webhook_paths))
        and all(isinstance(path, str) and path.startswith("/") for path in webhook_paths)
        and GOVERNED_READ_PATHS.isdisjoint(webhook_paths),
        "dynamic webhook paths are invalid or shadow a governed GET route",
    )
    route_bindings = authenticated_get_routes(factory_source)
    require(
        route_bindings.get("/metrics")
        == ("monitoring-readonly", "metrics.read"),
        "metrics authentication binding drift",
    )
    require(
        route_bindings.get("/v1/runtime/safety")
        == ("monitoring-readonly", "health.read"),
        "runtime safety authentication binding drift",
    )
    require(
        "expires_at - issued_at > 300" in security_source,
        "token lifetime enforcement is missing",
    )
    print("MIDDLEWARE_STAGING_INTAKE_OBSERVABILITY_CONTRACT=PASS")


if __name__ == "__main__":
    main()
