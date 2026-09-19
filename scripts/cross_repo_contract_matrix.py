#!/usr/bin/env python3
"""Build the Codestra core cross-repository contract matrix from local source.

Joins, per Middleware public-API operation, what each repository actually
declares today. Every cell is read from a file named below; nothing is taken
from documentation or inferred from naming alone, and every mismatch reported
is a concrete difference between two files.

* Middleware  — ``deploy/public-api-route-contract.json`` (+ ``.sha256``): the
  write boundary's own edge contract (method, path, classification, calling
  client, audience, scope, auth, idempotency carrier, correlation fields,
  upstream, owner, operation id).
* Kong        — ``config/kong-middleware-authority.v2.json`` (issuer, audience,
  scope, azp, authentication per route), ``config/kong-canonical-middleware-
  routes.json`` (route name, upstream host/port, pinned Middleware contract
  digest) and ``config/kong-access-policy.v1.json`` (access class, audience
  profile, required scopes, tenant policy, identity propagation per route id).
* Keycloak    — ``config/clients/*.json`` (audience mappers, hard-coded scope
  claims, service-account flag, token lifespan) and ``config/client-scopes``.
* Caddy       — ``sites/api.codestra.co.caddy`` (the ``@kong`` matcher and the
  legacy fallback handler) and ``config/caddy-kong-contract.v1.json``.
* Odoo        — Middleware paths referenced by ``custom-addons`` (non-test).
* N8N         — HTTP ``url`` targets referenced by ``automations``/``workflows``.

Usage: python scripts/cross_repo_contract_matrix.py [--root <GitHub dir>] [--write] [--json]
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

MIDDLEWARE_ROOT = Path(__file__).resolve().parents[1]
CANONICAL_UPSTREAM = "middleware-integration-api:8095"
REPOSITORIES = ("Middleware-", "Kong", "Caddy", "Keycloak", "Odoo", "N8N")
INTEGRATION_WORKTREES = {
    "Middleware-": "Middleware-.worktrees/core-crossrepo-20260919",
    "Kong": "Kong.worktrees/middleware-8095-20260919",
    "Caddy": "Caddy.worktrees/crossrepo-20260919",
    "Keycloak": "Keycloak.worktrees/crossrepo-20260919",
    "Odoo": "Odoo.worktrees/crossrepo-20260919",
    "N8N": "N8N.worktrees/crossrepo-20260919",
}
# Middleware V3 kernel routes: prepared in Kong/Keycloak but not activated until
# the final Middleware V3 route contract is frozen.
V3_PENDING_ROUTES = (
    ("POST", "/platform/v1/commands", "platform.command"),
    ("GET", "/platform/v1/kernel/describe", "platform.command.read"),
    ("GET", "/platform/v1/operations/{operation_id}", "platform.command.read"),
    ("POST", "/platform/v1/operations/{operation_id}/cancel", "platform.command"),
    (
        "POST",
        "/platform/v1/operations/{operation_id}/replay",
        "platform.command.replay",
    ),
    ("GET", "/platform/v1/operations/{operation_id}/timeline", "platform.command.read"),
)
# Kong tenant policies that make a tenant (and campaign) claim mandatory.
TENANT_REQUIRED_POLICIES = {
    "HEADER_REQUIRED_CLAIM_AUTHORITY",
    "CLAIM_FIXED_TENANT_CAMPAIGN",
}
TENANT_SELECTOR_POLICIES = {"HEADER_SELECTOR_CLAIM_AUTHORITY"}
# Headers the edge must carry end to end (mission phase 3/15).
REQUIRED_EDGE_HEADERS = (
    "Authorization",
    "X-Correlation-ID",
    "Idempotency-Key",
    "traceparent",
    "tracestate",
)
CLIENT_IDENTITY_HEADER_PREFIXES = (
    "X-Authenticated-",
    "X-Consumer-",
    "X-Credential-",
    "X-Anonymous-",
    "X-Codestra-",
    "X-Tenant-ID",
)
# Middleware paths that close each downstream loop, taken from the contract itself.
RESULT_PATHS = {
    "n8n": "/api/v1/integrations/n8n/results",
    "odoo": "/api/v1/odoo/events",
}
CALLBACK_PATHS = {
    "n8n": "/api/v1/integration/automation-results",
    "odoo": "/api/v1/integration/campaigns/actual-state",
}
# Middleware calling-client values that are policy classes, not Keycloak client ids.
POLICY_CLASSES = {
    "authorized-provisioning-client",
    "platform-operator",
    "production-operator",
    "browser-session",
    "job_family_client_only",
    "approval_job_family_client_only",
    "all_declared_clients",
    "command_prefix_client_only",
    "command_family_client_only",
    "none",
}


def default_root() -> Path:
    parent = MIDDLEWARE_ROOT.parent
    return parent.parent if parent.name.endswith(".worktrees") else parent


def resolve(root: Path, name: str) -> Path | None:
    """Prefer the mission integration worktree, else the primary checkout."""
    for candidate in (root / INTEGRATION_WORKTREES[name], root / name):
        if (candidate / ".git").exists():
            return candidate
    return None


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def git(path: Path, *args: str) -> str:
    out = subprocess.run(
        ["git", "-C", str(path), *args], capture_output=True, text=True, check=False
    )
    return out.stdout.strip() if out.returncode == 0 else "unknown"


def as_list(value: Any) -> list[str]:
    if value in (None, "", "none"):
        return []
    if isinstance(value, list):
        return [str(v) for v in value]
    return [str(value)]


def template_path(path: str) -> str:
    return re.sub(r"\{[^}]+\}", "{}", path)


def path_prefix(path: str) -> str:
    """The literal prefix of a templated path, for matching call sites that append ids."""
    return path.split("{", 1)[0].rstrip("/")


# --- source readers --------------------------------------------------------------------


@dataclass
class KongView:
    authority: dict[tuple[str, str], dict[str, Any]] = field(default_factory=dict)
    contract_routes: dict[tuple[str, str], dict[str, Any]] = field(default_factory=dict)
    policy: dict[str, dict[str, Any]] = field(default_factory=dict)
    pinned_contract: str = ""
    vendored_hash: str = ""
    vendored_rows: int = 0
    legacy_host_enabled: bool | None = None
    provider_effects_enabled: bool | None = None
    denied_routes: int = 0

    @classmethod
    def read(cls, path: Path) -> "KongView":
        view = cls()
        authority = load_json(path / "config" / "kong-middleware-authority.v2.json")
        for row in authority.get("routes", []):
            view.authority[(row["method"], row["path"])] = row
        canonical = load_json(path / "config" / "kong-canonical-middleware-routes.json")
        view.legacy_host_enabled = canonical.get("legacyHostEnabled")
        view.provider_effects_enabled = canonical.get("providerEffectsEnabled")
        view.denied_routes = len(canonical.get("deniedRoutes", []))
        edge = canonical.get("middlewareEdgeContract") or {}
        view.pinned_contract = json.dumps(edge, sort_keys=True) if edge else ""
        for route in canonical.get("contractRoutes", []):
            for method in route.get("methods", []):
                view.contract_routes[(method, route.get("pathTemplate", ""))] = route
        for row in load_json(path / "config" / "kong-access-policy.v1.json").get(
            "routes", []
        ):
            view.policy[row["routeId"]] = row
        pinned = path / "config" / "middleware-public-api-route-contract.sha256"
        view.vendored_hash = (
            pinned.read_text(encoding="utf-8").split()[0] if pinned.exists() else ""
        )
        vendored = path / "config" / "middleware-public-api-route-contract.v1.json"
        if vendored.exists():
            view.vendored_rows = len(load_json(vendored).get("routes", []))
        return view


@dataclass
class KeycloakClient:
    client_id: str
    audiences: tuple[str, ...]
    scopes: tuple[str, ...]
    service_account: bool
    token_lifespan: str | None
    optional_client_scopes: tuple[str, ...]
    default_client_scopes: tuple[str, ...]


def read_keycloak(path: Path) -> tuple[dict[str, KeycloakClient], dict[str, str]]:
    clients: dict[str, KeycloakClient] = {}
    for file in sorted((path / "config" / "clients").glob("*.json")):
        doc = load_json(file)
        audiences: list[str] = []
        scopes: list[str] = []
        for mapper in doc.get("protocolMappers", []):
            config = mapper.get("config", {})
            if mapper.get("protocolMapper") == "oidc-audience-mapper":
                audiences.append(
                    str(
                        config.get("included.custom.audience")
                        or config.get("included.client.audience")
                        or ""
                    )
                )
            if (
                mapper.get("protocolMapper") == "oidc-hardcoded-claim-mapper"
                and config.get("claim.name") == "scope"
            ):
                scopes.extend(str(config.get("claim.value", "")).split())
        clients[doc["clientId"]] = KeycloakClient(
            client_id=doc["clientId"],
            audiences=tuple(a for a in audiences if a),
            scopes=tuple(sorted(set(scopes))),
            service_account=bool(doc.get("serviceAccountsEnabled")),
            token_lifespan=(doc.get("attributes") or {}).get("access.token.lifespan"),
            optional_client_scopes=tuple(doc.get("optionalClientScopes") or ()),
            default_client_scopes=tuple(doc.get("defaultClientScopes") or ()),
        )
    client_scopes: dict[str, str] = {}
    for file in sorted((path / "config" / "client-scopes").glob("*.json")):
        doc = load_json(file)
        client_scopes[doc.get("name", file.stem)] = file.relative_to(path).as_posix()
    return clients, client_scopes


@dataclass
class CaddyView:
    kong_prefixes: tuple[str, ...]
    transitional_paths: tuple[str, ...]
    legacy_fallback_allowed: bool
    site_kong_matcher: tuple[str, ...]
    site_realtime_matcher: tuple[str, ...]
    site_has_legacy_catchall: bool
    header_up_set: tuple[str, ...]
    header_up_deleted: tuple[str, ...]

    @classmethod
    def read(cls, path: Path) -> "CaddyView":
        contract = load_json(path / "config" / "caddy-kong-contract.v1.json")
        site = (path / "sites" / "api.codestra.co.caddy").read_text(encoding="utf-8")
        kong = re.search(r"@kong path ([^\n]+)", site)
        realtime = re.search(r"@realtime path ([^\n]+)", site)
        return cls(
            kong_prefixes=tuple(contract.get("kongManagedPathPrefixes", [])),
            transitional_paths=tuple(contract.get("transitionalPaths", [])),
            legacy_fallback_allowed=bool(
                contract.get("migration", {}).get("legacyFallbackTemporarilyAllowed")
            ),
            site_kong_matcher=tuple(kong.group(1).split()) if kong else (),
            site_realtime_matcher=tuple(realtime.group(1).split()) if realtime else (),
            site_has_legacy_catchall="CADDY_LEGACY_API_UPSTREAM" in site,
            header_up_set=tuple(
                sorted(set(re.findall(r"header_up ([A-Za-z][A-Za-z0-9-]*) ", site)))
            ),
            header_up_deleted=tuple(
                sorted(set(re.findall(r"header_up -([A-Za-z][A-Za-z0-9-]*)", site)))
            ),
        )

    def routes_to_kong(self, path: str) -> bool:
        return any(
            path.startswith(p[:-1]) if p.endswith("*") else path == p
            for p in self.site_kong_matcher
        )

    def strips_client_identity(self) -> bool:
        return any(
            h.startswith(CLIENT_IDENTITY_HEADER_PREFIXES)
            for h in self.header_up_deleted
        )


def read_odoo_paths(path: Path) -> dict[str, dict[str, Any]]:
    """API paths referenced from Odoo add-ons (non-test), with their files and direction.

    A path referenced only from ``controllers/`` modules is an Odoo *inbound* controller
    (Middleware → Odoo); anything else is an *outbound* call Odoo makes (Odoo → Middleware).
    ``%s`` format placeholders and ``<type:name>`` converters are normalised to ``{}``.
    """
    hits: dict[str, set[str]] = {}
    url_keys: dict[str, set[str]] = {}
    for file in (path / "custom-addons").rglob("*.py"):
        posix = file.relative_to(path).as_posix()
        if "/tests/" in posix:
            continue
        text = file.read_text(encoding="utf-8", errors="ignore")
        # Configuration keys that hold the outbound base URL (env or ir.config_parameter).
        keys = set(
            re.findall(r"""getenv\(\s*["']([A-Z0-9_]*URL[A-Z0-9_]*)["']""", text)
        )
        keys |= set(
            re.findall(r"""get_param\(\s*["']([a-z0-9_.]*url[a-z0-9_.]*)["']""", text)
        )
        keys |= {
            "CODESTRA_" + m + "_API_BASE_URL"
            for m in re.findall(r'"CODESTRA_([A-Z]+)_" \+ name', text)
        }
        # Calls routed through the private provisioning-service client model use its base URL.
        if 'env["codestra.private.provisioning.service"]' in text:
            keys.add("CODESTRA_PROVISIONING_URL")
        # Literal paths, paths appended to a configured base inside f-strings or
        # %-formats (f"{base}/api/v1/…", "%s/control/callbacks/%s"), and route decorators.
        for found in re.findall(
            r"""["'](?:\{[^{}]*\}|%s)?(/(?:api|v1|v2|platform|control)/[A-Za-z0-9/_{}<>:.%-]+)""",
            text,
        ):
            normalised = re.sub(r"<[^>]+>|%s|\{[^}]+\}", "{}", found).rstrip("/")
            hits.setdefault(normalised, set()).add(posix)
            url_keys.setdefault(normalised, set()).update(keys)
    result: dict[str, dict[str, Any]] = {}
    for k, v in hits.items():
        keys = sorted(url_keys.get(k, ()))
        joined = "\n".join(
            (path / f).read_text(encoding="utf-8", errors="ignore") for f in sorted(v)
        )
        result[k] = {
            "files": sorted(v),
            "direction": "inbound"
            if all("/controllers/" in f for f in v)
            else "outbound",
            "url_config_keys": keys,
            # How the referencing modules authenticate and which edge headers they send.
            "auth": (
                "keycloak-client-credentials"
                if re.search(r"client_credentials|token_url|TOKEN_URL", joined)
                else "static-bearer-file+hmac"
                if re.search(r"_TOKEN_FILE", joined) and "hmac" in joined
                else "static-bearer-file"
                if re.search(r"_TOKEN_FILE", joined)
                else "shared-api-key"
                if re.search(r"api_key|service_secret|service_token", joined)
                else "unknown"
            ),
            "headers": sorted(
                h
                for h in (
                    "Idempotency-Key",
                    "X-Correlation-ID",
                    "traceparent",
                    "tracestate",
                    "X-Tenant-ID",
                )
                if re.search(re.escape(h), joined, re.IGNORECASE)
            ),
            "kind": (
                "EVENT"
                if "/events" in k
                else "RESULT"
                if "result" in k
                else "CALLBACK"
                if "callback" in k
                else "READ"
                if re.search(
                    r"/(status|health|projections|mappings|traces|capabilities)\b", k
                )
                else "COMMAND"
            ),
            "target_service": (
                "provisioning-service"
                if keys
                and all(
                    "PROVISIONING" in x.upper() and "MIDDLEWARE" not in x.upper()
                    for x in keys
                )
                else "middleware"
            ),
        }
    return result


def read_odoo_direct_provider_paths(path: Path) -> list[dict[str, Any]]:
    """Odoo modules that reach a provider without Middleware: an ir.mail_server pinned to a
    provider SMTP host, or an HTTP call to a provider host. Read from source, not names."""
    findings: list[dict[str, Any]] = []
    for file in (path / "custom-addons").rglob("*.py"):
        posix = file.relative_to(path).as_posix()
        if "/tests/" in posix:
            continue
        text = file.read_text(encoding="utf-8", errors="ignore")
        for host in re.findall(
            r"""smtp_host\s*(?:!=|==|=)\s*["']([a-z0-9.-]+\.[a-z]{2,})["']""", text
        ):
            findings.append(
                {
                    "module": posix.split("/")[1],
                    "file": posix,
                    "kind": "SMTP",
                    "host": host,
                }
            )
        for url in re.findall(
            r"""https?://[a-z0-9.-]*(?:klyrow|telnexa|vicidial)[a-z0-9.-]*""", text
        ):
            findings.append(
                {
                    "module": posix.split("/")[1],
                    "file": posix,
                    "kind": "HTTP",
                    "host": url,
                }
            )
    return sorted(findings, key=lambda f: (f["module"], f["file"], f["host"]))


def read_middleware_registry() -> dict[tuple[str, str], set[str]]:
    """Every (method, path) Middleware registers, with the profiles that mount it."""
    if str(MIDDLEWARE_ROOT) not in sys.path:
        sys.path.insert(0, str(MIDDLEWARE_ROOT))
    try:
        from app.application import AppProfile, create_app
        from app.router_registry import route_operations
    except (
        Exception
    ) as exc:  # pragma: no cover - the generator stays usable without app deps
        print(
            f"WARNING: Middleware route registry unavailable ({exc}); outbound targets are classified without it",
            file=sys.stderr,
        )
        return {}
    registered: dict[tuple[str, str], set[str]] = {}
    for profile in (
        AppProfile.INTEGRATION,
        AppProfile.CONTROL_PLANE,
        AppProfile.MONOLITH,
    ):
        app = create_app(profile=profile)
        for method, route_path in set(route_operations(app)):
            registered.setdefault((method, route_path), set()).add(profile.value)
    return registered


def read_n8n_targets(path: Path) -> dict[str, list[str]]:
    hits: dict[str, set[str]] = {}
    for directory in ("automations", "workflows"):
        base = path / directory
        if not base.exists():
            continue
        for file in base.rglob("*.json"):
            posix = file.relative_to(path).as_posix()
            text = file.read_text(encoding="utf-8", errors="ignore")
            for found in re.findall(r'"url":\s*"([^"]+)"', text):
                hits.setdefault(found, set()).add(posix)
    return {k: sorted(v) for k, v in hits.items()}


def n8n_target_path(url: str) -> str:
    """Path component of an N8N HTTP target, with expression fragments cut off."""
    without_scheme = re.sub(r"^[a-z]+://[^/]+", "", url)
    return without_scheme.split("{{", 1)[0].rstrip("/")


# --- matrix ------------------------------------------------------------------------------


def downstream_of(path: str, operation_id: str) -> str:
    text = f"{path} {operation_id}"
    if "/automation" in path or "n8n" in text:
        return "n8n"
    if "odoo" in text or "/campaign" in path:
        return "odoo"
    return "middleware"


def build(root: Path) -> dict[str, Any]:
    repos = {name: resolve(root, name) for name in REPOSITORIES}
    missing = [name for name, path in repos.items() if path is None]
    if missing:
        raise SystemExit(
            f"CROSS_REPO_MATRIX=FAIL missing local repositories: {', '.join(missing)}"
        )
    paths: dict[str, Path] = {
        name: path for name, path in repos.items() if path is not None
    }
    mw = paths["Middleware-"]
    contract = load_json(mw / "deploy" / "public-api-route-contract.json")
    middleware_hash = (
        (mw / "deploy" / "public-api-route-contract.sha256")
        .read_text(encoding="utf-8")
        .split()[0]
    )
    kong = KongView.read(paths["Kong"])
    keycloak, keycloak_scope_files = read_keycloak(paths["Keycloak"])
    caddy = CaddyView.read(paths["Caddy"])
    odoo_refs = read_odoo_paths(paths["Odoo"])
    odoo_outbound = {
        k: v["files"] for k, v in odoo_refs.items() if v["direction"] == "outbound"
    }
    odoo_meta = {k: v for k, v in odoo_refs.items() if v["direction"] == "outbound"}
    odoo_inbound = {
        k: v["files"] for k, v in odoo_refs.items() if v["direction"] == "inbound"
    }
    n8n_targets = read_n8n_targets(paths["N8N"])
    odoo_direct = read_odoo_direct_provider_paths(paths["Odoo"])
    registry = read_middleware_registry()
    registry_by_template: dict[str, set[str]] = {}
    for (_, route_path), profiles in registry.items():
        registry_by_template.setdefault(template_path(route_path), set()).update(
            profiles
        )
    scope_issuers: dict[str, list[str]] = {}
    for client in keycloak.values():
        for scope in client.scopes:
            scope_issuers.setdefault(scope, []).append(client.client_id)
    contract_keys = {(r["method"], r["path"]) for r in contract["routes"]}
    contract_prefixes = {path_prefix(r["path"]) for r in contract["routes"]}
    contract_templates = {template_path(r["path"]) for r in contract["routes"]}

    rows: list[dict[str, Any]] = []
    for row in contract["routes"]:
        key = (row["method"], row["path"])
        shared = row["classification"] == "shared_edge"
        authority = kong.authority.get(key) or {}
        kong_route = kong.contract_routes.get(key) or {}
        policy = kong.policy.get(kong_route.get("name", "")) or {}
        calling = as_list(row.get("calling_client"))
        azp = as_list(authority.get("azp"))
        scope = row.get("scope") or "none"
        audience = row.get("audience") or ""
        # A calling client is a Keycloak client id unless it is one of Middleware's policy
        # classes; classes are resolved through the Keycloak clients that issue the scope.
        concrete = [c for c in calling if c not in POLICY_CLASSES]
        unknown_ids = [c for c in concrete if c not in keycloak]
        issuers = scope_issuers.get(scope, [])
        keycloak_clients = [c for c in concrete if c in keycloak] or issuers
        client_docs = [keycloak[c] for c in keycloak_clients]
        tenant_policy = policy.get("tenantPolicy", "")
        downstream = (
            downstream_of(row["path"], row["operation_id"])
            if shared
            else ("odoo" if row.get("upstream", "").startswith("odoo") else "none")
        )
        entry: dict[str, Any] = {
            "METHOD": row["method"],
            "PATH": row["path"],
            "PUBLIC_PRIVATE": {
                "shared_edge": "PUBLIC",
                "private_only": "PRIVATE",
                "denied": "DENIED",
            }[row["classification"]],
            "CALLING_CLIENT": "|".join(calling) or "none",
            "KEYCLOAK_CLIENT": "|".join(keycloak_clients)
            or ("n/a" if not shared else "NONE_ISSUES_SCOPE"),
            "AUDIENCE": audience,
            "SCOPE": scope,
            "TENANT_REQUIRED": True
            if tenant_policy in TENANT_REQUIRED_POLICIES or "{tenant_id}" in row["path"]
            else ("selector" if tenant_policy in TENANT_SELECTOR_POLICIES else False),
            "CAMPAIGN_REQUIRED": "{campaign_id}" in row["path"]
            or tenant_policy == "CLAIM_FIXED_TENANT_CAMPAIGN",
            "IDEMPOTENCY_REQUIRED": bool(
                (row.get("idempotency") or {}).get("required")
            ),
            "IDEMPOTENCY_CARRIER": (row.get("idempotency") or {}).get(
                "carrier", "none"
            ),
            "CORRELATION_REQUIRED": bool(row.get("correlation_fields")),
            "TRACE_REQUIRED": "traceparent"
            in " ".join(row.get("correlation_fields") or [])
            or "correlation-id" in (kong_route.get("requiredPlugins") or []),
            "KONG_ROUTE": kong_route.get("name") or ("MISSING" if shared else "n/a"),
            "KONG_UPSTREAM": f"{kong_route['serviceHost']}:{kong_route['servicePort']}"
            if kong_route
            else "",
            "KONG_ACCESS_CLASS": policy.get("accessClass", ""),
            "KONG_AUDIENCE": authority.get("audience", ""),
            "KONG_SCOPE": authority.get("scope", ""),
            "KONG_AZP": "|".join(azp),
            "KONG_AUTH": authority.get("authentication", ""),
            "KONG_TENANT_POLICY": tenant_policy,
            "KONG_IDENTITY_PROPAGATION": policy.get("identityPropagation", ""),
            "MIDDLEWARE_HANDLER": row.get("operation_id", ""),
            "MIDDLEWARE_AUTH": row.get("auth", ""),
            "UPSTREAM": row.get("upstream", ""),
            "DOWNSTREAM": downstream,
            "RESULT_PATH": RESULT_PATHS.get(downstream, "") if shared else "",
            "CALLBACK_PATH": CALLBACK_PATHS.get(downstream, "") if shared else "",
            "OWNER": row.get("owner", ""),
            "CADDY_TO_KONG": caddy.routes_to_kong(row["path"]) if shared else None,
            "KEYCLOAK_CLIENT_EXISTS": (not unknown_ids) if shared else None,
            "KEYCLOAK_UNKNOWN_CLIENT_IDS": unknown_ids,
            "KEYCLOAK_AUDIENCE_OK": (
                any(audience in c.audiences for c in client_docs)
                if client_docs
                else None
            )
            if shared
            else None,
            "KEYCLOAK_SCOPE_OK": (
                "dynamic"
                if scope.startswith("resolved_from_")
                else (bool(issuers) if scope != "none" else True)
            )
            if shared
            else None,
            "KEYCLOAK_TOKEN_TTL": "|".join(
                sorted({c.token_lifespan or "realm-default" for c in client_docs})
            ),
            "ODOO_CALLS": odoo_outbound.get(template_path(row["path"]), []),
            "N8N_CALLS": [
                u
                for u in n8n_targets
                if n8n_target_path(u) in (row["path"], path_prefix(row["path"]))
            ],
        }
        rows.append(entry)

    shared_rows = [r for r in rows if r["PUBLIC_PRIVATE"] == "PUBLIC"]

    def resolve_outbound(p: str) -> str:
        """Odoo call sites that append a path to a configured /api/v1 base (for example
        ``{base}/control/callbacks``) are compared against the contract as /api/v1 + path."""
        if p in contract_templates or p in registry_by_template:
            return p
        candidate = "/api/v1" + p
        if candidate in contract_templates or candidate in registry_by_template:
            return candidate
        # A trailing dynamic segment may stand for a literal operation name
        # ("/control/callbacks/{}/{}" → "/api/v1/control/callbacks/{}/start" …).
        pattern = re.compile("^" + re.escape(candidate).replace(r"\{\}", "[^/]+") + "$")
        matches = sorted(
            t for t in registry_by_template if pattern.match(t.replace("{}", "x"))
        )
        if matches:
            registry_by_template[candidate] = set().union(
                *(registry_by_template[t] for t in matches)
            )
            if all(t in contract_templates for t in matches):
                contract_templates.add(candidate)
            return candidate
        return p

    odoo_resolved = {p: resolve_outbound(p) for p in odoo_outbound}
    v3_rows = [
        {
            "METHOD": method,
            "PATH": path,
            "SCOPE": scope,
            "IN_MIDDLEWARE_CONTRACT": (method, path) in contract_keys,
            "KONG_ROUTE": "V3_PENDING_FINAL_MIDDLEWARE_CONTRACT",
            "KEYCLOAK_SCOPE_ISSUED_BY": scope_issuers.get(scope, []),
            "CADDY_TO_KONG": caddy.routes_to_kong(path),
        }
        for method, path, scope in V3_PENDING_ROUTES
    ]
    summary: dict[str, Any] = {
        "MIDDLEWARE_CONTRACT_ROWS": len(rows),
        "SHARED_EDGE_ROWS": len(shared_rows),
        "PRIVATE_ONLY_ROWS": sum(1 for r in rows if r["PUBLIC_PRIVATE"] == "PRIVATE"),
        "DENIED_ROWS": sum(1 for r in rows if r["PUBLIC_PRIVATE"] == "DENIED"),
        "MIDDLEWARE_CONTRACT_HASH": middleware_hash,
        "KONG_STABLE_ROUTES": sum(
            1 for r in shared_rows if r["KONG_ROUTE"] not in ("", "MISSING", "n/a")
        ),
        "KONG_MISSING_ROUTES": [
            f"{r['METHOD']} {r['PATH']}"
            for r in shared_rows
            if r["KONG_ROUTE"] == "MISSING"
        ],
        "KONG_UPSTREAM_NON_CANONICAL": [
            f"{r['METHOD']} {r['PATH']} -> {r['KONG_UPSTREAM']}"
            for r in shared_rows
            if r["KONG_UPSTREAM"] and r["KONG_UPSTREAM"] != CANONICAL_UPSTREAM
        ],
        "KONG_VENDORED_CONTRACT_HASH": kong.vendored_hash,
        "KONG_VENDORED_CONTRACT_ROWS": kong.vendored_rows,
        "KONG_PINNED_CONTRACT": kong.pinned_contract,
        "KONG_VENDORED_CONTRACT_STALE": kong.vendored_hash != middleware_hash,
        "KONG_LEGACY_HOST_ENABLED": kong.legacy_host_enabled,
        "KONG_PROVIDER_EFFECTS_ENABLED": kong.provider_effects_enabled,
        "KONG_DENIED_ROUTES": kong.denied_routes,
        "AUDIENCE_MISMATCHES": [
            f"{r['METHOD']} {r['PATH']}: middleware={r['AUDIENCE']} kong={r['KONG_AUDIENCE']}"
            for r in shared_rows
            if r["KONG_AUDIENCE"] and r["KONG_AUDIENCE"] != r["AUDIENCE"]
        ],
        "SCOPE_MISMATCHES": [
            f"{r['METHOD']} {r['PATH']}: middleware={r['SCOPE']} kong={r['KONG_SCOPE']}"
            for r in shared_rows
            if r["KONG_SCOPE"] and r["KONG_SCOPE"] != r["SCOPE"]
        ],
        "AZP_MISMATCHES": [
            f"{r['METHOD']} {r['PATH']}: middleware={r['CALLING_CLIENT']} kong={r['KONG_AZP']}"
            for r in shared_rows
            if r["KONG_AZP"] and r["KONG_AZP"] != r["CALLING_CLIENT"]
        ],
        "AUTH_MISMATCHES": [
            f"{r['METHOD']} {r['PATH']}: middleware={r['MIDDLEWARE_AUTH']} kong={r['KONG_AUTH']}"
            for r in shared_rows
            if r["KONG_AUTH"] and r["KONG_AUTH"] != r["MIDDLEWARE_AUTH"]
        ],
        "METHOD_MISMATCHES": [
            f"{r['METHOD']} {r['PATH']}"
            for r in shared_rows
            if r["KONG_ROUTE"] == "MISSING"
            and r["PATH"] in {p for (_, p) in kong.contract_routes}
        ],
        "CADDY_FALLTHROUGH_ROUTES": [
            f"{r['METHOD']} {r['PATH']}"
            for r in shared_rows
            if r["CADDY_TO_KONG"] is False
        ],
        "CADDY_KONG_MATCHER": list(caddy.site_kong_matcher),
        "CADDY_REALTIME_MATCHER": list(caddy.site_realtime_matcher),
        "CADDY_CONTRACT_PREFIXES_MATCH_SITE": sorted(caddy.kong_prefixes)
        == sorted(p.rstrip("*") for p in caddy.site_kong_matcher),
        "CADDY_LEGACY_FALLBACK_ALLOWED": caddy.legacy_fallback_allowed,
        "CADDY_SITE_HAS_LEGACY_CATCHALL": caddy.site_has_legacy_catchall,
        "CADDY_HEADER_UP_SET": list(caddy.header_up_set),
        "CADDY_HEADER_UP_DELETED": list(caddy.header_up_deleted),
        "CADDY_STRIPS_CLIENT_IDENTITY_HEADERS": caddy.strips_client_identity(),
        "CADDY_REQUIRED_HEADERS_BLOCKED": [
            h for h in REQUIRED_EDGE_HEADERS if h in caddy.header_up_deleted
        ],
        "KEYCLOAK_CLIENTS": sorted(keycloak),
        "KEYCLOAK_CLIENT_SCOPES": keycloak_scope_files,
        "KEYCLOAK_UNKNOWN_CLIENT_IDS": sorted(
            {c for r in shared_rows for c in r["KEYCLOAK_UNKNOWN_CLIENT_IDS"]}
        ),
        "KEYCLOAK_AUDIENCE_MISSING": sorted(
            {
                f"{r['KEYCLOAK_CLIENT']}->{r['AUDIENCE']}"
                for r in shared_rows
                if r["KEYCLOAK_AUDIENCE_OK"] is False
            }
        ),
        "KEYCLOAK_SCOPE_NOT_ISSUED": sorted(
            {r["SCOPE"] for r in shared_rows if r["KEYCLOAK_SCOPE_OK"] is False}
        ),
        "KEYCLOAK_ROUTES_WITHOUT_ISSUER": sum(
            1 for r in shared_rows if r["KEYCLOAK_SCOPE_OK"] is False
        ),
        "ODOO_OUTBOUND_TARGETS": {
            p: {
                "files": files,
                "resolved_path": odoo_resolved[p],
                "classification": (
                    "OTHER_SERVICE:" + odoo_meta[p]["target_service"]
                    if odoo_meta[p]["target_service"] != "middleware"
                    else "EDGE_CONTRACT"
                    if odoo_resolved[p] in contract_templates
                    else "MIDDLEWARE_"
                    + "+".join(sorted(registry_by_template[odoo_resolved[p]])).upper()
                    + "_ONLY"
                    if odoo_resolved[p] in registry_by_template
                    else "NOT_SERVED_BY_MIDDLEWARE"
                ),
                "url_config_keys": odoo_meta[p]["url_config_keys"],
                "kind": odoo_meta[p]["kind"],
                "auth": odoo_meta[p]["auth"],
                "headers": odoo_meta[p]["headers"],
                "caddy_to_kong": caddy.routes_to_kong(
                    odoo_resolved[p].replace("{}", "x")
                ),
            }
            for p, files in sorted(odoo_outbound.items())
        },
        "ODOO_INBOUND_CONTROLLERS": dict(sorted(odoo_inbound.items())),
        "ODOO_DIRECT_PROVIDER_PATHS": odoo_direct,
        "ODOO_OUTBOUND_NOT_IN_EDGE_CONTRACT": sorted(
            p
            for p in odoo_outbound
            if odoo_resolved[p] not in contract_templates
            and odoo_meta[p]["target_service"] == "middleware"
        ),
        "ODOO_OUTBOUND_NOT_SERVED_BY_MIDDLEWARE": sorted(
            p
            for p in odoo_outbound
            if odoo_resolved[p] not in contract_templates
            and odoo_resolved[p] not in registry_by_template
            and odoo_meta[p]["target_service"] == "middleware"
        ),
        "MIDDLEWARE_REGISTRY_OPERATIONS": len(registry),
        "N8N_TARGETS": dict(sorted(n8n_targets.items())),
        "N8N_TARGETS_NOT_IN_CONTRACT": sorted(
            u
            for u in n8n_targets
            if n8n_target_path(u) not in contract_prefixes
            and n8n_target_path(u) not in {r["PATH"] for r in rows}
        ),
        "V3_PENDING_ROUTES": v3_rows,
        "V3_PENDING_FINAL_MIDDLEWARE_CONTRACT": True,
        "REPOSITORIES": {
            name: {
                "checkout": path.name,
                "branch": git(path, "branch", "--show-current") or "detached",
                "head": git(path, "rev-parse", "HEAD"),
            }
            for name, path in paths.items()
        },
    }
    return {
        "schema": "codestra.core-contract-matrix.v1",
        "summary": summary,
        "rows": rows,
    }


MATRIX_COLUMNS = (
    "METHOD",
    "PATH",
    "PUBLIC_PRIVATE",
    "CALLING_CLIENT",
    "KEYCLOAK_CLIENT",
    "AUDIENCE",
    "SCOPE",
    "TENANT_REQUIRED",
    "CAMPAIGN_REQUIRED",
    "IDEMPOTENCY_REQUIRED",
    "CORRELATION_REQUIRED",
    "TRACE_REQUIRED",
    "KONG_ROUTE",
    "MIDDLEWARE_HANDLER",
    "DOWNSTREAM",
    "RESULT_PATH",
    "CALLBACK_PATH",
    "OWNER",
    "CADDY_TO_KONG",
    "KEYCLOAK_SCOPE_OK",
    "KEYCLOAK_AUDIENCE_OK",
)
SUMMARY_SCALARS = (
    "MIDDLEWARE_CONTRACT_ROWS",
    "SHARED_EDGE_ROWS",
    "PRIVATE_ONLY_ROWS",
    "DENIED_ROWS",
    "MIDDLEWARE_CONTRACT_HASH",
    "KONG_STABLE_ROUTES",
    "KONG_VENDORED_CONTRACT_HASH",
    "KONG_VENDORED_CONTRACT_ROWS",
    "KONG_VENDORED_CONTRACT_STALE",
    "KONG_LEGACY_HOST_ENABLED",
    "KONG_PROVIDER_EFFECTS_ENABLED",
    "KONG_DENIED_ROUTES",
    "CADDY_CONTRACT_PREFIXES_MATCH_SITE",
    "CADDY_LEGACY_FALLBACK_ALLOWED",
    "CADDY_SITE_HAS_LEGACY_CATCHALL",
    "CADDY_STRIPS_CLIENT_IDENTITY_HEADERS",
    "CADDY_HEADER_UP_SET",
    "CADDY_HEADER_UP_DELETED",
    "CADDY_REQUIRED_HEADERS_BLOCKED",
    "KEYCLOAK_ROUTES_WITHOUT_ISSUER",
    "MIDDLEWARE_REGISTRY_OPERATIONS",
    "V3_PENDING_FINAL_MIDDLEWARE_CONTRACT",
)
SUMMARY_LISTS = (
    "KONG_MISSING_ROUTES",
    "KONG_UPSTREAM_NON_CANONICAL",
    "AUDIENCE_MISMATCHES",
    "SCOPE_MISMATCHES",
    "AZP_MISMATCHES",
    "AUTH_MISMATCHES",
    "METHOD_MISMATCHES",
    "CADDY_FALLTHROUGH_ROUTES",
    "KEYCLOAK_UNKNOWN_CLIENT_IDS",
    "KEYCLOAK_AUDIENCE_MISSING",
    "KEYCLOAK_SCOPE_NOT_ISSUED",
    "ODOO_OUTBOUND_NOT_IN_EDGE_CONTRACT",
    "ODOO_OUTBOUND_NOT_SERVED_BY_MIDDLEWARE",
    "N8N_TARGETS_NOT_IN_CONTRACT",
)


def render_markdown(matrix: dict[str, Any]) -> str:
    s = matrix["summary"]
    lines = [
        "# Codestra core contract matrix (generated from local source)",
        "",
        "Generated by `scripts/cross_repo_contract_matrix.py --write`. Every value is read from a repository file "
        "named in the generator; mismatch lists are concrete differences between two files. Do not hand-edit.",
        "",
        "## Repositories",
    ]
    for name, meta in s["REPOSITORIES"].items():
        lines.append(f"- **{name}** `{meta['branch']}` @ `{meta['head'][:12]}`")
    lines += ["", "## Summary"]
    for key in SUMMARY_SCALARS:
        lines.append(f"- `{key}` = `{s[key]}`")
    for key in SUMMARY_LISTS:
        values = s[key]
        lines.append(
            f"- `{key}` = {len(values)}"
            + ("" if not values else "\n" + "\n".join(f"  - `{v}`" for v in values))
        )
    lines += [
        "",
        "## Odoo → Middleware outbound targets (from `custom-addons`, non-test, non-controller)",
    ]
    lines.append(
        "| PATH | RESOLVED | KIND | AUTH | HEADERS | CLASSIFICATION | CADDY_TO_KONG | URL_CONFIG_KEYS | FILES |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for path, meta in s["ODOO_OUTBOUND_TARGETS"].items():
        lines.append(
            f"| `{path}` | `{meta['resolved_path']}` | {meta['kind']} | {meta['auth']} | "
            f"{', '.join(meta['headers']) or '—'} | {meta['classification']} | {meta['caddy_to_kong']} | "
            + ", ".join(f"`{k}`" for k in meta["url_config_keys"])
            + " | "
            + ", ".join(f"`{f}`" for f in meta["files"])
            + " |"
        )
    lines += ["", "## Odoo direct provider paths (bypass Middleware; from source)"]
    for item in s["ODOO_DIRECT_PROVIDER_PATHS"] or []:
        lines.append(
            f"- `{item['module']}`: {item['kind']} to `{item['host']}` (`{item['file']}`)"
        )
    if not s["ODOO_DIRECT_PROVIDER_PATHS"]:
        lines.append("- none")
    lines += [
        "",
        "## Middleware → Odoo inbound controllers (Odoo `controllers/`; served by Odoo, not Middleware routes)",
    ]
    for path, files in s["ODOO_INBOUND_CONTROLLERS"].items():
        lines.append(f"- `{path}` ← " + ", ".join(f"`{f}`" for f in files))
    lines += ["", "## N8N HTTP targets (from `automations`/`workflows`)"]
    for url, files in s["N8N_TARGETS"].items():
        lines.append(f"- `{url}` ← " + ", ".join(f"`{f}`" for f in files))
    lines += ["", "## Keycloak clients (from `config/clients`)"]
    lines.append("- " + ", ".join(f"`{c}`" for c in s["KEYCLOAK_CLIENTS"]))
    lines.append(
        "- client scopes: "
        + ", ".join(f"`{k}` (`{v}`)" for k, v in s["KEYCLOAK_CLIENT_SCOPES"].items())
    )
    lines += [
        "",
        "## Middleware V3 kernel routes (V3_PENDING_FINAL_MIDDLEWARE_CONTRACT=true)",
    ]
    lines.append(
        "| METHOD | PATH | SCOPE | IN_MIDDLEWARE_CONTRACT | KONG_ROUTE | KEYCLOAK_SCOPE_ISSUED_BY | CADDY_TO_KONG |"
    )
    lines.append("|---|---|---|---|---|---|---|")
    for v in s["V3_PENDING_ROUTES"]:
        lines.append(
            f"| {v['METHOD']} | `{v['PATH']}` | `{v['SCOPE']}` | {v['IN_MIDDLEWARE_CONTRACT']} | {v['KONG_ROUTE']} | {', '.join(v['KEYCLOAK_SCOPE_ISSUED_BY']) or '—'} | {v['CADDY_TO_KONG']} |"
        )
    lines += [
        "",
        "## Matrix",
        "| " + " | ".join(MATRIX_COLUMNS) + " |",
        "|" + "---|" * len(MATRIX_COLUMNS),
    ]
    for row in matrix["rows"]:
        lines.append(
            "| "
            + " | ".join(
                str(row.get(c, "")).replace("|", "\\|") for c in MATRIX_COLUMNS
            )
            + " |"
        )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n", 1)[0])
    parser.add_argument(
        "--root",
        type=Path,
        default=default_root(),
        help="directory holding the six repositories",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="write docs/integration/core-contract-matrix.{md,json}",
    )
    parser.add_argument("--json", action="store_true", help="print the matrix as JSON")
    args = parser.parse_args(argv)
    matrix = build(args.root)
    if args.write:
        out = MIDDLEWARE_ROOT / "docs" / "integration"
        out.mkdir(parents=True, exist_ok=True)
        (out / "core-contract-matrix.json").write_text(
            json.dumps(matrix, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        (out / "core-contract-matrix.md").write_text(
            render_markdown(matrix), encoding="utf-8", newline="\n"
        )
    if args.json:
        print(json.dumps(matrix, indent=2, sort_keys=True))
        return 0
    s = matrix["summary"]
    print(
        f"CROSS_REPO_MATRIX=OK rows={s['MIDDLEWARE_CONTRACT_ROWS']} shared_edge={s['SHARED_EDGE_ROWS']} "
        f"kong_stable={s['KONG_STABLE_ROUTES']} kong_missing={len(s['KONG_MISSING_ROUTES'])} "
        f"kong_non_canonical_upstream={len(s['KONG_UPSTREAM_NON_CANONICAL'])} kong_vendored_stale={s['KONG_VENDORED_CONTRACT_STALE']} "
        f"audience_mismatch={len(s['AUDIENCE_MISMATCHES'])} scope_mismatch={len(s['SCOPE_MISMATCHES'])} azp_mismatch={len(s['AZP_MISMATCHES'])} "
        f"caddy_fallthrough={len(s['CADDY_FALLTHROUGH_ROUTES'])} caddy_strips_identity={s['CADDY_STRIPS_CLIENT_IDENTITY_HEADERS']} "
        f"keycloak_unknown_clients={s['KEYCLOAK_UNKNOWN_CLIENT_IDS']} keycloak_scope_not_issued={len(s['KEYCLOAK_SCOPE_NOT_ISSUED'])} "
        f"odoo_outbound_not_in_edge_contract={len(s['ODOO_OUTBOUND_NOT_IN_EDGE_CONTRACT'])} odoo_outbound_not_served={len(s['ODOO_OUTBOUND_NOT_SERVED_BY_MIDDLEWARE'])} n8n_targets_not_in_contract={len(s['N8N_TARGETS_NOT_IN_CONTRACT'])}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
