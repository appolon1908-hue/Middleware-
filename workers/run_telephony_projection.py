#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import logging
import os

import asyncpg
import httpx

from app.config import ConfigurationError, Settings
from app.telephony_projection import (
    ODOO_CALL_EVENT_DESTINATION,
    OdooCallEventDispatcher,
    PostgresTelephonyProjectionStore,
    TelephonyOutboxStore,
)
from app.worker import OutboxWorker


log = logging.getLogger(__name__)


def _poll_seconds() -> float:
    raw = os.environ.get("TELEPHONY_PROJECTION_POLL_SECONDS", "0.25")
    try:
        value = float(raw)
    except ValueError as exc:
        raise ConfigurationError(
            "TELEPHONY_PROJECTION_POLL_SECONDS must be numeric"
        ) from exc
    if not 0.05 <= value <= 5.0:
        raise ConfigurationError(
            "TELEPHONY_PROJECTION_POLL_SECONDS must be between 0.05 and 5.0"
        )
    return value


async def _project_forever(
    store: PostgresTelephonyProjectionStore,
    poll_seconds: float,
) -> None:
    while True:
        projected = await store.project_once()
        if not projected:
            await asyncio.sleep(poll_seconds)


async def run() -> None:
    settings = Settings.from_env()
    if os.environ.get("TELEPHONY_ODOO_PROJECTION_ENABLED", "").strip().lower() != "true":
        raise ConfigurationError(
            "TELEPHONY_ODOO_PROJECTION_ENABLED must be explicitly true"
        )
    if not settings.odoo_delivery_enabled:
        raise ConfigurationError(
            "call-event projection requires the existing ODOO_WRITE and "
            "EXTERNAL_DELIVERY_ENABLED gates"
        )
    if not settings.database_url:
        raise ConfigurationError("DATABASE_URL is required for call-event projection")
    if not settings.odoo_base_url:
        raise ConfigurationError("ODOO_19_BASE_URL is required for call-event projection")

    poll_seconds = _poll_seconds()
    pool = await asyncpg.create_pool(
        settings.database_url,
        min_size=1,
        max_size=6,
        command_timeout=max(5, settings.odoo_timeout_seconds),
    )
    client = httpx.AsyncClient(
        timeout=httpx.Timeout(settings.odoo_timeout_seconds),
        follow_redirects=False,
        limits=httpx.Limits(max_connections=8, max_keepalive_connections=4),
    )
    try:
        projection_store = PostgresTelephonyProjectionStore(pool)
        outbox_store = TelephonyOutboxStore(pool)
        dispatcher = OdooCallEventDispatcher(
            client=client,
            base_url=settings.odoo_base_url,
            default_secret=settings.odoo_default_hmac_secret,
            tenant_secrets=settings.odoo_tenant_hmac_secrets,
        )
        outbox_worker = OutboxWorker(
            outbox_store,
            {ODOO_CALL_EVENT_DESTINATION: dispatcher},
            poll_seconds=poll_seconds,
            lease_seconds=60,
            handler_timeout_seconds=min(45, settings.odoo_timeout_seconds + 5),
        )
        log.info(
            "starting isolated VICIdial-to-Odoo call-event projection worker"
        )
        async with asyncio.TaskGroup() as group:
            group.create_task(_project_forever(projection_store, poll_seconds))
            group.create_task(outbox_worker.run_forever())
    finally:
        await client.aclose()
        await pool.close()


def main() -> None:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    asyncio.run(run())


if __name__ == "__main__":
    main()
