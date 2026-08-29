#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import os
from pathlib import Path

import asyncpg

from migration_lineage import LineageError, inspect_database_lineage


ROOT = Path(__file__).resolve().parents[1]


async def main() -> None:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("DATABASE_URL is required")
    conn = await asyncpg.connect(url, command_timeout=30)
    try:
        try:
            lineage = await inspect_database_lineage(conn, root=ROOT)
        except LineageError as exc:
            raise SystemExit(f"RUNTIME_MIGRATION_LINEAGE=FAIL {exc}") from exc

        if lineage.alembic_table_present:
            print(
                "RUNTIME_MIGRATION_LINEAGE=PASS "
                + "DATABASE_REVISIONS="
                + ",".join(lineage.database_revisions)
            )
        else:
            print("RUNTIME_MIGRATION_LINEAGE=PASS ALEMBIC_VERSION_TABLE=ABSENT")

        migrations = sorted((ROOT / "migrations").glob("[0-9][0-9][0-9][0-9]_*.sql"))
        if not migrations:
            raise SystemExit("no runtime migrations found")
        for migration in migrations:
            await conn.execute(migration.read_text(encoding="utf-8"))
            print(f"RUNTIME_MIGRATION_APPLIED={migration.name}")
    finally:
        await conn.close()
    print("RUNTIME_MIGRATION=PASS")


if __name__ == "__main__":
    asyncio.run(main())
