"""Fail-closed public-route and configured-upstream release audit.

The source mode is safe for CI. Runtime mode resolves and connects to every
configured URL-valued setting while printing only setting name, host and port.
Credentials and URL paths are never emitted.
"""

from __future__ import annotations

import argparse
import json
import socket
from pathlib import Path
from urllib.parse import urlsplit

from app.core.config import settings
from app.entrypoints.integration_api import app

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "deploy/public-api-route-contract.json"
URL_SCHEMES = {
    "http": 80,
    "https": 443,
    "postgres": 5432,
    "postgresql": 5432,
    "postgresql+asyncpg": 5432,
    "redis": 6379,
    "rediss": 6379,
}


def source_audit() -> list[str]:
    contract = json.loads(CONTRACT.read_text())
    assert contract["schema"] == "codestra.middleware.public-api-route-contract.v1"
    assert contract["service"] == "middleware-integration-api"
    assert contract["listener_port"] == 8095
    actual = {
        (method.upper(), path)
        for route in app.routes
        if (path := getattr(route, "path", None)) is not None
        for method in (getattr(route, "methods", None) or set())
    }
    expected = {(row["method"], row["path"]) for row in contract["routes"]}
    missing = sorted(expected - actual)
    if missing:
        raise SystemExit(f"public API route contract missing routes: {missing}")
    return [f"ROUTE={method}|{path}|PASS" for method, path in sorted(expected)]


def configured_upstreams() -> list[tuple[str, str, int]]:
    rows: set[tuple[str, str, int]] = set()
    for name, value in settings.model_dump().items():
        if not isinstance(value, str) or not value or "://" not in value:
            continue
        if "url" not in name:
            continue
        parsed = urlsplit(value)
        if not parsed.hostname or parsed.scheme not in URL_SCHEMES:
            raise SystemExit(f"unsupported configured upstream setting: {name}")
        port = parsed.port or URL_SCHEMES[parsed.scheme]
        rows.add((name, parsed.hostname, port))
    return sorted(rows)


def runtime_audit(timeout: float) -> list[str]:
    output: list[str] = []
    failures: list[str] = []
    for name, host, port in configured_upstreams():
        try:
            socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
            with socket.create_connection((host, port), timeout=timeout):
                pass
            output.append(f"UPSTREAM={name}|{host}|{port}|DNS=PASS|TCP=PASS")
        except OSError as exc:
            output.append(
                f"UPSTREAM={name}|{host}|{port}|DNS_OR_TCP=FAIL|"
                f"ERROR={type(exc).__name__}"
            )
            failures.append(name)
    if failures:
        print("\n".join(output))
        raise SystemExit("configured upstream audit failed: " + ",".join(failures))
    return output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime", action="store_true")
    parser.add_argument("--timeout", type=float, default=3.0)
    args = parser.parse_args()
    rows = source_audit()
    if args.runtime:
        rows.extend(runtime_audit(args.timeout))
    print("\n".join(rows))


if __name__ == "__main__":
    main()
