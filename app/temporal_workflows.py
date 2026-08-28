from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError, ApplicationError


@dataclass(frozen=True)
class ActivityResult:
    status: str
    detail: str


@dataclass(frozen=True)
class WorkflowOutcome:
    operation_id: str
    workflow_type: str
    status: str
    detail: str


@dataclass(frozen=True)
class ReconciliationRequest:
    operation_id: str
    tenant_id: str
    reason: str


@dataclass(frozen=True)
class DelayedCallbackRequest:
    operation_id: str
    tenant_id: str
    callback_id: str
    delay_seconds: int


@dataclass(frozen=True)
class ProvisioningRequest:
    operation_id: str
    tenant_id: str
    principal_id: str
    products: tuple[str, ...]


@dataclass(frozen=True)
class ProvisioningStepRequest:
    operation_id: str
    tenant_id: str
    principal_id: str
    product: str | None = None


@dataclass(frozen=True)
class DeadLetterRecoveryRequest:
    operation_id: str
    tenant_id: str
    dead_letter_id: str


@dataclass(frozen=True)
class DeadLetterApproval:
    operator_id: str
    reason: str
    approved: bool


@dataclass(frozen=True)
class DeadLetterReplayRequest:
    operation_id: str
    tenant_id: str
    dead_letter_id: str
    operator_id: str
    approval_reason: str


ACTIVITY_RETRY_POLICY = RetryPolicy(
    initial_interval=timedelta(seconds=1),
    backoff_coefficient=2.0,
    maximum_interval=timedelta(seconds=30),
    maximum_attempts=5,
)


def _require_identity(value: str, label: str) -> None:
    if not value or len(value) > 180:
        raise ApplicationError(
            f"{label} must contain 1-180 characters",
            non_retryable=True,
        )


async def _activity(name: str, request: object) -> ActivityResult:
    return await workflow.execute_activity(
        name,
        request,
        result_type=ActivityResult,
        start_to_close_timeout=timedelta(seconds=30),
        retry_policy=ACTIVITY_RETRY_POLICY,
    )


@workflow.defn(name="codestra.reconciliation.v1")
class ReconciliationWorkflow:
    @workflow.run
    async def run(self, request: ReconciliationRequest) -> WorkflowOutcome:
        _require_identity(request.operation_id, "operation_id")
        _require_identity(request.tenant_id, "tenant_id")
        result = await _activity("reconcile_operation", request)
        return WorkflowOutcome(
            operation_id=request.operation_id,
            workflow_type="reconciliation",
            status=result.status,
            detail=result.detail,
        )


@workflow.defn(name="codestra.delayed-callback.v1")
class DelayedCallbackWorkflow:
    @workflow.run
    async def run(self, request: DelayedCallbackRequest) -> WorkflowOutcome:
        _require_identity(request.operation_id, "operation_id")
        _require_identity(request.tenant_id, "tenant_id")
        _require_identity(request.callback_id, "callback_id")
        if request.delay_seconds < 0 or request.delay_seconds > 2_592_000:
            raise ApplicationError(
                "delay_seconds must be between 0 and 2592000",
                non_retryable=True,
            )
        await workflow.sleep(timedelta(seconds=request.delay_seconds))
        result = await _activity("dispatch_delayed_callback", request)
        return WorkflowOutcome(
            operation_id=request.operation_id,
            workflow_type="delayed_callback",
            status=result.status,
            detail=result.detail,
        )


@workflow.defn(name="codestra.provisioning.v1")
class ProvisioningWorkflow:
    @workflow.run
    async def run(self, request: ProvisioningRequest) -> WorkflowOutcome:
        _require_identity(request.operation_id, "operation_id")
        _require_identity(request.tenant_id, "tenant_id")
        _require_identity(request.principal_id, "principal_id")
        if not request.products or len(request.products) > 32:
            raise ApplicationError(
                "products must contain 1-32 entries",
                non_retryable=True,
            )

        base = ProvisioningStepRequest(
            operation_id=request.operation_id,
            tenant_id=request.tenant_id,
            principal_id=request.principal_id,
        )
        completed_products: list[str] = []
        try:
            await _activity("provision_identity", base)
            for product in request.products:
                _require_identity(product, "product")
                await _activity(
                    "provision_product",
                    ProvisioningStepRequest(
                        operation_id=request.operation_id,
                        tenant_id=request.tenant_id,
                        principal_id=request.principal_id,
                        product=product,
                    ),
                )
                completed_products.append(product)
            result = await _activity("verify_provisioning", base)
        except ActivityError as exc:
            await _activity(
                "compensate_provisioning",
                ProvisioningStepRequest(
                    operation_id=request.operation_id,
                    tenant_id=request.tenant_id,
                    principal_id=request.principal_id,
                    product=",".join(completed_products) or None,
                ),
            )
            return WorkflowOutcome(
                operation_id=request.operation_id,
                workflow_type="provisioning",
                status="failed_compensated",
                detail=str(exc),
            )

        return WorkflowOutcome(
            operation_id=request.operation_id,
            workflow_type="provisioning",
            status=result.status,
            detail=result.detail,
        )


@workflow.defn(name="codestra.dead-letter-recovery.v1")
class DeadLetterRecoveryWorkflow:
    def __init__(self) -> None:
        self._approval: DeadLetterApproval | None = None

    @workflow.signal
    def approve(self, approval: DeadLetterApproval) -> None:
        _require_identity(approval.operator_id, "operator_id")
        _require_identity(approval.reason, "reason")
        self._approval = approval

    @workflow.query
    def approval_status(self) -> str:
        if self._approval is None:
            return "awaiting_approval"
        return "approved" if self._approval.approved else "denied"

    @workflow.run
    async def run(self, request: DeadLetterRecoveryRequest) -> WorkflowOutcome:
        _require_identity(request.operation_id, "operation_id")
        _require_identity(request.tenant_id, "tenant_id")
        _require_identity(request.dead_letter_id, "dead_letter_id")
        await workflow.wait_condition(lambda: self._approval is not None)
        approval = self._approval
        if approval is None or not approval.approved:
            return WorkflowOutcome(
                operation_id=request.operation_id,
                workflow_type="dead_letter_recovery",
                status="denied",
                detail="operator denied replay",
            )
        result = await _activity(
            "replay_dead_letter",
            DeadLetterReplayRequest(
                operation_id=request.operation_id,
                tenant_id=request.tenant_id,
                dead_letter_id=request.dead_letter_id,
                operator_id=approval.operator_id,
                approval_reason=approval.reason,
            ),
        )
        return WorkflowOutcome(
            operation_id=request.operation_id,
            workflow_type="dead_letter_recovery",
            status=result.status,
            detail=result.detail,
        )


WORKFLOWS = (
    ReconciliationWorkflow,
    DelayedCallbackWorkflow,
    ProvisioningWorkflow,
    DeadLetterRecoveryWorkflow,
)
