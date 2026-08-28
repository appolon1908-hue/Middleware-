from __future__ import annotations

from typing import Any
from uuid import UUID

from temporalio import activity
from temporalio.exceptions import ApplicationError

from .commands import CommandConflict, CommandNotFound, CommandState, PostgresCommandStore
from .temporal_workflows import (
    ActivityResult,
    CommandExecutionRequest,
    CommandTransitionRequest,
    DeadLetterReplayRequest,
    DelayedCallbackRequest,
    ProvisioningStepRequest,
    ReconciliationRequest,
)


class FailClosedWorkflowActivities:
    """Activity bindings used until a durable command/operation owns execution."""

    @staticmethod
    def _blocked(name: str) -> ApplicationError:
        return ApplicationError(
            f"{name} is not bound to the durable command ledger",
            non_retryable=True,
            type="CapabilityDisabled",
        )

    @activity.defn(name="reconcile_operation")
    async def reconcile_operation(self, request: ReconciliationRequest) -> Any:
        raise self._blocked("reconcile_operation")

    @activity.defn(name="dispatch_delayed_callback")
    async def dispatch_delayed_callback(self, request: DelayedCallbackRequest) -> Any:
        raise self._blocked("dispatch_delayed_callback")

    @activity.defn(name="provision_identity")
    async def provision_identity(self, request: ProvisioningStepRequest) -> Any:
        raise self._blocked("provision_identity")

    @activity.defn(name="provision_product")
    async def provision_product(self, request: ProvisioningStepRequest) -> Any:
        raise self._blocked("provision_product")

    @activity.defn(name="verify_provisioning")
    async def verify_provisioning(self, request: ProvisioningStepRequest) -> Any:
        raise self._blocked("verify_provisioning")

    @activity.defn(name="compensate_provisioning")
    async def compensate_provisioning(self, request: ProvisioningStepRequest) -> Any:
        raise self._blocked("compensate_provisioning")

    @activity.defn(name="replay_dead_letter")
    async def replay_dead_letter(self, request: DeadLetterReplayRequest) -> Any:
        raise self._blocked("replay_dead_letter")

    def registered(self) -> tuple[Any, ...]:
        return (
            self.reconcile_operation,
            self.dispatch_delayed_callback,
            self.provision_identity,
            self.provision_product,
            self.verify_provisioning,
            self.compensate_provisioning,
            self.replay_dead_letter,
        )


class CommandLedgerWorkflowActivities:
    def __init__(self, store: PostgresCommandStore) -> None:
        self.store = store

    @activity.defn(name="record_command_transition")
    async def record_command_transition(
        self,
        request: CommandTransitionRequest,
    ) -> ActivityResult:
        try:
            operation = await self.store.transition(
                request.tenant_id,
                UUID(request.command_id),
                new_state=request.new_state,  # type: ignore[arg-type]
                actor_id=request.actor_id,
                reason=request.reason,
                provider_operation_id=request.provider_operation_id,
            )
        except (ValueError, CommandConflict, CommandNotFound) as exc:
            raise ApplicationError(
                str(exc),
                non_retryable=True,
                type="CommandTransitionRejected",
            ) from exc
        return ActivityResult(
            status=operation.state,
            detail=request.reason,
            provider_operation_id=operation.provider_operation_id,
        )

    @activity.defn(name="execute_command")
    async def execute_command(
        self,
        request: CommandExecutionRequest,
    ) -> ActivityResult:
        raise ApplicationError(
            "no production provider adapter is activated for this command",
            non_retryable=True,
            type="CapabilityDisabled",
        )

    @activity.defn(name="readback_command")
    async def readback_command(
        self,
        request: CommandExecutionRequest,
    ) -> ActivityResult:
        raise ApplicationError(
            "no provider read-back adapter is activated for this command",
            non_retryable=True,
            type="CapabilityDisabled",
        )

    def registered(self) -> tuple[Any, ...]:
        return (
            self.record_command_transition,
            self.execute_command,
            self.readback_command,
        )
