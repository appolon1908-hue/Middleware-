#!/usr/bin/env python3
from __future__ import annotations

import asyncio
from datetime import timedelta

from temporalio.worker import Worker

from app.config import ConfigurationError, Settings
from app.temporal_activities import FailClosedWorkflowActivities
from app.temporal_runtime import connect_temporal
from app.temporal_workflows import WORKFLOWS


async def main() -> None:
    settings = Settings.from_env()
    if settings.temporal_worker_mode == "disabled":
        raise ConfigurationError(
            "TEMPORAL_WORKER_MODE=disabled; workflow worker is intentionally disabled"
        )
    client = await connect_temporal(settings)
    activities = FailClosedWorkflowActivities()
    worker = Worker(
        client,
        task_queue=settings.temporal_task_queue,
        workflows=list(WORKFLOWS),
        activities=list(activities.registered()),
        graceful_shutdown_timeout=timedelta(seconds=30),
    )
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
