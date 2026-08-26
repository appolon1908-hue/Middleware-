from __future__ import annotations

import os
from urllib.parse import urlparse

import pytest


@pytest.fixture(scope="session", autouse=True)
def require_disposable_integration_targets() -> None:
    """Fail before any destructive fixture if integration mode is unsafe.

    The shell wrapper performs the same checks, but the pytest suite must remain
    safe when invoked directly by a developer or alternate CI runner.
    """

    if os.getenv("RUNTIME_INTEGRATION_TESTS") != "1":
        return

    if os.getenv("RUNTIME_INTEGRATION_ALLOW_DISPOSABLE") != "YES":
        pytest.fail("RUNTIME_INTEGRATION_ALLOW_DISPOSABLE=YES is required")

    database_url = os.getenv("DATABASE_URL", "")
    redis_url = os.getenv("REDIS_URL", "")
    pg = urlparse(database_url)
    redis = urlparse(redis_url)

    if pg.scheme not in {"postgres", "postgresql"}:
        pytest.fail("DATABASE_URL must use postgres/postgresql")
    if pg.hostname not in {"127.0.0.1", "localhost"}:
        pytest.fail("DATABASE_URL must target localhost disposable PostgreSQL")
    if not pg.path.lstrip("/").startswith("middleware_test_"):
        pytest.fail("database name must start with middleware_test_")

    if redis.scheme not in {"redis", "rediss"}:
        pytest.fail("REDIS_URL must use redis/rediss")
    if redis.hostname not in {"127.0.0.1", "localhost"}:
        pytest.fail("REDIS_URL must target localhost disposable Redis")
    try:
        redis_db = int(redis.path.lstrip("/") or "0")
    except ValueError:
        pytest.fail("REDIS_URL must select an explicit numeric disposable DB")
    if redis_db <= 0:
        pytest.fail("REDIS_URL must not target Redis DB 0 for destructive integration tests")
