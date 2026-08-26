#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

: "${RUNTIME_INTEGRATION_TESTS:?RUNTIME_INTEGRATION_TESTS must be set to 1}"
: "${RUNTIME_INTEGRATION_ALLOW_DISPOSABLE:?RUNTIME_INTEGRATION_ALLOW_DISPOSABLE must be YES}"
: "${DATABASE_URL:?DATABASE_URL is required}"
: "${REDIS_URL:?REDIS_URL is required}"

if [[ "$RUNTIME_INTEGRATION_TESTS" != "1" ]]; then
  echo "ERROR=RUNTIME_INTEGRATION_TESTS_MUST_EQUAL_1" >&2
  exit 1
fi
if [[ "$RUNTIME_INTEGRATION_ALLOW_DISPOSABLE" != "YES" ]]; then
  echo "ERROR=DISPOSABLE_TEST_ACK_REQUIRED" >&2
  exit 1
fi

python3 - <<'PY'
import os
from urllib.parse import urlparse

pg = urlparse(os.environ["DATABASE_URL"])
redis = urlparse(os.environ["REDIS_URL"])

if pg.scheme not in {"postgres", "postgresql"}:
    raise SystemExit("DATABASE_URL must use postgres/postgresql")
if pg.hostname not in {"127.0.0.1", "localhost"}:
    raise SystemExit("DATABASE_URL must target localhost disposable PostgreSQL")
if not pg.path.lstrip("/").startswith("middleware_test_"):
    raise SystemExit("database name must start with middleware_test_")
if redis.scheme not in {"redis", "rediss"}:
    raise SystemExit("REDIS_URL must use redis/rediss")
if redis.hostname not in {"127.0.0.1", "localhost"}:
    raise SystemExit("REDIS_URL must target localhost disposable Redis")

print("DISPOSABLE_INTEGRATION_TARGETS=PASS")
PY

python3 -m venv .venv-integration
trap 'rm -rf .venv-integration' EXIT
. .venv-integration/bin/activate
python -m pip install --disable-pip-version-check --no-input --quiet --upgrade pip
python -m pip install --disable-pip-version-check --no-input --quiet -r requirements-runtime.txt

pytest -q tests/integration/test_postgres_redis.py

echo "POSTGRES_INTEGRATION=PASS"
echo "REDIS_INTEGRATION=PASS"
echo "INBOX_CONCURRENCY=PASS"
echo "OUTBOX_LEASE_DLQ=PASS"
echo "RUNTIME_INTEGRATION_CI=PASS"
