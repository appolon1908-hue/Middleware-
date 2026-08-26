from __future__ import annotations

import asyncio
import logging
import os
import socket
import uuid
from collections.abc import Awaitable, Callable

from .storage import OutboxRecord, PostgresOutboxStore


Handler = Callable[[OutboxRecord], Awaitable[None]]
log = logging.getLogger(__name__)


class OutboxWorker:
    """Generic lease/retry/DLQ worker.

    No provider handlers are registered on intake-runtime-v1. The executable
    refuses to start while OUTBOX_DISPATCH_ENABLED=false, so this code cannot
    cause external delivery on the current branch.
    """

    def __init__(
        self,
        store: PostgresOutboxStore,
        handlers: dict[str, Handler],
        *,
        poll_seconds: float = 1.0,
    ) -> None:
        self.store = store
        self.handlers = handlers
        self.poll_seconds = poll_seconds
        self.worker_id = f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"

    async def run_forever(self) -> None:
        while True:
            record = await self.store.claim(worker_id=self.worker_id)
            if record is None:
                await asyncio.sleep(self.poll_seconds)
                continue
            handler = self.handlers.get(record.destination)
            if handler is None:
                await self.store.fail(
                    record.id,
                    worker_id=self.worker_id,
                    error=f"no handler registered for destination {record.destination}",
                )
                continue
            try:
                await handler(record)
            except Exception as exc:
                log.exception("outbox delivery failed", extra={"outbox_id": record.id})
                await self.store.fail(
                    record.id,
                    worker_id=self.worker_id,
                    error=str(exc),
                )
            else:
                await self.store.complete(record.id, worker_id=self.worker_id)
