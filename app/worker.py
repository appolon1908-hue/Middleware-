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
    not use this exception; they remain quarantined for reconciliation instead.
    """


class OutboxWorker:
    """Generic bounded lease/retry/reconciliation worker.

    No provider handlers are registered on intake-runtime-v1. Immediately before
    any future provider handler is invoked, the claimed row is durably moved into
    the reconciliation-required state and its active worker lease is refreshed for
    a full lease window. That excludes the row from automatic claims and ensures
    the configured handler timeout remains strictly inside the refreshed lease.

    A normal handler return lets the owning worker resolve that active dispatch as
    complete. An explicit KnownSafeRetryError lets the owning worker resolve it as
    retry. Timeout and generic exceptions leave the precommitted quarantine and
    lease in place until lease expiry, after which audited manual reconciliation
    may proceed. Provider dispatch remains disabled by Settings on this branch.
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

        # This final pre-provider transaction refreshes the lease from database
        # time. If it fails, the exception propagates and provider code is never run.
        await self.store.quarantine_unknown_outcome(
            record.id,
            worker_id=self.worker_id,
            error=(
                "provider dispatch reserved before handler invocation; external outcome "
                "must be explicitly confirmed before automatic release"
            ),
            lease_seconds=self.lease_seconds,
        )

        try:
            await asyncio.wait_for(
                handler(record),
                timeout=self.handler_timeout_seconds,
            )
        except TimeoutError:
            log.error(
                "outbox handler timed out; active reconciliation quarantine retained",
                extra={"outbox_id": record.id},
            )
        except KnownSafeRetryError as exc:
            log.warning(
                "outbox handler certified failure as safe to retry",
                extra={"outbox_id": record.id},
            )
            await self.store.resolve_reconciliation(
                record.id,
                operator_id=f"worker:{self.worker_id}",
                action="retry",
                reason=f"handler certified known-safe retry: {exc}",
                max_attempts=self.max_attempts,
                worker_id=self.worker_id,
            )
        except Exception:
            log.exception(
                "outbox handler raised; active reconciliation quarantine retained",
                extra={"outbox_id": record.id},
            )
        else:
            await self.store.resolve_reconciliation(
                record.id,
                operator_id=f"worker:{self.worker_id}",
                action="complete",
                reason="handler returned successfully and confirmed delivery outcome",
                max_attempts=self.max_attempts,
                worker_id=self.worker_id,
            )
        return True

    async def run_forever(self) -> None:
        while True:
            processed = await self.run_once()
            if not processed:
                await asyncio.sleep(self.poll_seconds)
