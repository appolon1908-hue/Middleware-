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
EXPECTED_DIGEST = (
    "sha256:695fa3ce3f50ba4d0ae0784976b946a0a683ca731155e4bd3bd9e90a4670b820"
)
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
    "campaign_design_router": "campaign_design_api",
    "n8n_control_plane_router": "n8n_control_plane",
    "operations_dashboard_router": "operations_dashboard",
    "operations_router": "operations",
    "control_api_router": "control_api",
    "compatibility_api_router": "compatibility_api",
    "domain_api_router": "domain_api",
    "webhook_api_router": "webhook_api",
    "monitoring_router": "monitoring.routes",
}
EXPECTED_SIDE_EFFECT_ROUTER_MODULES = {"provider_control_api"}
EXPECTED_ROUTE_HELPERS = {"register_survey_routes": "survey_routes"}
ROUTE_REGISTRATION_METHODS = {
    "add_api_route",
    "add_route",
    "api_route",
    "get",
    "head",
    "mount",
    "options",
    "patch",
    "post",
    "put",
    "route",
    "trace",
    "websocket",
}
WORKFLOW_REQUIRED_PATHS = {
    ".github/workflows/staging-intake-observability-contract.yml",
    "app/**/*.py",
    "config/api-webhook-contracts.json",
    "config/environments/staging.intake-observability.runtime.env.example",
    "config/provider-operation-policy.json",
    "config/runtime-profiles.v1.json",
    "contracts/staging-intake-observability-runtime.v1.json",
    "scripts/validate_staging_intake_observability_contract.py",
    "tests/test_staging_intake_observability_contract_validation.py",
}


class ContractError(ValueError):
    """The staging contract or one of its bound sources is invalid."""


def require(condition: object, message: str) -> None:
    if not condition:
        raise ContractError(message)


def workflow_trigger_paths(source: str, trigger: str) -> set[str]:
    """Read one workflow paths filter without accepting another YAML section."""
    lines = source.splitlines()
    trigger_header = f"  {trigger}:"
    try:
        trigger_index = lines.index(trigger_header)
    except ValueError as error:
        raise ContractError(f"workflow {trigger} trigger is missing") from error
    paths_index: int | None = None
    for index in range(trigger_index + 1, len(lines)):
        line = lines[index]
        if line.startswith("  ") and not line.startswith("    ") and line.strip():
            break
        if line == "    paths:":
            paths_index = index
            break
    require(paths_index is not None, f"workflow {trigger} paths filter is missing")
    paths: list[str] = []
    if paths_index is None:
        raise ContractError(f"workflow {trigger} paths filter is missing")
    for line in lines[paths_index + 1 :]:
        if line.startswith("      - "):
            raw = line.removeprefix("      - ").strip()
            try:
                value = json.loads(raw)
            except json.JSONDecodeError as error:
                raise ContractError(
                    f"workflow {trigger} path is not a JSON string"
                ) from error
            require(
                isinstance(value, str) and bool(value),
                f"workflow {trigger} path is invalid",
            )
            paths.append(value)
            continue
        if line.strip() and not line.startswith("      "):
            break
    require(
        len(paths) == len(set(paths)),
        f"workflow {trigger} paths contain duplicates",
    )
    return set(paths)


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
        unquote(parsed.username or "") == EXPECTED_PROFILE["database"]["username"],
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


