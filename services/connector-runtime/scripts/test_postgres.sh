#!/usr/bin/env bash
set -Eeuo pipefail
: "${DATABASE_URL:?DATABASE_URL is required}"
cd "$(dirname "$0")/.."
alembic upgrade head
pytest -q -m postgres
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
PGURL="${DATABASE_URL/postgresql+psycopg:/postgresql:}"
pg_dump --format=custom --no-owner --no-acl "$PGURL" > "$TMP/connector.dump"
createdb_url="${PGURL%/*}/connector_restore"
psql "${PGURL%/*}/postgres" -v ON_ERROR_STOP=1 -c 'DROP DATABASE IF EXISTS connector_restore' -c 'CREATE DATABASE connector_restore'
pg_restore --no-owner --no-acl --dbname "$createdb_url" "$TMP/connector.dump"
psql "$createdb_url" -v ON_ERROR_STOP=1 -c "SELECT count(*) FROM connector_sdk.connector_installations"
alembic downgrade base
alembic upgrade head
