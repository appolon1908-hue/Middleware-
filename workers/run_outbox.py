#!/usr/bin/env python3
from __future__ import annotations

import asyncio

import asyncpg

from app.config import ConfigurationError, Settings
from app.nats_transport import NatsJetStreamPublisher
from app.storage import NATS_JETSTREAM_DESTINATION, PostgresOutboxStore
from app.worker import OutboxWorker


async def main() -> None:
    settings = Settings.from_env()
    if not settings.outbox_dispatch_enabled:
        raise ConfigurationError(
            "OUTBOX_DISPATCH_ENABLED=false; outbox worker is intentionally disabled"
        )
    if settings.database_url is None:
        raise ConfigurationError("DATABASE_URL is required for the outbox worker")

    pool = await asyncpg.create_pool(
        settings.database_url,
        min_size=1,
        max_size=8,
        command_timeout=10,
    )
    publisher: NatsJetStreamPublisher | None = None
    try:
        publisher = await NatsJetStreamPublisher.connect(settings)
        worker = OutboxWorker(
            PostgresOutboxStore(pool),
            {NATS_JETSTREAM_DESTINATION: publisher.publish},
        )
        await worker.run_forever()
    finally:
        if publisher is not None:
            await publisher.close()
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
