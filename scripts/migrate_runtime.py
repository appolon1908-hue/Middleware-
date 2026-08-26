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
    sql = (ROOT / "migrations" / "0001_runtime.sql").read_text(encoding="utf-8")
    conn = await asyncpg.connect(url, command_timeout=30)
    try:
        await conn.execute(sql)
    finally:
        await conn.close()
    print("RUNTIME_MIGRATION=PASS")


if __name__ == "__main__":
    asyncio.run(main())
