#!/usr/bin/env python3
from __future__ import annotations

import asyncio

import asyncpg

from app.config import ConfigurationError, Settings
from app.commands import TEMPORAL_COMMAND_DESTINATION
from app.nats_transport import NatsJetStreamPublisher
from app.storage import NATS_JETSTREAM_DESTINATION, PostgresOutboxStore
from app.temporal_runtime import connect_temporal
from app.temporal_transport import TemporalCommandDispatcher
from app.worker import OutboxWorker


async def main() -> None:
    settings = Settings.from_env()
    temporal_enabled = settings.temporal_worker_mode != "disabled"
    if not settings.outbox_dispatch_enabled and not temporal_enabled:
        raise ConfigurationError(
            "both JetStream and Temporal outbox dispatch are intentionally disabled"
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
        handlers = {}
        if settings.outbox_dispatch_enabled:
            publisher = await NatsJetStreamPublisher.connect(settings)
            handlers[NATS_JETSTREAM_DESTINATION] = publisher.publish
        if temporal_enabled:
            temporal_client = await connect_temporal(settings)
            temporal_dispatcher = TemporalCommandDispatcher(
                temporal_client,
                settings.temporal_task_queue,
            )
            handlers[TEMPORAL_COMMAND_DESTINATION] = temporal_dispatcher.dispatch
        worker = OutboxWorker(
            PostgresOutboxStore(pool),
            handlers,
        )
        await worker.run_forever()
    finally:
        if publisher is not None:
            await publisher.close()
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
