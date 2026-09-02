from __future__ import annotations

import hashlib
from dataclasses import dataclass

from temporalio.client import Client
from temporalio.common import WorkflowIDConflictPolicy, WorkflowIDReusePolicy
from temporalio.exceptions import WorkflowAlreadyStartedError

from .commands import CommandEnvelope, TEMPORAL_COMMAND_DESTINATION
from .storage import OutboxRecord
from .temporal_workflows import CommandExecutionRequest, CommandExecutionWorkflow


class TemporalTransportError(RuntimeError):
    """Raised before workflow start when durable intent violates its contract."""


def command_workflow_id(tenant_id: str, command_id: str, idempotency_key: str) -> str:
    identity = hashlib.sha256(
        f"{tenant_id}\0{command_id}\0{idempotency_key}".encode("utf-8")
    ).hexdigest()
    return f"codestra-command-{identity}"


@dataclass(slots=True)
class TemporalCommandDispatcher:
    client: Client
    task_queue: str

    async def dispatch(self, record: OutboxRecord) -> None:
        if record.destination != TEMPORAL_COMMAND_DESTINATION:
            raise TemporalTransportError(
                "outbox row targets an unsupported Temporal destination"
            )
        try:
            command = CommandEnvelope.model_validate(record.payload)
        except Exception as exc:
            raise TemporalTransportError(
                "outbox command does not match the canonical command envelope"
            ) from exc
        if command.tenant_id != record.tenant_id:
            raise TemporalTransportError(
                "outbox tenant does not match the command envelope"
            )
        if command.command_type != record.event_type:
            raise TemporalTransportError(
                "outbox event type does not match the command type"
            )
        if command.idempotency_key != record.idempotency_key:
            raise TemporalTransportError(
                "outbox idempotency key does not match the command envelope"
            )

        request = CommandExecutionRequest(**command.model_dump(mode="json"))
        try:
            await self.client.start_workflow(
                CommandExecutionWorkflow.run,
                request,
                id=command_workflow_id(
                    command.tenant_id,
                    str(command.command_id),
                    command.idempotency_key,
                ),
                task_queue=self.task_queue,
                id_reuse_policy=WorkflowIDReusePolicy.REJECT_DUPLICATE,
                id_conflict_policy=WorkflowIDConflictPolicy.USE_EXISTING,
            )
        except WorkflowAlreadyStartedError:
            # A completed execution with the same deterministic workflow ID proves
            # that this durable intent was already handed to Temporal.
            return
