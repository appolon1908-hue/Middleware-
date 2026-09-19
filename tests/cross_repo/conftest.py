"""Cross-repository contract tests for the Codestra core.

These tests read the *local* checkouts of Kong, Caddy, Keycloak, Odoo and N8N
next to this repository (the mission integration worktrees first, the primary
checkouts otherwise) and prove the contract Middleware publishes is what the
other repositories actually declare. They never contact a network service.

When a repository is not present locally the whole package is skipped with the
reason recorded; a skip is never reported as a pass.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.cross_repo_contract_matrix import (  # noqa: E402
    REPOSITORIES,
    build,
    default_root,
    resolve,
)


def _root() -> Path:
    """The directory holding the six repositories; CODESTRA_REPOS_ROOT overrides the
    default (the parent of this checkout, or of its .worktrees directory)."""
    override = os.environ.get("CODESTRA_REPOS_ROOT")
    return Path(override) if override else default_root()


def _repositories() -> dict[str, Path]:
    root = _root()
    found = {name: resolve(root, name) for name in REPOSITORIES}
    missing = sorted(name for name, path in found.items() if path is None)
    if missing:
        pytest.skip(
            f"local repositories not present next to Middleware: {', '.join(missing)}"
        )
    return {name: path for name, path in found.items() if path is not None}


@pytest.fixture(scope="session")
def repos() -> dict[str, Path]:
    return _repositories()


@pytest.fixture(scope="session")
def matrix(repos: dict[str, Path]) -> dict[str, Any]:
    return build(_root())


@pytest.fixture(scope="session")
def summary(matrix: dict[str, Any]) -> dict[str, Any]:
    return matrix["summary"]


@pytest.fixture(scope="session")
def shared_rows(matrix: dict[str, Any]) -> list[dict[str, Any]]:
    return [row for row in matrix["rows"] if row["PUBLIC_PRIVATE"] == "PUBLIC"]


@pytest.fixture(scope="session")
def middleware_contract() -> dict[str, Any]:
    return json.loads(
        (ROOT / "deploy" / "public-api-route-contract.json").read_text(encoding="utf-8")
    )


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def odoo_controller_routes(odoo: Path) -> dict[str, set[str]]:
    """Every ``@http.route`` path Odoo's add-ons expose (template form) with its methods."""
    routes: dict[str, set[str]] = {}
    for file in (odoo / "custom-addons").rglob("controllers/*.py"):
        text = file.read_text(encoding="utf-8", errors="ignore")
        for block in re.findall(r"@http\.route\((.*?)\)\s*\n\s*def ", text, re.S):
            paths = re.findall(r"""["'](/api/v1/[A-Za-z0-9/_<>:.-]+)["']""", block)
            methods = re.findall(r"""methods\s*=\s*\[([^\]]*)\]""", block)
            method_set = (
                set(re.findall(r"[A-Z]+", methods[0])) if methods else {"GET", "POST"}
            )
            for path in paths:
                template = re.sub(r"<[^>]+>", "{}", path)
                routes.setdefault(template, set()).update(method_set)
    return routes
