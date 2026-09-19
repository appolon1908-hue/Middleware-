#!/usr/bin/env python3
"""Classify every port binding the six core repositories declare (mission phase 23).

Scans Middleware, Kong, Caddy, Keycloak, Odoo and N8N (local checkouts) for the
listener and upstream ports that matter to the core contract — 8095 (Middleware
canonical), 8080 (retired Middleware alias / Keycloak HTTP / miscellaneous),
8000 (Kong proxy), 8069 (Odoo), 5678 (N8N) — and classifies each occurrence from
its own context. Nothing is rewritten; unrelated services that happen to use
8080 (Keycloak's own listener, standby fixtures, the websocket gateway) are
named as such instead of being "fixed".

Usage: python scripts/cross_repo_port_contract.py [--root <GitHub dir>] [--write]
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from cross_repo_contract_matrix import REPOSITORIES, default_root, resolve

MIDDLEWARE_ROOT = Path(__file__).resolve().parents[1]
PORT_PATTERN = re.compile(r"(?<![0-9])(8095|8080|8000|8069|5678)(?![0-9])")
CANONICAL = {
    "8095": "MIDDLEWARE_CANONICAL_INTEGRATION_API",
    "8000": "KONG_PROXY_LISTENER",
    "8069": "ODOO_HTTP",
    "5678": "N8N_HTTP",
}
# (repository, regex over "path:line") → classification, first match wins; only for 8080.
RULES_8080: tuple[tuple[str, str, str], ...] = (
    (
        "*",
        r"keycloak[a-z0-9.-]*:8080|codestra-identity-keycloak-1:8080|127\.0\.0\.1:8080\}:8080|KEYCLOAK_HTTP_PORT|auth\.codestra\.co\.caddy|realms/",
        "KEYCLOAK_HTTP_LISTENER_OR_TOKEN_ENDPOINT",
    ),
    ("Keycloak", r".*", "KEYCLOAK_HTTP_LISTENER_OR_TOKEN_ENDPOINT"),
    ("Kong", r"appolon-middleware-integration-api", "MIDDLEWARE_RETIRED_ALIAS_DENIED"),
    ("Kong", r"codestra-kong-standby-auth|standby", "KONG_STANDBY_AUTH_FIXTURE"),
    ("Kong", r"kong-test-upstream|gateway-test", "KONG_TEST_UPSTREAM_RETIRE_CANDIDATE"),
    (
        "Kong",
        r"identity-certification|token-validat",
        "KONG_TRANSITIONAL_CERTIFICATION_PROBE",
    ),
    (
        "Kong",
        r"service-auth-adapter|email-reseller|sms-api-api|crm-route|sms-route|email-route|sms-dlr",
        "LEGACY_PROVIDER_ADAPTER_DEPRECATE",
    ),
    (
        "Kong",
        r"TRANSITIONAL_8080|8080 alias|middlewareListenerSplit|RETIRED|retired|8080\D*(alias|retire)",
        "MIDDLEWARE_RETIRED_ALIAS_DENIED",
    ),
    (
        "Kong",
        r"tests/|scripts/validate_kong_foundation|scripts/validate_provider_control_routes|scripts/apply_kong_standby",
        "KONG_VALIDATOR_OR_TEST_REFERENCE",
    ),
    (
        "Kong",
        r"community-n8n-egress|n8n",
        "COMMUNITY_N8N_EGRESS_PLAIN_HTTP_PROPOSED_TLS",
    ),
    (
        "Middleware-",
        r"observability-alerts/",
        "MIDDLEWARE_OBSERVABILITY_ALERT_API_LISTENER",
    ),
    (
        "Middleware-",
        r"deploy/production/compose\.canary\.yaml|deploy/production/server/codestra-middleware-deploy",
        "MIDDLEWARE_LEGACY_MONOLITH_CANARY_LISTENER",
    ),
    (
        "Middleware-",
        r"production-route-contract\.yml",
        "CI_ROUTE_CERTIFICATION_CONTAINER_LISTENER",
    ),
    ("Middleware-", r"agent_desktop/Caddyfile", "AGENT_DESKTOP_STATIC_SITE_LISTENER"),
    (
        "Middleware-",
        r"deploy/beyvra-email/",
        "BEYVRA_EMAIL_RUNTIME_LISTENER_SEPARATE_SERVICE",
    ),
    ("Middleware-", r"cadvisor", "CADVISOR_EXPORTER_LISTENER"),
    (
        "Middleware-",
        r"integrated-monitoring-inventory\.json",
        "MONITORING_INVENTORY_DEFAULT_INTERNAL_PORT",
    ),
    ("Middleware-", r"websocket", "WEBSOCKET_GATEWAY_INTERNAL_LISTENER"),
    (
        "Middleware-",
        r"RETIRED_PROXY_DEPENDENCY_MATRIX|discover_auth_codestra_edge|config/caddy/",
        "RETIRED_PROXY_OR_KEYCLOAK_EDGE_REFERENCE",
    ),
    (
        "Odoo",
        r"parsed\.port == 8080|token\.port == 8080",
        "KEYCLOAK_TOKEN_ENDPOINT_GUARD",
    ),
    ("Odoo", r"/tests/", "TEST_FIXTURE"),
    ("*", r"/tests?/|test_", "TEST_FIXTURE"),
)
EXCLUDED_DIRS = (
    "docs/",
    ".git/",
    "node_modules/",
    "__pycache__",
    ".worktrees/",
    "evidence/",
    # the scanner, its tests and its generated reports describe ports; they are not bindings
    "scripts/cross_repo_",
    "tests/cross_repo/",
)
TEXT_SUFFIXES = {
    ".py",
    ".json",
    ".yml",
    ".yaml",
    ".toml",
    ".sh",
    ".caddy",
    ".snippet",
    ".env",
    ".example",
    ".csv",
    ".mjs",
    ".js",
    ".lua",
    ".txt",
    ".cfg",
    ".ini",
    "",
    ".Dockerfile",
}


def tracked_files(repo: Path) -> list[str]:
    out = subprocess.run(
        ["git", "-C", str(repo), "ls-files"],
        capture_output=True,
        text=True,
        check=False,
    )
    return out.stdout.split("\n") if out.returncode == 0 else []


def json_port_bindings(document: Any) -> list[dict[str, str]]:
    """Every object in a JSON document that binds a ``port`` (int or string), described by
    its own host/name and the names of the objects that enclose it."""
    found: list[dict[str, str]] = []

    def describe(node: dict[str, Any]) -> str:
        keys = (
            "host",
            "name",
            "serviceId",
            "routeId",
            "route",
            "service",
            "role",
            "lifecycle",
            "disposition",
            "purpose",
            "note",
        )
        return " ".join(
            f"{k}={node[k]}" for k in keys if isinstance(node.get(k), (str, int))
        )

    def walk(node: Any, trail: list[str]) -> None:
        if isinstance(node, dict):
            port = node.get("port")
            if isinstance(port, (int, str)) and str(port).isdigit():
                found.append(
                    {
                        "port": str(port),
                        "description": " / ".join([*trail, describe(node)]).strip(" /"),
                    }
                )
            for value in node.values():
                walk(value, [*trail, describe(node)] if describe(node) else trail)
        elif isinstance(node, list):
            for item in node:
                walk(item, trail)

    walk(document, [])
    return found


def classify_8080(repo_name: str, context: str) -> str:
    for scope, pattern, label in RULES_8080:
        if scope in ("*", repo_name) and re.search(pattern, context):
            return label
    return "UNCLASSIFIED"


def scan(root: Path) -> dict[str, Any]:
    rows: list[dict[str, str]] = []
    heads: dict[str, str] = {}
    for name in REPOSITORIES:
        repo = resolve(root, name)
        if repo is None:
            raise SystemExit(f"PORT_CONTRACT=FAIL missing local repository {name}")
        head = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )
        heads[name] = head.stdout.strip()
        for relative in tracked_files(repo):
            if (
                not relative
                or any(part in relative for part in EXCLUDED_DIRS)
                or relative.endswith(".md")
            ):
                continue
            path = repo / relative
            if path.suffix not in TEXT_SUFFIXES or not path.is_file():
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if path.suffix == ".json":
                try:
                    document = json.loads(text)
                except ValueError:
                    document = None
                if document is not None:
                    for context in json_port_bindings(document):
                        port = context["port"]
                        if port not in CANONICAL and port != "8080":
                            continue
                        described = f"{relative}:{context['description']}"
                        label = (
                            classify_8080(name, described)
                            if port == "8080"
                            else CANONICAL[port]
                        )
                        rows.append(
                            {
                                "repository": name,
                                "file": relative,
                                "line": "json",
                                "port": port,
                                "classification": label,
                                "context": context["description"][:140],
                            }
                        )
                    continue
            for number, line in enumerate(text.splitlines(), 1):
                for port in PORT_PATTERN.findall(line):
                    if port == "8080" and not re.search(
                        r"(:|port\W{0,4}|-)8080\b|8080\b.*(port|listen|expose)",
                        line,
                        re.I,
                    ):
                        continue
                    context = f"{relative}:{line.strip()}"
                    if port == "8080":
                        label = classify_8080(name, context)
                    else:
                        label = CANONICAL[port]
                        if (
                            port == "8095"
                            and "middleware" not in context.lower()
                            and "8095" in context
                        ):
                            label = "MIDDLEWARE_CANONICAL_INTEGRATION_API"
                    rows.append(
                        {
                            "repository": name,
                            "file": relative,
                            "line": str(number),
                            "port": port,
                            "classification": label,
                            "context": line.strip()[:140],
                        }
                    )
    summary: dict[str, Any] = {
        # A list of objects, not {"<name>": "<sha>"} pairs, so no secret scanner reads a
        # repository name followed by a hex digest as a credential.
        "REPOSITORIES": [
            {"repository": name, "head": head} for name, head in sorted(heads.items())
        ],
        "TOTAL": len(rows),
        "BY_CLASSIFICATION": {},
        "UNCLASSIFIED": [
            f"{r['repository']}:{r['file']}:{r['line']}"
            for r in rows
            if r["classification"] == "UNCLASSIFIED"
        ],
        "MIDDLEWARE_8080_AS_CANONICAL": [
            f"{r['repository']}:{r['file']}:{r['line']}"
            for r in rows
            if r["port"] == "8080"
            and r["classification"] == "MIDDLEWARE_RETIRED_ALIAS_DENIED"
            and "canonical" in r["context"].lower()
            and "retired" not in r["context"].lower()
        ],
        "CANONICAL_8080": 0,
    }
    for row in rows:
        summary["BY_CLASSIFICATION"][row["classification"]] = (
            summary["BY_CLASSIFICATION"].get(row["classification"], 0) + 1
        )
    summary["CANONICAL_8080"] = len(summary["MIDDLEWARE_8080_AS_CANONICAL"])
    return {
        "schema": "codestra.core-port-contract.v1",
        "summary": summary,
        "rows": rows,
    }


def render(report: dict[str, Any]) -> str:
    s = report["summary"]
    lines = [
        "# Codestra core port contract (generated from local source)",
        "",
        "Generated by `scripts/cross_repo_port_contract.py --write`; every row is a tracked source line. Do not hand-edit.",
        "",
    ]
    lines.append("## Canonical listeners")
    lines += [
        "- Middleware canonical integration API: `middleware-integration-api:8095` (Kong upstream, Dockerfile EXPOSE, compose.runtime)",
        "- Kong proxy: `127.0.0.1:8000` (Caddy `CADDY_KONG_UPSTREAM` reference listener)",
        "- Odoo: `odoo:8069` (Middleware private_only upstream)",
        "- N8N: `5678` (N8N compose listener; reached by Middleware only through the attested reservation transport)",
        "- Keycloak: `8080` is Keycloak's own HTTP listener behind its Caddy site and the token/JWKS endpoints other services call; it is not a Middleware port",
        "",
    ]
    lines.append("## Summary")
    lines.append(f"- `TOTAL_PORT_REFERENCES` = {s['TOTAL']}")
    lines.append(f"- `CANONICAL_8080` = {s['CANONICAL_8080']}")
    lines.append(f"- `UNCLASSIFIED` = {len(s['UNCLASSIFIED'])}")
    for label, count in sorted(s["BY_CLASSIFICATION"].items()):
        lines.append(f"- `{label}` = {count}")
    lines += [
        "",
        "## Rows",
        "| REPOSITORY | FILE | LINE | PORT | CLASSIFICATION | CONTEXT |",
        "|---|---|---|---|---|---|",
    ]
    for r in report["rows"]:
        lines.append(
            f"| {r['repository']} | `{r['file']}` | {r['line']} | {r['port']} | {r['classification']} | `{r['context'].replace('|', '¦')}` |"
        )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=default_root())
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    report = scan(args.root)
    if args.write:
        out = MIDDLEWARE_ROOT / "docs" / "integration"
        out.mkdir(parents=True, exist_ok=True)
        (out / "core-port-contract.json").write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        (out / "core-port-contract.md").write_text(
            render(report), encoding="utf-8", newline="\n"
        )
    s = report["summary"]
    print(
        f"PORT_CONTRACT=OK total={s['TOTAL']} canonical_8080={s['CANONICAL_8080']} unclassified={len(s['UNCLASSIFIED'])} "
        + " ".join(f"{k}={v}" for k, v in sorted(s["BY_CLASSIFICATION"].items()))
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
