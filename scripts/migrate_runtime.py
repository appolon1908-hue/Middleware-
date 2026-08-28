#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import os
from pathlib import Path

import asyncpg


ROOT = Path(__file__).resolve().parents[1]


async def main() -> None:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("DATABASE_URL is required")
    conn = await asyncpg.connect(url, command_timeout=30)
    try:
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
