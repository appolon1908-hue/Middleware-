"""PostgreSQL repository helpers for the automation control plane.

This module accepts a PEP 249 compatible PostgreSQL connection so deployment
can choose psycopg, psycopg2, or an existing application connection pool.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol


ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS_DIR = ROOT / "migrations" / "automation"


class Cursor(Protocol):
    def execute(self, sql: str, params: Any | None = None) -> Any: ...
    def fetchone(self) -> Any: ...
    def fetchall(self) -> list[Any]: ...


class Connection(Protocol):
    def cursor(self) -> Any: ...
    def commit(self) -> None: ...
    def rollback(self) -> None: ...


def migration_files() -> list[Path]:
    return sorted(MIGRATIONS_DIR.glob("*.sql"))


def apply_migrations(connection: Connection) -> list[str]:
    applied: list[str] = []
    try:
        with connection.cursor() as cursor:
            for path in migration_files():
                cursor.execute(path.read_text(encoding="utf-8"))
                applied.append(path.name)
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    return applied


class PostgresAutomationRepository:
    def __init__(self, connection: Connection) -> None:
        self.connection = connection

    def insert_job(self, job: dict[str, Any], delivery_token_hash: str) -> None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO automation_jobs (
                    job_id, tenant_id, actor_id, workflow_key, workflow_version,
                    workflow_family, delivery_token_hash, state, attempts
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    job["job_id"],
                    job["tenant_id"],
                    job["actor_id"],
                    job["workflow_key"],
                    job["workflow_version"],
                    job["workflow_family"],
                    delivery_token_hash,
                    job["state"],
                    job["attempts"],
                ),
            )
        self.connection.commit()

    def fetch_job_state(self, job_id: str) -> str | None:
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT state FROM automation_jobs WHERE job_id = %s", (job_id,))
            row = cursor.fetchone()
        return None if row is None else row[0]
