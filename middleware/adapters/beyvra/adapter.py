"""This adapter is called by Middleware only. No other system may call Beyvra directly."""

from __future__ import annotations

from typing import Any, Mapping

from ..base import BaseAdapter, EnvRef, ProviderError, ProviderRequest, ProviderResponse


class BeyvraAdapter(BaseAdapter):
    """Publish allowlisted non-financial operations to Beyvra through its private API."""

    ADAPTER_NAME = "beyvra"
    COMMANDS = frozenset(
        {
            "create_onboarding_case",
            "request_compliance_reminder",
            "create_support_escalation",
            "create_report_request",
            "request_notification",
            "create_security_alert",
            "reconcile_webhook_delivery",
            "notify_call_completed",
            "notify_contact_enriched",
            "notify_scrape_completed",
        }
    )
    WEBHOOK_EVENTS = frozenset({"operation.completed", "operation.failed", "operation.reconciled"})
    CAPABILITIES = {
        "nonfinancial_operations": True,
        "notifications": True,
        "webhook_reconciliation": True,
        "financial_write": False,
        "trade_execution": False,
        "wallet_write": False,
    }
    ENVIRONMENT_NAMES = (
        "BEYVRA_BASE_URL",
        "BEYVRA_CLIENT_ID",
        "BEYVRA_CLIENT_SECRET",
        "BEYVRA_WEBHOOK_SECRET",
    )

    _PATHS = {
        "create_onboarding_case": "/v1/automation/onboarding-cases",
        "create_support_escalation": "/v1/automation/support-escalations",
        "create_report_request": "/v1/automation/report-requests",
        "request_notification": "/v1/automation/notifications",
        "create_security_alert": "/v1/automation/security-alerts",
        "reconcile_webhook_delivery": "/v1/automation/webhook-reconciliation",
        "notify_call_completed": "/v1/automation/notifications",
        "notify_contact_enriched": "/v1/automation/notifications",
        "notify_scrape_completed": "/v1/automation/notifications",
    }

    def _validate(self, command_type: str, payload: Mapping[str, Any]) -> None:
        if command_type == "request_compliance_reminder" and not payload.get("task_id"):
            raise ProviderError("Beyvra compliance task_id is required", code="invalid_payload")
        if command_type.startswith("notify_") and not payload.get("contact_id"):
            raise ProviderError("Beyvra notification contact_id is required", code="invalid_payload")
        forbidden = {
            "order_id",
            "trade_id",
            "wallet_id",
            "withdrawal_id",
            "deposit_id",
            "transfer_id",
            "payment_method",
        }
        if forbidden.intersection(payload):
            raise ProviderError(
                "Beyvra financial/trading fields are prohibited on the automation adapter",
                code="financial_boundary_violation",
            )

    def _build_request(
        self,
        *,
        command_type: str,
        payload: Mapping[str, Any],
        idempotency_key: str,
        correlation_id: str,
        request_id: str,
    ) -> ProviderRequest:
        if command_type == "request_compliance_reminder":
            path = f"/v1/automation/compliance-tasks/{payload['task_id']}/remind"
            body = {key: value for key, value in payload.items() if key != "task_id"}
        else:
            path = self._PATHS[command_type]
            body = dict(payload)
        if command_type.startswith("notify_"):
            body = {
                "event_type": command_type.removeprefix("notify_"),
                "payload": body,
            }
        return ProviderRequest(
            method="POST",
            path=path,
            body=body,
            headers={
                "Authorization": EnvRef("BEYVRA_CLIENT_SECRET"),
                "X-Codestra-Client-ID": EnvRef("BEYVRA_CLIENT_ID"),
                "Idempotency-Key": idempotency_key,
                "X-Correlation-ID": correlation_id,
                "X-Request-ID": request_id,
            },
        )

    def _readback_matches(
        self,
        command_type: str,
        payload: Mapping[str, Any],
        write: ProviderResponse,
        readback: ProviderResponse,
    ) -> bool:
        del command_type, payload, write
        return readback.status.strip().lower() in {
            "accepted",
            "queued",
            "processing",
            "completed",
            "reconciled",
        }
