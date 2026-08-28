from __future__ import annotations

import os
from typing import Any

import pytest
from temporalio import activity
from temporalio.client import WorkflowHandle
from temporalio.exceptions import ApplicationError
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from app.temporal_workflows import (
    ActivityResult,
    DeadLetterApproval,
    DeadLetterRecoveryRequest,
    DeadLetterRecoveryWorkflow,
    DeadLetterReplayRequest,
    DelayedCallbackRequest,
    DelayedCallbackWorkflow,
    ProvisioningRequest,
    ProvisioningStepRequest,
    ProvisioningWorkflow,
    ReconciliationRequest,
    ReconciliationWorkflow,
    WORKFLOWS,
)


RUN = os.getenv("TEMPORAL_INTEGRATION_TESTS") == "1"
TASK_QUEUE = "codestra-test-critical"

pytestmark = pytest.mark.skipif(
    not RUN,
    reason="set TEMPORAL_INTEGRATION_TESTS=1 for the Temporal test server",
)


class DeterministicActivities:
    def __init__(self) -> None:
        self.reconciliation_attempts = 0
        self.callbacks: list[str] = []
        self.provisioned: list[str] = []
        self.compensations: list[str] = []
        self.replays: list[str] = []

    @activity.defn(name="reconcile_operation")
    async def reconcile_operation(
        self,
        request: ReconciliationRequest,
    ) -> ActivityResult:
        self.reconciliation_attempts += 1
        if self.reconciliation_attempts < 3:
            raise ApplicationError("transient read-back failure")
        return ActivityResult("completed", "provider read-back matched")

    @activity.defn(name="dispatch_delayed_callback")
    async def dispatch_delayed_callback(
        self,
        request: DelayedCallbackRequest,
    ) -> ActivityResult:
        self.callbacks.append(request.callback_id)
        return ActivityResult("completed", "callback dispatched")

    @activity.defn(name="provision_identity")
    async def provision_identity(
        self,
        request: ProvisioningStepRequest,
    ) -> ActivityResult:
        self.provisioned.append("identity")
        return ActivityResult("completed", "identity provisioned")

    @activity.defn(name="provision_product")
    async def provision_product(
        self,
        request: ProvisioningStepRequest,
    ) -> ActivityResult:
        assert request.product is not None
        if request.product == "email":
            raise ApplicationError("email provisioning rejected", non_retryable=True)
        self.provisioned.append(request.product)
        return ActivityResult("completed", f"{request.product} provisioned")

    @activity.defn(name="verify_provisioning")
    async def verify_provisioning(
        self,
        request: ProvisioningStepRequest,
    ) -> ActivityResult:
        return ActivityResult("completed", "provisioning read-back matched")

    @activity.defn(name="compensate_provisioning")
    async def compensate_provisioning(
        self,
        request: ProvisioningStepRequest,
    ) -> ActivityResult:
        self.compensations.append(request.product or "identity")
        return ActivityResult("completed", "provisioning compensated")

    @activity.defn(name="replay_dead_letter")
    async def replay_dead_letter(
        self,
        value: DeadLetterReplayRequest,
    ) -> ActivityResult:
        self.replays.append(value.dead_letter_id)
        return ActivityResult(
            "completed",
            f"approved by {value.operator_id}",
        )

    def registered(self) -> list[Any]:
        return [
            self.reconcile_operation,
            self.dispatch_delayed_callback,
            self.provision_identity,
            self.provision_product,
            self.verify_provisioning,
            self.compensate_provisioning,
            self.replay_dead_letter,
        ]


@pytest.mark.asyncio
async def test_critical_workflows_retry_wait_compensate_and_require_approval() -> None:
    activities = DeterministicActivities()
    async with await WorkflowEnvironment.start_time_skipping() as environment:
        async with Worker(
            environment.client,
            task_queue=TASK_QUEUE,
            workflows=list(WORKFLOWS),
            activities=activities.registered(),
        ):
            reconciliation = await environment.client.execute_workflow(
                ReconciliationWorkflow.run,
                ReconciliationRequest("op-reconcile", "tenant-test", "read-back"),
                id="test-reconciliation",
                task_queue=TASK_QUEUE,
            )
            assert reconciliation.status == "completed"
            assert activities.reconciliation_attempts == 3

            callback = await environment.client.execute_workflow(
                DelayedCallbackWorkflow.run,
                DelayedCallbackRequest(
                    "op-callback",
                    "tenant-test",
                    "callback-1",
                    86_400,
                ),
                id="test-delayed-callback",
                task_queue=TASK_QUEUE,
            )
            assert callback.status == "completed"
            assert activities.callbacks == ["callback-1"]

            provisioning = await environment.client.execute_workflow(
                ProvisioningWorkflow.run,
                ProvisioningRequest(
                    "op-provision",
                    "tenant-test",
                    "principal-1",
                    ("identity-profile", "email"),
                ),
                id="test-provisioning",
                task_queue=TASK_QUEUE,
            )
            assert provisioning.status == "failed_compensated"
            assert activities.provisioned == ["identity", "identity-profile"]
            assert activities.compensations == ["identity-profile"]

            recovery: WorkflowHandle = await environment.client.start_workflow(
                DeadLetterRecoveryWorkflow.run,
                DeadLetterRecoveryRequest(
                    "op-recovery",
                    "tenant-test",
                    "dead-letter-1",
                ),
                id="test-dead-letter-recovery",
                task_queue=TASK_QUEUE,
            )
            assert await recovery.query(
                DeadLetterRecoveryWorkflow.approval_status
            ) == "awaiting_approval"
            await recovery.signal(
                DeadLetterRecoveryWorkflow.approve,
                DeadLetterApproval(
                    operator_id="operator-1",
                    reason="verified provider outage is resolved",
                    approved=True,
                ),
            )
            recovered = await recovery.result()
            assert recovered.status == "completed"
            assert activities.replays == ["dead-letter-1"]
