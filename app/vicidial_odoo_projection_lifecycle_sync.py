"""Keep telephony_call_lifecycle in sync with projected VICIdial call events.

This module is a side effect of the existing NATS -> Odoo call-event
dispatcher (see workers/run_vicidial_odoo_projection.py): every event that
already reaches the dispatcher for delivery to Odoo is also, best-effort,
applied here so that GET /platform/v1/calls (app/api/v1/calls.py) reflects
live call state instead of staying frozen at whatever
POST /v1/telephony/calls/originate wrote at origination.

This intentionally does NOT populate telephony_call_lifecycle_event -- that
child table's integration_event_id column is a NOT NULL, UNIQUE foreign key
into the integration_event table, which is populated by a different
ingestion path (POST /api/v1/events/vicidial), not by this NATS-sourced
envelope. Writing that table correctly is that other path's job.

In addition to the coarse STARTED/CONNECTED/ENDED lifecycle_state, every
event that reaches here also records its raw event_type/timestamp in
last_event_type/last_event_at -- unconditionally, even for event types that
don't move the coarse state (e.g. call.held, call.transfer.started) -- so
GET /platform/v1/calls can surface the same finer-grained taxonomy Odoo's
own call_event_projection.py already tracks, without restructuring the
coarse enum every existing consumer of lifecycle_state depends on.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import TelephonyCallLifecycle
from app.vicidial_odoo_projection_models import OdooCallEvent

log = logging.getLogger("codestra.vicidial_odoo_projection.lifecycle_sync")

# Coarse, monotonic states the read-side table actually tracks. A call may
# only move forward through this ordering; a redelivered or out-of-order
# event that maps to an earlier or equal state than what's stored is a no-op
# for lifecycle_state (idempotent under JetStream at-least-once redelivery).
_STATE_RANK = {"STARTED": 1, "CONNECTED": 2, "ENDED": 3}

_STARTED_TYPES = frozenset({"call.created", "call.offered", "call.ringing"})
_CONNECTED_TYPES = frozenset(
    {"call.answered", "call.connected", "call.held", "call.resumed"}
)
_ENDED_TYPES = frozenset({"call.hangup", "call.completed", "call.failed", "call.missed"})
# Recognized by Odoo's call_event_projection.py taxonomy but not part of the
# coarse STARTED/CONNECTED/ENDED progression -- still worth recording in
# last_event_type/last_event_at for read-side visibility.
_NON_COARSE_TYPES = frozenset(
    {"call.transfer.started", "call.transfer.completed"}
)
_DISPOSITION_BY_TYPE = {
    "call.completed": "COMPLETED",
    "call.failed": "FAILED",
    "call.missed": "MISSED",
}


def _coarse_state(event_type: str) -> str | None:
    if event_type in _STARTED_TYPES:
        return "STARTED"
    if event_type in _CONNECTED_TYPES:
        return "CONNECTED"
    if event_type in _ENDED_TYPES:
        return "ENDED"
    # call.transfer.* don't move the coarse STARTED/CONNECTED/ENDED state
    # this table tracks (handled separately via _NON_COARSE_TYPES).
    return None


async def sync_call_lifecycle(session: AsyncSession, event: OdooCallEvent) -> None:
    """Best-effort, idempotent update of telephony_call_lifecycle.

    Never raises for "expected" conditions (no matching row, event type that
    doesn't move the coarse state) -- this is a side effect of Odoo
    delivery, not a condition that should affect message ack/nak/term
    decisions in the caller's redelivery state machine.
    """
    new_state = _coarse_state(event.event_type)
    if new_state is None and event.event_type not in _NON_COARSE_TYPES:
        return

    row = (
        await session.execute(
            select(TelephonyCallLifecycle).where(
                TelephonyCallLifecycle.correlation_id == event.correlation_id
            )
        )
    ).scalar_one_or_none()
    if row is None:
        log.info(
            "no telephony_call_lifecycle row for correlation_id=%s "
            "(event_type=%s) -- not originated via /calls/originate, skipping",
            event.correlation_id,
            event.event_type,
        )
        return

    row.last_event_type = event.event_type
    row.last_event_at = event.timestamp

    if new_state is None:
        # Non-coarse type (transfer.*): recorded above, no state transition.
        await session.commit()
        return

    if new_state == "STARTED" and row.started_at is None:
        row.started_at = event.timestamp
    elif new_state == "CONNECTED" and row.connected_at is None:
        row.connected_at = event.timestamp
    elif new_state == "ENDED" and row.ended_at is None:
        row.ended_at = event.timestamp
        if event.hangup_cause is not None:
            row.hangup_cause = event.hangup_cause
        disposition = _DISPOSITION_BY_TYPE.get(event.event_type)
        if disposition is not None:
            row.disposition = disposition

    if _STATE_RANK[new_state] > _STATE_RANK.get(row.lifecycle_state, 0):
        row.lifecycle_state = new_state

    await session.commit()
