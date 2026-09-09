#!/usr/bin/env python3
"""Generate and verify the API contract artifacts from the FastAPI runtime."""

from __future__ import annotations

import argparse
import json
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

HTTP_METHODS = frozenset({"get", "post", "put", "patch", "delete"})
MUTATION_METHODS = frozenset({"post", "put", "patch", "delete"})
PUBLIC_PATHS = frozenset(
    {"/health", "/ready", "/readiness", "/dependencies", "/version", "/capabilities"}
)
INVENTORY_BASE_SHA = "55073dc8061085f51bf54180b5dc2ed2f0f4e446"

DESCRIPTION = (
    "Exact generated Middleware runtime contract. Bearer tokens use issuer "
    "https://auth.codestra.co/realms/codestra and audience middleware-api. "
    "Tenant-scoped reads enforce each configured caller status_scope; mutations "
    "enforce command_scope. External effects remain disabled."
)
BEARER_SECURITY_SCHEME = {
    "type": "http",
    "scheme": "bearer",
    "bearerFormat": "JWT",
    "description": (
        "Keycloak machine token; issuer auth.codestra.co realm codestra; "
        "audience middleware-api"
    ),
}
REQUIRED_HEADERS: dict[str, dict[str, Any]] = {
    "X-Tenant-ID": {
        "name": "X-Tenant-ID",
        "in": "header",
        "required": True,
        "schema": {"type": "string", "minLength": 1, "maxLength": 128},
    },
    "X-Correlation-ID": {
        "name": "X-Correlation-ID",
        "in": "header",
        "required": True,
        "schema": {"type": "string", "minLength": 1, "maxLength": 180},
    },
    "Idempotency-Key": {
        "name": "Idempotency-Key",
        "in": "header",
        "required": True,
        "schema": {"type": "string", "minLength": 8, "maxLength": 180},
    },
}
STANDARD_RESPONSES = (
    ("400", "Invalid canonical request"),
    ("401", "Authentication failed"),
    ("403", "Scope or tenant denied"),
    ("404", "Resource not found"),
    ("409", "Version, state, or idempotency conflict"),
    ("429", "Rate limited"),
    ("503", "Required durable dependency unavailable"),
)
OUTPUT_PATHS = {
    "json": ROOT / "contracts/platform/middleware-openapi.generated.json",
    "yaml": ROOT / "contracts/platform/integration-fabric-api.v2.yaml",
    "matrix": ROOT / "config/api-completion-matrix.yaml",
}


def _governed_api_path(path: str) -> bool:
    return (
        path.startswith(("/v1/", "/api/v1/"))
        and path != "/v1/runtime/safety"
        and "webhook" not in path
    )


def _ensure_header(parameters: list[dict[str, Any]], name: str) -> None:
    matches = [
        parameter
        for parameter in parameters
        if parameter.get("in") == "header"
        and str(parameter.get("name", "")).casefold() == name.casefold()
    ]
    if len(matches) > 1:
        raise ValueError(f"operation declares {name} more than once")
    if matches:
        expected = REQUIRED_HEADERS[name]
        actual = matches[0]
        expected_schema = expected["schema"]
        actual_schema = actual.get("schema")
        if (
            actual.get("required") is not True
            or not isinstance(actual_schema, dict)
            or any(
                actual_schema.get(key) != value
                for key, value in expected_schema.items()
            )
        ):
            raise ValueError(f"operation declares a non-canonical {name} contract")
    else:
        # Header contracts are immutable module constants. Reusing each object
        # also keeps the YAML artifact compact through safe-dumper anchors.
        parameters.append(REQUIRED_HEADERS[name])


def _domain_for_path(path: str) -> str:
    return next(
        (
            part
            for part in path.split("/")
            if part and part not in {"v1", "api", "internal"}
        ),
        "platform",
    )


def build_documents() -> tuple[dict[str, Any], dict[str, Any]]:
    """Build the enriched OpenAPI document and completion matrix in memory."""
    # These imports follow the explicit repository-root path setup above so this
    # file remains directly executable from any working directory.
    from app.config import Settings
    from app.main import create_app

    settings = Settings.from_env(
        {
            "APP_ENV": "test",
            "ALLOW_IN_MEMORY_STORAGE": "true",
            "EXTERNAL_EFFECTS": "false",
        }
    )
    schema: dict[str, Any] = create_app(settings=settings).openapi()
    schema["info"]["description"] = DESCRIPTION
    components = schema.setdefault("components", {})
    security_schemes = components.setdefault("securitySchemes", {})
    security_schemes["bearerAuth"] = deepcopy(BEARER_SECURITY_SCHEME)

    operations: list[dict[str, Any]] = []
    for path, item in schema["paths"].items():
        for method, operation in item.items():
            if method not in HTTP_METHODS:
                continue
            if path not in PUBLIC_PATHS:
                operation["security"] = [{"bearerAuth": []}]
            if _governed_api_path(path):
                parameters = operation.setdefault("parameters", [])
                _ensure_header(parameters, "X-Tenant-ID")
                if method in MUTATION_METHODS:
                    _ensure_header(parameters, "X-Correlation-ID")
                    _ensure_header(parameters, "Idempotency-Key")

            responses = operation.setdefault("responses", {})
            # Preserve business-specific 422 responses emitted by the runtime.
            # The application-wide validation handler normalizes generic request
            # validation failures to the canonical 400 envelope.
            for code, description in STANDARD_RESPONSES:
                responses.setdefault(code, {"description": description})

            operations.append(
                {
                    "domain": _domain_for_path(path),
                    "method": method.upper(),
                    "path": path,
                    "canonical_operation_id": operation.get("operationId"),
                    "implementation_file": "registered FastAPI runtime",
                    "runtime_state": (
                        "DEPRECATED" if operation.get("deprecated") else "IMPLEMENTED"
                    ),
                }
            )

    operations.sort(key=lambda row: (row["path"], row["method"]))
    matrix = {
        "schema_version": "2.0",
        "inventory_base_sha": INVENTORY_BASE_SHA,
        "classification_complete": True,
        "unknown_endpoints": 0,
        "operations": operations,
    }
    return schema, matrix


def render_documents(
    schema: dict[str, Any],
    matrix: dict[str, Any],
) -> dict[Path, str]:
    return {
        OUTPUT_PATHS["json"]: json.dumps(schema, indent=2, sort_keys=True) + "\n",
        OUTPUT_PATHS["yaml"]: yaml.safe_dump(
            schema,
            sort_keys=False,
            allow_unicode=True,
        ),
        OUTPUT_PATHS["matrix"]: yaml.safe_dump(matrix, sort_keys=False),
    }


def _check_documents(documents: dict[Path, str]) -> list[Path]:
    stale: list[Path] = []
    for path, expected in documents.items():
        try:
            actual = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            stale.append(path)
            continue
        if actual != expected:
            stale.append(path)
    return stale


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail if committed contract artifacts differ from generated output",
    )
    args = parser.parse_args(argv)
    schema, matrix = build_documents()
    documents = render_documents(schema, matrix)

    if args.check:
        stale = _check_documents(documents)
        if stale:
            for path in stale:
                print(f"STALE_API_CONTRACT={path.relative_to(ROOT)}", file=sys.stderr)
            return 1
    else:
        for path, content in documents.items():
            path.write_text(content, encoding="utf-8")

    print(f"OPENAPI_ROUTES={len(matrix['operations'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