def authenticated_get_routes(
    source: str,
    *,
    webhook_paths: list[str],
    provider_paths: list[str],
) -> dict[str, tuple[str, str]]:
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

    def current_scope_nodes(node: ast.AST) -> list[ast.AST]:
        nodes: list[ast.AST] = []

        def visit(candidate: ast.AST) -> None:
            nodes.append(candidate)
            if isinstance(
                candidate,
                (ast.AsyncFunctionDef, ast.ClassDef, ast.FunctionDef, ast.Lambda),
            ):
                return
            for child in ast.iter_child_nodes(candidate):
                visit(child)

        body = (
            node.body
            if isinstance(
                node,
                (ast.AsyncFunctionDef, ast.ClassDef, ast.FunctionDef, ast.Module),
            )
            else []
        )
        for statement in body:
            visit(statement)
        return nodes

    request_bindings: list[str] = []
    for candidate in current_scope_nodes(tree):
        if isinstance(candidate, ast.ImportFrom):
            for imported in candidate.names:
                bound = imported.asname or imported.name
                if bound != "Request":
                    continue
                if (
                    candidate.level == 0
                    and candidate.module == "fastapi"
                    and imported.name == "Request"
                    and imported.asname is None
                ):
                    request_bindings.append("fastapi.Request")
                else:
                    request_bindings.append("another import")
        elif isinstance(candidate, ast.Import):
            for imported in candidate.names:
                if (imported.asname or imported.name.split(".", 1)[0]) == "Request":
                    request_bindings.append("another import")
        elif isinstance(
            candidate, (ast.AsyncFunctionDef, ast.ClassDef, ast.FunctionDef)
        ):
            if candidate.name == "Request":
                request_bindings.append("a definition")
        elif (
            isinstance(candidate, ast.Name)
            and candidate.id == "Request"
            and isinstance(candidate.ctx, (ast.Store, ast.Del))
        ):
            request_bindings.append("an assignment")
        elif isinstance(candidate, ast.ExceptHandler) and candidate.name == "Request":
            request_bindings.append("an exception target")
        elif isinstance(candidate, (ast.MatchAs, ast.MatchStar)):
            if candidate.name == "Request":
                request_bindings.append("a pattern target")
        elif isinstance(candidate, ast.MatchMapping) and candidate.rest == "Request":
            request_bindings.append("a pattern target")
    require(
        request_bindings == ["fastapi.Request"],
        "FastAPI Request import is missing, ambiguous, or rebound",
    )

    factory = factories[0]
    app_assignments = [
        statement
        for statement in factory.body
        if isinstance(statement, ast.Assign)
        and len(statement.targets) == 1
        and isinstance(statement.targets[0], ast.Name)
        and statement.targets[0].id == "app"
        and isinstance(statement.value, ast.Call)
        and isinstance(statement.value.func, ast.Name)
        and statement.value.func.id == "FastAPI"
    ]
    require(len(app_assignments) == 1, "FastAPI app binding is missing or ambiguous")
    app_assignment_value = app_assignments[0].value
    if not isinstance(app_assignment_value, ast.Call):
        raise ContractError("FastAPI app binding is missing or ambiguous")
    require(
        not any(
            keyword.arg in {None, "middleware"}
            for keyword in app_assignment_value.keywords
        ),
        "FastAPI constructor middleware is not permitted",
    )
    canonical_app_target = app_assignments[0].targets[0]
    factory_scope = current_scope_nodes(ast.Module(body=factory.body, type_ignores=[]))
    require(
        not any(
            isinstance(candidate, ast.Name)
            and candidate.id == "app"
            and isinstance(candidate.ctx, (ast.Store, ast.Del))
            and candidate is not canonical_app_target
            for candidate in factory_scope
        ),
        "FastAPI app binding is reassigned",
    )
    for candidate in ast.walk(factory):
        value: ast.expr | None = None
        if isinstance(candidate, (ast.Assign, ast.AnnAssign, ast.NamedExpr)):
            value = candidate.value
        if isinstance(value, ast.Name) and value.id == "app":
            raise ContractError("FastAPI app alias makes route registration ambiguous")

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

    def static_string(
        node: ast.expr,
        names: dict[str, str] | None = None,
    ) -> str | None:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, ast.Name) and names is not None:
            return names.get(node.id)
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            left = static_string(node.left, names)
            right = static_string(node.right, names)
            if left is not None and right is not None:
                return left + right
        if isinstance(node, ast.JoinedStr):
            values: list[str] = []
            for item in node.values:
                if not isinstance(item, ast.Constant) or not isinstance(
                    item.value, str
                ):
                    return None
                values.append(item.value)
            return "".join(values)
        return None

    def module_string_constants(module_tree: ast.Module) -> dict[str, str]:
        constants: dict[str, str] = {}
        assignments: dict[str, list[ast.expr]] = {}
        for statement in module_tree.body:
            if isinstance(statement, ast.Assign) and len(statement.targets) == 1:
                target = statement.targets[0]
                value = statement.value
            elif isinstance(statement, ast.AnnAssign) and statement.value is not None:
                target = statement.target
                value = statement.value
            else:
                continue
            if isinstance(target, ast.Name):
                assignments.setdefault(target.id, []).append(value)
        unresolved = {
            name: values[0] for name, values in assignments.items() if len(values) == 1
        }
        changed = True
        while changed:
            changed = False
            for name, value in list(unresolved.items()):
                resolved = static_string(value, constants)
                if resolved is not None:
                    constants[name] = resolved
                    unresolved.pop(name)
                    changed = True
        return constants

    def route_template_pattern(value: str) -> str:
        parts: list[str] = []
        index = 0
        while index < len(value):
            opening = value.find("{", index)
            closing = value.find("}", index)
            if opening == -1:
                require(closing == -1, "route template contains an unmatched brace")
                parts.append(re.escape(value[index:]))
                break
            require(
                closing == -1 or opening < closing,
                "route template contains an unmatched brace",
            )
            parts.append(re.escape(value[index:opening]))
            end = value.find("}", opening + 1)
            require(end != -1, "route template contains an unmatched brace")
            token = value[opening + 1 : end]
            require(
                bool(token) and "{" not in token,
                "route template parameter is malformed",
            )
            name, separator, converter = token.partition(":")
            require(
                bool(name)
                and name.isidentifier()
                and (not separator or bool(converter)),
                "route template parameter is malformed",
            )
            parts.append(
                "[^/]+" if converter in {"", "float", "int", "str", "uuid"} else ".*"
            )
            index = end + 1
        return "".join(parts)

    def route_pattern(node: ast.expr) -> str | None:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return route_template_pattern(node.value)
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            left = route_pattern(node.left)
            right = route_pattern(node.right)
            if left is not None and right is not None:
                return left + right
        if isinstance(node, ast.JoinedStr):
            parts: list[str] = []
            for item in node.values:
                if isinstance(item, ast.Constant) and isinstance(item.value, str):
                    parts.append(route_template_pattern(item.value))
                elif isinstance(item, ast.FormattedValue):
                    parts.append(".*")
                else:
                    return None
            return "".join(parts)
        if isinstance(node, (ast.Name, ast.Attribute, ast.Subscript)):
            return ".*"
        return None

    def registration_path_argument(call: ast.Call) -> ast.expr:
        require(
            not any(keyword.arg is None for keyword in call.keywords),
            "route registration uses expanded keywords",
        )
        candidates: list[ast.expr] = list(call.args[:1])
        candidates.extend(
            keyword.value for keyword in call.keywords if keyword.arg == "path"
        )
        require(
            len(candidates) == 1,
            "route registration path is missing or ambiguous",
        )
        return candidates[0]

    def exact_methods(call: ast.Call) -> list[str] | None:
        values = [
            keyword.value for keyword in call.keywords if keyword.arg == "methods"
        ]
        if len(values) != 1 or not isinstance(values[0], (ast.List, ast.Tuple)):
            return None
        methods: list[str] = []
        for item in values[0].elts:
            if not isinstance(item, ast.Constant) or not isinstance(item.value, str):
                return None
            methods.append(item.value)
        return methods

    def joined_path(prefix: str, path: str) -> str:
        if not prefix:
            return path or "/"
        if not path:
            return prefix
        return prefix.rstrip("/") + "/" + path.lstrip("/")

    def registered_paths(
        module_tree: ast.Module,
        *,
        module_name: str,
        receiver_prefixes: dict[str, str],
        static_names: dict[str, str] | None = None,
        allow_webhook_dynamic: bool = False,
        allow_provider_dynamic: bool = False,
        allow_http_middleware: bool = False,
    ) -> list[str]:
        paths: list[str] = []
        webhook_registrations = 0
        provider_registrations = 0

        def record_path(path: str, *, prefix: str, mount: bool) -> None:
            full_path = joined_path(prefix, path)
            pattern = route_template_pattern(full_path)
            if mount:
                pattern = pattern.rstrip("/")
                pattern = (pattern or re.escape("/")) + (
                    ".*" if full_path.rstrip("/") in {"", "/"} else "(?:/.*)?"
                )
            matches = {
                governed
                for governed in GOVERNED_READ_PATHS
                if re.fullmatch(pattern, governed) is not None
            }
            if matches and (mount or full_path not in GOVERNED_READ_PATHS):
                raise ContractError(
                    "route registration may shadow a governed GET route"
                )
            if full_path in GOVERNED_READ_PATHS:
                paths.append(full_path)

        for candidate in ast.walk(module_tree):
            if not isinstance(candidate, ast.Call) or not isinstance(
                candidate.func, ast.Attribute
            ):
                continue
            receiver = attribute_path(candidate.func.value)
            if receiver is None or len(receiver) != 1:
                continue
            receiver_name = receiver[0]
            if receiver_name not in receiver_prefixes:
                if receiver_name == "app" or receiver_name.endswith("router"):
                    raise ContractError("route registration receiver is not tracked")
                continue
            if candidate.func.attr == "add_middleware":
                raise ContractError(
                    f"custom middleware is not permitted: {module_name}:{candidate.lineno}"
                )
            if candidate.func.attr == "middleware":
                require(
                    allow_http_middleware,
                    f"untracked middleware registration: {module_name}:{candidate.lineno}",
                )
                continue
            if candidate.func.attr not in ROUTE_REGISTRATION_METHODS:
                continue
            path_argument = registration_path_argument(candidate)
            if (
                allow_webhook_dynamic
                and receiver == ["app"]
                and candidate.func.attr == "add_api_route"
                and attribute_path(path_argument) == ["route", "path"]
                and exact_methods(candidate) == ["POST"]
            ):
                webhook_registrations += 1
                for configured_path in webhook_paths:
                    record_path(configured_path, prefix="", mount=False)
                continue
            if (
                allow_provider_dynamic
                and receiver == ["router"]
                and candidate.func.attr == "add_api_route"
                and attribute_path(path_argument) == ["_spec", "route"]
                and exact_methods(candidate) == ["POST"]
            ):
                provider_registrations += 1
                for configured_path in provider_paths:
                    record_path(configured_path, prefix="", mount=False)
                continue
            prefix = receiver_prefixes[receiver_name]
            path = static_string(path_argument, static_names)
            if path is not None:
                record_path(
                    path,
                    prefix=prefix,
                    mount=candidate.func.attr == "mount",
                )
                continue
            pattern = route_pattern(path_argument)
            if pattern is None:
                raise ContractError(
                    "route registration path cannot be proven safe: "
                    f"{module_name}:{candidate.lineno}"
                )
            prefixed_pattern = route_template_pattern(prefix.rstrip("/")) + pattern
            if candidate.func.attr == "mount":
                prefixed_pattern += ".*"
            require(
                not any(
                    re.fullmatch(prefixed_pattern, governed) is not None
                    for governed in GOVERNED_READ_PATHS
                ),
                "dynamic route registration may shadow a governed GET route: "
                f"{module_name}:{candidate.lineno}",
            )
        require(
            webhook_registrations == (1 if allow_webhook_dynamic else 0),
            "dynamic webhook route registration is missing or ambiguous",
        )
        require(
            provider_registrations == (1 if allow_provider_dynamic else 0),
            "dynamic provider route registration is missing or ambiguous",
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
                require(
                    alias not in imported_routers, f"duplicate router import: {alias}"
                )
                imported_routers[alias] = statement.module
    require(
        imported_routers == EXPECTED_INCLUDED_ROUTERS,
        "application factory included-router imports are incomplete",
    )
    imported_route_helpers: dict[str, str] = {}
    for statement in tree.body:
        if not isinstance(statement, ast.ImportFrom) or statement.level != 1:
            continue
        for imported in statement.names:
            bound = imported.asname or imported.name
            if bound not in EXPECTED_ROUTE_HELPERS:
                continue
            require(
                imported.asname is None
                and statement.module == EXPECTED_ROUTE_HELPERS[bound],
                f"route helper import drift: {bound}",
            )
            require(
                bound not in imported_route_helpers,
                f"duplicate route helper import: {bound}",
            )
            if statement.module is None:
                raise ContractError(f"route helper import drift: {bound}")
            imported_route_helpers[bound] = statement.module
    require(
        imported_route_helpers == EXPECTED_ROUTE_HELPERS,
        "application factory route-helper imports are incomplete",
    )
    side_effect_modules = {
        imported.name
        for statement in tree.body
        if isinstance(statement, ast.ImportFrom)
        and statement.level == 1
        and statement.module is None
        for imported in statement.names
    }
    require(
        side_effect_modules == EXPECTED_SIDE_EFFECT_ROUTER_MODULES,
        "application factory side-effect router imports drifted",
    )
    rebound_router_names = {
        candidate.id
        for candidate in current_scope_nodes(tree)
        if isinstance(candidate, ast.Name)
        and isinstance(candidate.ctx, (ast.Store, ast.Del))
        and candidate.id in EXPECTED_INCLUDED_ROUTERS
    }
    require(not rebound_router_names, "included router binding is reassigned")
    rebound_helper_names = {
        candidate.id
        for candidate in current_scope_nodes(tree)
        if isinstance(candidate, ast.Name)
        and isinstance(candidate.ctx, (ast.Store, ast.Del))
        and candidate.id in EXPECTED_ROUTE_HELPERS
    }
    require(not rebound_helper_names, "route helper binding is reassigned")

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
    for helper_name in EXPECTED_ROUTE_HELPERS:
        helper_calls = [
            candidate
            for candidate in ast.walk(factory)
            if isinstance(candidate, ast.Call)
            and isinstance(candidate.func, ast.Name)
            and candidate.func.id == helper_name
        ]
        require(
            len(helper_calls) == 1
            and len(helper_calls[0].args) == 1
            and not helper_calls[0].keywords
            and isinstance(helper_calls[0].args[0], ast.Name)
            and helper_calls[0].args[0].id == "app",
            f"route helper call is missing or ambiguous: {helper_name}",
        )

    app_argument_calls = [
        candidate
        for candidate in factory_scope
        if isinstance(candidate, ast.Call)
        and any(
            isinstance(argument, ast.Name) and argument.id == "app"
            for argument in candidate.args
        )
    ]

    def approved_app_argument_call(call: ast.Call) -> bool:
        if (
            isinstance(call.func, ast.Name)
            and call.func.id in EXPECTED_ROUTE_HELPERS
            and len(call.args) == 1
            and not call.keywords
        ):
            return True
        return (
            isinstance(call.func, ast.Name)
            and call.func.id == "setattr"
            and len(call.args) == 3
            and not call.keywords
            and isinstance(call.args[0], ast.Name)
            and call.args[0].id == "app"
            and isinstance(call.args[1], ast.Constant)
            and call.args[1].value == "openapi"
            and isinstance(call.args[2], ast.Name)
            and call.args[2].id == "canonical_openapi"
        )

    require(
        len(app_argument_calls) == len(EXPECTED_ROUTE_HELPERS) + 1
        and all(approved_app_argument_call(call) for call in app_argument_calls),
        "FastAPI app is passed to an untracked registration helper",
    )

    middleware_definitions: list[ast.AsyncFunctionDef] = []
    middleware_decorators: list[ast.Call] = []
    for candidate in ast.walk(factory):
        if not isinstance(candidate, (ast.AsyncFunctionDef, ast.FunctionDef)):
            continue
        matched: list[ast.Call] = []
        for decorator in candidate.decorator_list:
            if isinstance(decorator, ast.Call) and attribute_path(decorator.func) == [
                "app",
                "middleware",
            ]:
                matched.append(decorator)
        if not matched:
            continue
        require(
            isinstance(candidate, ast.AsyncFunctionDef)
            and len(candidate.decorator_list) == 1
            and len(matched) == 1,
            "HTTP middleware definition is ambiguous",
        )
        if not isinstance(candidate, ast.AsyncFunctionDef):
            raise ContractError("HTTP middleware definition is ambiguous")
        middleware_definitions.append(candidate)
        middleware_decorators.extend(matched)
    all_middleware_calls = [
        candidate
        for candidate in ast.walk(factory)
        if isinstance(candidate, ast.Call)
        and attribute_path(candidate.func) == ["app", "middleware"]
    ]
    require(
        len(middleware_definitions) == 1
        and len(all_middleware_calls) == 1
        and all_middleware_calls[0] is middleware_decorators[0],
        "HTTP middleware registration is missing or ambiguous",
    )
    middleware = middleware_definitions[0]
    decorator = middleware_decorators[0]
    require(
        len(decorator.args) == 1
        and not decorator.keywords
        and isinstance(decorator.args[0], ast.Constant)
        and decorator.args[0].value == "http",
        "HTTP middleware registration is not exact",
    )
    middleware_arguments = [*middleware.args.posonlyargs, *middleware.args.args]
    require(
        [argument.arg for argument in middleware_arguments] == ["request", "call_next"]
        and isinstance(middleware_arguments[0].annotation, ast.Name)
        and middleware_arguments[0].annotation.id == "Request"
        and not middleware.args.defaults
        and middleware.args.vararg is None
        and middleware.args.kwarg is None
        and not middleware.args.kwonlyargs,
        "HTTP middleware parameters are not exact",
    )
    middleware_scope = current_scope_nodes(middleware)
    delegated_calls = [
        candidate
        for candidate in middleware_scope
        if isinstance(candidate, ast.Await)
        and isinstance(candidate.value, ast.Call)
        and isinstance(candidate.value.func, ast.Name)
        and candidate.value.func.id == "call_next"
        and len(candidate.value.args) == 1
        and isinstance(candidate.value.args[0], ast.Name)
        and candidate.value.args[0].id == "request"
        and not candidate.value.keywords
    ]
    require(len(delegated_calls) == 1, "HTTP middleware delegation is not exact")
    delegated_call = delegated_calls[0].value
    call_next_loads = [
        candidate
        for candidate in middleware_scope
        if isinstance(candidate, ast.Name)
        and candidate.id == "call_next"
        and isinstance(candidate.ctx, ast.Load)
    ]
    require(
        isinstance(delegated_call, ast.Call)
        and call_next_loads == [delegated_call.func],
        "HTTP middleware delegation callable is reused or aliased",
    )
    response_assignments = [
        candidate
        for candidate in middleware_scope
        if isinstance(candidate, ast.Assign)
        and len(candidate.targets) == 1
        and isinstance(candidate.targets[0], ast.Name)
        and candidate.targets[0].id == "response"
        and candidate.value is delegated_calls[0]
    ]
    require(
        len(response_assignments) == 1,
        "HTTP middleware does not preserve the delegated response",
    )
    response_name_bindings = [
        candidate
        for candidate in middleware_scope
        if isinstance(candidate, ast.Name)
        and candidate.id == "response"
        and isinstance(candidate.ctx, (ast.Store, ast.Del))
    ]
    require(
        response_name_bindings == [response_assignments[0].targets[0]],
        "HTTP middleware response binding is reassigned",
    )

    def expression_root_name(node: ast.expr) -> str | None:
        current = node
        while isinstance(current, (ast.Attribute, ast.Subscript)):
            current = current.value
        return current.id if isinstance(current, ast.Name) else None

    allowed_response_header_names: list[str] = []
    for candidate in middleware_scope:
        targets: list[ast.expr] = []
        if isinstance(candidate, ast.Assign):
            targets.extend(candidate.targets)
        elif isinstance(candidate, (ast.AnnAssign, ast.AugAssign)):
            targets.append(candidate.target)
        elif isinstance(candidate, ast.Delete):
            targets.extend(candidate.targets)
        for target in targets:
            if expression_root_name(target) != "response":
                continue
            if target is response_assignments[0].targets[0]:
                continue
            require(
                isinstance(target, ast.Subscript)
                and attribute_path(target.value) == ["response", "headers"]
                and isinstance(target.slice, ast.Constant)
                and target.slice.value in {"X-Correlation-ID", "traceparent"},
                "HTTP middleware mutates the delegated response",
            )
            if (
                not isinstance(target, ast.Subscript)
                or not isinstance(target.slice, ast.Constant)
                or not isinstance(target.slice.value, str)
            ):
                raise ContractError("HTTP middleware mutates the delegated response")
            allowed_response_header_names.append(target.slice.value)
    require(
        set(allowed_response_header_names) == {"X-Correlation-ID", "traceparent"},
        "HTTP middleware response-header mutations drifted",
    )
    for candidate in middleware_scope:
        if isinstance(candidate, ast.Call):
            call_path = attribute_path(candidate.func)
            if call_path is not None and call_path[:1] == ["response"]:
                raise ContractError("HTTP middleware mutates the delegated response")
            if call_path is not None and call_path[:1] == ["request"]:
                require(
                    call_path == ["request", "headers", "get"],
                    "HTTP middleware mutates or ambiguously consumes the request",
                )
        if isinstance(
            candidate, (ast.Assign, ast.AnnAssign, ast.AugAssign, ast.Delete)
        ):
            targets = (
                candidate.targets
                if isinstance(candidate, (ast.Assign, ast.Delete))
                else [candidate.target]
            )
            for target in targets:
                if expression_root_name(target) != "request":
                    continue
                target_path = attribute_path(target)
                require(
                    target_path is not None and target_path[:2] == ["request", "state"],
                    "HTTP middleware mutates request routing state",
                )
    middleware_returns = [
        candidate for candidate in middleware_scope if isinstance(candidate, ast.Return)
    ]
    require(
        bool(middleware_returns)
        and all(
            isinstance(candidate.value, ast.Name) and candidate.value.id == "response"
            for candidate in middleware_returns
        ),
        "HTTP middleware may return without routing the request",
    )

    def authentication_binding(node: ast.AsyncFunctionDef) -> tuple[str, str]:
        positional_arguments = [*node.args.posonlyargs, *node.args.args]
        request_arguments = [
            (index, argument)
            for index, argument in enumerate(positional_arguments)
            if argument.arg == "request"
        ]
        require(
            len(request_arguments) == 1,
            "governed GET route request binding is missing or ambiguous",
        )
        request_index, request_argument = request_arguments[0]
        require(
            isinstance(request_argument.annotation, ast.Name)
            and request_argument.annotation.id == "Request",
            "governed GET route request parameter is not FastAPI Request",
        )
        default_start = len(positional_arguments) - len(node.args.defaults)
        require(
            request_index < default_start,
            "governed GET route request parameter has a dependency default",
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
                raise ContractError(f"governed GET route must be asynchronous: {path}")
            routes[path] = authentication_binding(node)

    all_registered_paths = registered_paths(
        tree,
        module_name="appolon_factory",
        receiver_prefixes={"app": ""},
        static_names=module_string_constants(tree),
        allow_webhook_dynamic=True,
        allow_http_middleware=True,
    )
    module_trees: dict[str, ast.Module] = {}
    local_prefix_cache: dict[str, dict[str, str]] = {}
    imported_binding_cache: dict[str, dict[str, tuple[str, str]]] = {}

    def load_router_module(module_name: str) -> ast.Module:
        require(
            bool(re.fullmatch(r"[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)*", module_name)),
            "included router module name is invalid",
        )
        if module_name in module_trees:
            return module_trees[module_name]
        module_path = ROOT / "app" / (module_name.replace(".", "/") + ".py")
        try:
            module_tree = ast.parse(
                module_path.read_text(encoding="utf-8"),
                filename=module_path.relative_to(ROOT).as_posix(),
            )
        except (OSError, SyntaxError) as error:
            raise ContractError(
                f"included router source is unavailable or invalid: {module_name}"
            ) from error
        module_trees[module_name] = module_tree
        return module_tree

    def local_router_prefixes(module_name: str) -> dict[str, str]:
        if module_name in local_prefix_cache:
            return local_prefix_cache[module_name]
        prefixes: dict[str, str] = {}
        for statement in load_router_module(module_name).body:
            if not isinstance(statement, (ast.Assign, ast.AnnAssign)):
                continue
            targets = (
                statement.targets
                if isinstance(statement, ast.Assign)
                else [statement.target]
            )
            value = statement.value
            if not (
                isinstance(value, ast.Call)
                and isinstance(value.func, ast.Name)
                and value.func.id == "APIRouter"
            ):
                continue
            require(
                len(targets) == 1 and isinstance(targets[0], ast.Name),
                f"router definition is ambiguous: {module_name}",
            )
            if len(targets) != 1 or not isinstance(targets[0], ast.Name):
                raise ContractError(f"router definition is ambiguous: {module_name}")
            name = targets[0].id
            prefix_values = [
                static_string(keyword.value)
                for keyword in value.keywords
                if keyword.arg == "prefix"
            ]
            require(
                len(prefix_values) <= 1
                and all(item is not None for item in prefix_values),
                f"router prefix is dynamic or ambiguous: {module_name}.{name}",
            )
            prefix = prefix_values[0] if prefix_values else ""
            if prefix is None:
                raise ContractError(
                    f"router prefix is dynamic or ambiguous: {module_name}.{name}"
                )
            require(
                name not in prefixes,
                f"duplicate router definition: {module_name}.{name}",
            )
            prefixes[name] = prefix
        local_prefix_cache[module_name] = prefixes
        return prefixes

    def imported_router_bindings(module_name: str) -> dict[str, tuple[str, str]]:
        if module_name in imported_binding_cache:
            return imported_binding_cache[module_name]
        bindings: dict[str, tuple[str, str]] = {}
        for statement in load_router_module(module_name).body:
            if (
                not isinstance(statement, ast.ImportFrom)
                or statement.level != 1
                or statement.module is None
            ):
                continue
            for imported in statement.names:
                bound = imported.asname or imported.name
                if not (
                    imported.name == "router"
                    or imported.name.endswith("_router")
                    or bound == "router"
                    or bound.endswith("_router")
                ):
                    continue
                require(
                    bound not in bindings,
                    f"duplicate imported router binding: {module_name}.{bound}",
                )
                bindings[bound] = (statement.module, imported.name)
        imported_binding_cache[module_name] = bindings
        return bindings

    def router_prefix(
        module_name: str,
        binding_name: str,
        resolving: set[tuple[str, str]] | None = None,
    ) -> str:
        marker = (module_name, binding_name)
        active = set() if resolving is None else set(resolving)
        require(marker not in active, "included router import cycle is ambiguous")
        active.add(marker)
        local = local_router_prefixes(module_name)
        imported = imported_router_bindings(module_name)
        require(
            not (binding_name in local and binding_name in imported),
            f"router binding is ambiguous: {module_name}.{binding_name}",
        )
        if binding_name in local:
            return local[binding_name]
        require(
            binding_name in imported,
            f"router binding is unresolved: {module_name}.{binding_name}",
        )
        source_module, source_binding = imported[binding_name]
        return router_prefix(source_module, source_binding, active)

    for helper_name, module_name in EXPECTED_ROUTE_HELPERS.items():
        helper_tree = load_router_module(module_name)
        all_registered_paths.extend(
            registered_paths(
                helper_tree,
                module_name=module_name,
                receiver_prefixes={"app": ""},
                static_names=module_string_constants(helper_tree),
            )
        )

    pending_modules = list(
        dict.fromkeys(
            [
                *EXPECTED_INCLUDED_ROUTERS.values(),
                *sorted(EXPECTED_SIDE_EFFECT_ROUTER_MODULES),
            ]
        )
    )
    scanned_modules: set[str] = set()
    while pending_modules:
        module_name = pending_modules.pop(0)
        if module_name in scanned_modules:
            continue
        module_tree = load_router_module(module_name)
        local = local_router_prefixes(module_name)
        imported_bindings = imported_router_bindings(module_name)
        receiver_names = set(local) | set(imported_bindings)
        require(receiver_names, f"included router module has no router: {module_name}")
        receiver_prefixes = {
            name: router_prefix(module_name, name) for name in receiver_names
        }
        for candidate in ast.walk(module_tree):
            if not isinstance(candidate, (ast.Assign, ast.AnnAssign, ast.NamedExpr)):
                continue
            if (
                isinstance(candidate.value, ast.Name)
                and candidate.value.id in receiver_names
            ):
                raise ContractError(
                    f"router alias makes registration ambiguous: {module_name}"
                )
        all_registered_paths.extend(
            registered_paths(
                module_tree,
                module_name=module_name,
                receiver_prefixes=receiver_prefixes,
                static_names=module_string_constants(module_tree),
                allow_provider_dynamic=module_name == "provider_control_api",
            )
        )
        for candidate in ast.walk(module_tree):
            if (
                not isinstance(candidate, ast.Call)
                or not isinstance(candidate.func, ast.Attribute)
                or candidate.func.attr != "include_router"
            ):
                continue
            receiver = attribute_path(candidate.func.value)
            require(
                receiver is not None
                and len(receiver) == 1
                and receiver[0] in receiver_names,
                f"included-router receiver is unresolved: {module_name}",
            )
            require(
                len(candidate.args) == 1
                and not candidate.keywords
                and isinstance(candidate.args[0], ast.Name)
                and candidate.args[0].id in receiver_names,
                f"included-router binding is dynamic or ambiguous: {module_name}",
            )
            if (
                len(candidate.args) != 1
                or candidate.keywords
                or not isinstance(candidate.args[0], ast.Name)
                or candidate.args[0].id not in receiver_names
            ):
                raise ContractError(
                    f"included-router binding is dynamic or ambiguous: {module_name}"
                )
            included_name = candidate.args[0].id
            if included_name in imported_bindings:
                pending_modules.append(imported_bindings[included_name][0])
        scanned_modules.add(module_name)
    for path in GOVERNED_READ_PATHS:
        require(
            all_registered_paths.count(path) == 1,
            f"governed GET route registration is missing or ambiguous: {path}",
        )
    return routes


def main() -> None:
    contract = json.loads(
        (ROOT / "contracts/staging-intake-observability-runtime.v1.json").read_text()
    )
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
    matches = [
        item
        for item in profiles["profiles"]
        if item["profile_id"] == EXPECTED_PROFILE["profile_id"]
    ]
    require(matches == [EXPECTED_PROFILE], "staging runtime profile drift")
    embedded = release["embedded_runtime_profile"]
    require(
        embedded
        == {
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
        },
        "embedded runtime profile drift",
    )

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
        runtime["dependencies"] == ["postgresql-tls", "redis-tls", "keycloak-jwks"],
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
        (
            "GET",
            "/metrics",
            "monitoring-readonly",
            "metrics.read",
            "middleware-api",
            False,
        ),
        (
            "GET",
            "/v1/runtime/safety",
            "monitoring-readonly",
            "health.read",
            "middleware-api",
            False,
        ),
    }
    actual = {
        (
            e["method"],
            e["path"],
            e["client_id"],
            e["scope"],
            e["audience"],
            e["public_exposure"],
        )
        for e in endpoints
    }
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
    require(
        contract["dispatch_controls"]
        == {
            "OUTBOX_DISPATCH_ENABLED": False,
            "NATS_DISPATCH_MODE": "disabled",
            "TEMPORAL_WORKER_MODE": "disabled",
            "PRODUCTION_DIALING": "DISABLED",
        },
        "dispatch control drift",
    )
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

    env = parse_env(
        ROOT / "config/environments/staging.intake-observability.runtime.env.example"
    )
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
    raw_webhooks = webhook_contract.get("webhooks", [])
    require(isinstance(raw_webhooks, list), "dynamic webhook policy is malformed")
    webhook_paths: list[str] = []
    for item in raw_webhooks:
        require(isinstance(item, dict), "dynamic webhook policy is malformed")
        path = item.get("path")
        require(
            isinstance(path, str) and path.startswith("/"),
            "dynamic webhook path is invalid",
        )
        webhook_paths.append(path)
    require(
        webhook_paths
        and len(webhook_paths) == len(set(webhook_paths))
        and GOVERNED_READ_PATHS.isdisjoint(webhook_paths),
        "dynamic webhook paths are duplicated or shadow a governed GET route",
    )
    provider_policy = json.loads(
        (ROOT / "config/provider-operation-policy.json").read_text(encoding="utf-8")
    )
    require(
        provider_policy.get("schemaVersion") == 1,
        "provider operation policy version drift",
    )
    raw_provider_operations = provider_policy.get("operations", [])
    require(
        isinstance(raw_provider_operations, list),
        "provider operation policy is malformed",
    )
    provider_paths: list[str] = []
    for operation in raw_provider_operations:
        require(
            isinstance(operation, dict),
            "provider operation policy is malformed",
        )
        if operation.get("externalEffect") is not True:
            continue
        path = operation.get("route")
        require(
            isinstance(path, str) and path.startswith("/"),
            "provider operation route is invalid",
        )
        provider_paths.append(path)
    require(
        provider_paths
        and len(provider_paths) == len(set(provider_paths))
        and GOVERNED_READ_PATHS.isdisjoint(provider_paths),
        "provider operation routes are duplicated or shadow a governed GET route",
    )
    route_bindings = authenticated_get_routes(
        factory_source,
        webhook_paths=webhook_paths,
        provider_paths=provider_paths,
    )
    require(
        route_bindings.get("/metrics") == ("monitoring-readonly", "metrics.read"),
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
    workflow_source = (
        ROOT / ".github/workflows/staging-intake-observability-contract.yml"
    ).read_text(encoding="utf-8")
    for trigger in ("pull_request", "push"):
        paths = workflow_trigger_paths(workflow_source, trigger)
        require(
            WORKFLOW_REQUIRED_PATHS <= paths,
            f"workflow {trigger} paths omit a bound contract source",
        )
    print("MIDDLEWARE_STAGING_INTAKE_OBSERVABILITY_CONTRACT=PASS")


if __name__ == "__main__":
    main()
