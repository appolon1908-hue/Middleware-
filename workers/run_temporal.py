#!/usr/bin/env python3
from __future__ import annotations

import asyncio
from datetime import timedelta

from temporalio.worker import Worker

from app.config import ConfigurationError, Settings
from app.commands import PostgresCommandStore
from app.odoo_provider_adapter import OdooProviderAdapter
from app.temporal_activities import (
    CommandLedgerWorkflowActivities,
    FailClosedWorkflowActivities,
)
from app.temporal_runtime import connect_temporal
from app.temporal_workflows import WORKFLOWS


async def main() -> None:
    settings = Settings.from_env()
    if settings.temporal_worker_mode == "disabled":
        raise ConfigurationError(
            "TEMPORAL_WORKER_MODE=disabled; workflow worker is intentionally disabled"
        )
    if settings.database_url is None:
        raise ConfigurationError("DATABASE_URL is required for the Temporal worker")
    client = await connect_temporal(settings)
    command_store = await PostgresCommandStore.connect(settings.database_url)
    try:
        safe_activities = FailClosedWorkflowActivities()
        command_activities = CommandLedgerWorkflowActivities(
            command_store,
            OdooProviderAdapter(settings),
        )
        worker = Worker(
            client,
            task_queue=settings.temporal_task_queue,
            workflows=list(WORKFLOWS),
            activities=[
                *safe_activities.registered(),
                *command_activities.registered(),
            ],
            graceful_shutdown_timeout=timedelta(seconds=30),
        )
        await worker.run()
    finally:
        await command_store.close()


if __name__ == "__main__":
    asyncio.run(main())
