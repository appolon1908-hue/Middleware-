#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
from contextlib import suppress
from typing import Any

import httpx
from pydantic import ValidationError

from app.models import EventEnvelope
from app.vicidial_odoo_projection import (
    DeterministicRejection,
    KnownNotDelivered,
    LIFECYCLE_EVENT_MAP,
    OdooCallEventDispatcher,
    OutcomeUnknown,
    ProjectionConflict,
    ProjectionError,
    ProjectionSettings,
    ProjectionState,
    project_envelope,
)
from app.vicidial_odoo_projection_authority import (
    validate_projection_source_locks,
)

log = logging.getLogger("codestra.vicidial_odoo_projection")


async def progress_heartbeat(message: Any, *, interval_seconds: float = 10.0) -> None:
    """Keep a JetStream delivery alive while POST and read-back may span its ack wait."""
    while True:
        await asyncio.sleep(interval_seconds)
        try:
            await message.in_progress()
        except Exception as exc:  # the broker will redeliver if progress cannot be recorded
            log.warning("call-event progress heartbeat failed: %s", exc)
            return


async def handle_message(
    message: Any,
    *,
    settings: ProjectionSettings,
    state: ProjectionState,
    dispatcher: OdooCallEventDispatcher,
) -> None:
    heartbeat = asyncio.create_task(progress_heartbeat(message))
    try:
        try:
            envelope = EventEnvelope.model_validate_json(message.data)
        except ValidationError as exc:
            log.error("terminating malformed canonical event: %s", exc)
            await message.term()
            return
        if envelope.event_type not in LIFECYCLE_EVENT_MAP:
            await message.ack()
            return
        try:
            event = project_envelope(envelope, synthetic_only=settings.synthetic_only)
            current = state.register(event)
        except (ProjectionError, ProjectionConflict) as exc:
            log.error("terminating rejected lifecycle event %s: %s", envelope.event_id, exc)
            await message.term()
            return
        if current == "delivered":
            await message.ack()
            return
        if current == "failed":
            await message.term()
            return
        try:
            if current == "reconciliation_required":
                await dispatcher.reconcile(event, reason="durable prior write attempt")
            else:
                # Persist the uncertainty boundary before any network I/O. A process
                # exit after this commit, whether before or after Odoo receives the
                # POST, therefore redelivers into signed read-back rather than a
                # blind second submission. A confirmed 404 moves the row to
                # retryable and only a later delivery may open another write attempt.
                state.transition(
                    event.event_id,
                    "reconciliation_required",
                    "write attempt opened before Odoo submission",
                )
                await dispatcher.submit(event)
        except KnownNotDelivered as exc:
            state.transition(event.event_id, "retryable", str(exc))
            await message.nak(delay=5)
        except OutcomeUnknown as exc:
            state.transition(event.event_id, "reconciliation_required", str(exc))
            # Redelivery performs read-back only; it cannot blindly resubmit.
            await message.nak(delay=15)
        except DeterministicRejection as exc:
            state.transition(event.event_id, "failed", str(exc))
            await message.term()
        else:
            state.transition(event.event_id, "delivered")
            await message.ack()
    finally:
        heartbeat.cancel()
        with suppress(asyncio.CancelledError):
            await heartbeat


async def process_batch(
    messages: list[Any],
    *,
    settings: ProjectionSettings,
    state: ProjectionState,
    dispatcher: OdooCallEventDispatcher,
) -> None:
    """Start every fetched message immediately so none expires behind the batch."""
    results = await asyncio.gather(
        *(
            handle_message(
                message,
                settings=settings,
                state=state,
                dispatcher=dispatcher,
            )
            for message in messages
        ),
        return_exceptions=True,
    )
    for result in results:
        if isinstance(result, BaseException):
            log.error(
                "call-event delivery failed outside the classified path",
                exc_info=(type(result), result, result.__traceback__),
            )


async def run() -> None:
    settings = ProjectionSettings.from_env()
    if not settings.enabled:
        raise SystemExit("VICIDIAL_ODOO_PROJECTION_ENABLED is false")
    # Source locks are evaluated only for an enabled worker. They bind the
    # runtime to the exact reviewed Keycloak, Odoo, and VICIdial commits and
    # fail before any NATS connection, durable state mutation, or Odoo request.
    validate_projection_source_locks(os.environ)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    import nats
    from nats.errors import TimeoutError as NatsTimeoutError

    options: dict[str, Any] = {}
    if settings.nats_credentials_file is not None:
        options["user_credentials"] = str(settings.nats_credentials_file)
    client = await nats.connect(
        servers=[settings.nats_url],
        connect_timeout=5,
        max_reconnect_attempts=-1,
        reconnect_time_wait=1,
        name="codestra-vicidial-odoo-projection",
        **options,
    )
    jetstream = client.jetstream()
    subscription = await jetstream.pull_subscribe(
        settings.subject,
        durable=settings.durable_consumer,
        stream=settings.nats_stream,
    )
    state = ProjectionState(settings.state_path)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:
            pass
    async with httpx.AsyncClient(timeout=httpx.Timeout(20)) as http:
        dispatcher = OdooCallEventDispatcher(
            client=http,
            base_url=settings.odoo_base_url or "",
            tenant_secrets=settings.tenant_secrets,
            default_secret=settings.default_secret,
        )
        try:
            while not stop.is_set():
                try:
                    messages = await subscription.fetch(
                        settings.batch_size,
                        timeout=settings.fetch_timeout_seconds,
                    )
                except (NatsTimeoutError, TimeoutError, asyncio.TimeoutError):
                    continue
                await process_batch(
                    list(messages),
                    settings=settings,
                    state=state,
                    dispatcher=dispatcher,
                )
        finally:
            await client.drain()


if __name__ == "__main__":
    asyncio.run(run())
