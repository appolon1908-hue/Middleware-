from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "migration_lineage.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("migration_lineage", MODULE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeConnection:
    def __init__(self, *, table_present: bool, revisions: tuple[str, ...] = ()) -> None:
        self.table_present = table_present
        self.revisions = revisions
        self.queries: list[str] = []

    async def fetchval(self, query: str):
        self.queries.append(query)
        return "alembic_version" if self.table_present else None

    async def fetch(self, query: str):
        self.queries.append(query)
        return [{"version_num": revision} for revision in self.revisions]


def test_repository_alembic_graph_is_complete_and_acyclic() -> None:
    module = _load_module()
    graph = module.discover_repository_graph(ROOT)
    assert set(graph) == {
        "20260828_0001",
        "20260828_0002",
        "20260828_0003",
        "20260828_0004",
    }
    assert graph["20260828_0001"] == ()
    assert graph["20260828_0004"] == ("20260828_0003",)


def test_known_database_revision_is_accepted() -> None:
    module = _load_module()
    report = module.validate_observed_revisions(["20260828_0004"], root=ROOT)
    assert report.alembic_table_present is True
    assert report.database_revisions == ("20260828_0004",)


def test_unknown_staging_revision_fails_closed() -> None:
    module = _load_module()
    with pytest.raises(module.LineageError) as raised:
        module.validate_observed_revisions(["0053_callback_worker_grants"], root=ROOT)
    message = str(raised.value)
    assert "0053_callback_worker_grants" in message
    assert "restore the exact historical migration source" in message
    assert "before any stamp, upgrade, or runtime migration" in message


@pytest.mark.asyncio
async def test_database_without_alembic_table_is_read_only_compatible() -> None:
    module = _load_module()
    conn = FakeConnection(table_present=False)
    report = await module.inspect_database_lineage(conn, root=ROOT)
    assert report.alembic_table_present is False
    assert report.database_revisions == ()
    assert len(conn.queries) == 1
    assert "to_regclass" in conn.queries[0]


@pytest.mark.asyncio
async def test_database_with_unknown_revision_is_rejected() -> None:
    module = _load_module()
    conn = FakeConnection(
        table_present=True,
        revisions=("0053_callback_worker_grants",),
    )
    with pytest.raises(module.LineageError):
        await module.inspect_database_lineage(conn, root=ROOT)
    assert len(conn.queries) == 2
    assert "SELECT version_num" in conn.queries[1]


def test_runtime_migration_checks_lineage_before_sql_execution() -> None:
    source = (ROOT / "scripts" / "migrate_runtime.py").read_text(encoding="utf-8")
    lineage_check = source.index("inspect_database_lineage")
    migration_loop = source.index("for migration in migrations")
    execute_migration = source.index("await conn.execute")
    assert lineage_check < migration_loop < execute_migration
