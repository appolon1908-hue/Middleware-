from __future__ import annotations

import asyncio
import logging
import os
import socket
import uuid
from collections.abc import Awaitable, Callable

from .storage import DEFAULT_MAX_OUTBOX_ATTEMPTS, OutboxRecord, PostgresOutboxStore


Handler = Callable[[OutboxRecord], Awaitable[None]]
log = logging.getLogger(__name__)


class KnownSafeRetryError(RuntimeError):
    """Handler-provided proof that no external effect could have committed.

    Provider adapters may raise this only when they can establish that the
    operation is safe to retry, for example because dispatch was rejected before
    any provider write was attempted. Ambiguous transport/provider errors must
    not use this exception; they are quarantined for reconciliation instead.
    """


class OutboxWorker:
    """Generic bounded lease/retry/DLQ worker.

    No provider handlers are registered on intake-runtime-v1. Future handlers
    receive the authoritative idempotency key and are bounded to complete before
    the database lease expires. Once a provider handler starts, timeout and
    generic exceptions are treated as unknown external outcomes and quarantined
    for explicit reconciliation. Automatic retry is permitted only when a
    handler deliberately raises KnownSafeRetryError. Provider dispatch remains
    disabled by Settings.
    """

    def __init__(
        self,
        store: PostgresOutboxStore,
        handlers: dict[str, Handler],
        *,
        poll_seconds: float = 1.0,
        lease_seconds: float = 60.0,
        handler_timeout_seconds: float = 45.0,
        max_attempts: int = DEFAULT_MAX_OUTBOX_ATTEMPTS,
    ) -> None:
        if poll_seconds <= 0:
            raise ValueError("poll_seconds must be positive")
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        if handler_timeout_seconds <= 0 or handler_timeout_seconds >= lease_seconds:
            raise ValueError("handler timeout must be positive and strictly below lease")
        if max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        self.store = store
        self.handlers = handlers
        self.poll_seconds = poll_seconds
        self.lease_seconds = lease_seconds
        self.handler_timeout_seconds = handler_timeout_seconds
        self.max_attempts = max_attempts
        self.worker_id = f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"

    async def run_once(self) -> bool:
        record = await self.store.claim(
            worker_id=self.worker_id,
            lease_seconds=self.lease_seconds,
            max_attempts=self.max_attempts,
        )
        if record is None:
            return False
        handler = self.handlers.get(record.destination)
        if handler is None:
            await self.store.fail(
                record.id,
                worker_id=self.worker_id,
                error=f"no handler registered for destination {record.destination}",
                max_attempts=self.max_attempts,
            )
            return True
        try:
            await asyncio.wait_for(
                handler(record),
                timeout=self.handler_timeout_seconds,
            )
        except TimeoutError:
            await self.store.quarantine_unknown_outcome(
                record.id,
                worker_id=self.worker_id,
                error=(
                    "delivery handler exceeded bounded timeout before lease expiry; "
                    "external outcome is unknown and requires reconciliation"
                ),
            )
        except KnownSafeRetryError as exc:
            log.warning(
                "outbox delivery failed before any external effect; safe retry allowed",
                extra={"outbox_id": record.id},
            )
            await self.store.fail(
                record.id,
                worker_id=self.worker_id,
                error=str(exc),
                max_attempts=self.max_attempts,
            )
        except Exception as exc:
            log.exception(
                "outbox delivery raised after handler invocation; outcome requires reconciliation",
                extra={"outbox_id": record.id},
            )
            await self.store.quarantine_unknown_outcome(
                record.id,
                worker_id=self.worker_id,
                error=(
                    "delivery handler raised after invocation; external outcome is unknown "
                    f"and requires reconciliation: {type(exc).__name__}: {exc}"
                ),
            )
        else:
            await self.store.complete(record.id, worker_id=self.worker_id)
        return True

    async def run_forever(self) -> None:
        while True:
            processed = await self.run_once()
            if not processed:
                await asyncio.sleep(self.poll_seconds)
