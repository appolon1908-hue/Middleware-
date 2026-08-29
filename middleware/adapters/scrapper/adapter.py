"""This adapter is called by Middleware only. No other system may call Scrapper directly."""

from __future__ import annotations

from typing import Any, Mapping

from ..base import BaseAdapter, EnvRef, ProviderError, ProviderRequest, ProviderResponse


class ScrapperAdapter(BaseAdapter):
    """Translate governed crawl commands onto the implemented Scrapper v2 job API."""

    ADAPTER_NAME = "scrapper"
    COMMANDS = frozenset({"dispatch_scrape_job", "cancel_job"})
    WEBHOOK_EVENTS = frozenset({"job.completed", "job.failed", "job.partial"})
    CAPABILITIES = {
        "url_scrape": True,
        "keyword_scrape": True,
        "domain_crawl": False,
        "result_webhook": True,
    }
    ENVIRONMENT_NAMES = (
        "SCRAPPER_BASE_URL",
        "SCRAPPER_API_KEY",
        "SCRAPPER_WEBHOOK_SECRET",
    )

    def _validate(self, command_type: str, payload: Mapping[str, Any]) -> None:
        if command_type == "dispatch_scrape_job":
            job_type = payload.get("job_type")
            if job_type not in {"url", "keyword"}:
                raise ProviderError(
                    "Scrapper job_type must be url or keyword; domain crawl is disabled",
                    code="unsupported_capability",
                )
            target = payload.get("target")
            if not isinstance(target, str) or not target.strip():
                raise ProviderError("Scrapper target is required", code="invalid_payload")
            depth = payload.get("depth", 1)
            if not isinstance(depth, int) or not 1 <= depth <= 10:
                raise ProviderError("Scrapper depth must be an integer from 1 to 10", code="invalid_payload")
        elif not payload.get("job_ref"):
            raise ProviderError("Scrapper job_ref is required for cancellation", code="invalid_payload")

    def _build_request(
        self,
        *,
        command_type: str,
        payload: Mapping[str, Any],
        idempotency_key: str,
        correlation_id: str,
        request_id: str,
    ) -> ProviderRequest:
        headers = {
            "Authorization": EnvRef("SCRAPPER_API_KEY"),
            "X-Tenant-ID": str(payload.get("tenant_id") or ""),
            "Idempotency-Key": idempotency_key,
            "X-Correlation-ID": correlation_id,
            "X-Request-ID": request_id,
        }
        if command_type == "dispatch_scrape_job":
            target = str(payload["target"])
            # The implemented API requires seedUrls. Keyword jobs remain a
            # prepared contract until a discovery provider is explicitly enabled.
            if payload["job_type"] == "keyword":
                raise ProviderError(
                    "keyword discovery has no approved provider binding in the current Scrapper API",
                    code="unsupported_capability",
                )
            body = {
                "seedUrls": [target],
                "maxDepth": payload.get("depth", 1),
            }
            return ProviderRequest(method="POST", path="/api/v2/jobs", body=body, headers=headers)
        return ProviderRequest(
            method="POST",
            path=f"/api/v2/jobs/{payload['job_ref']}/cancel",
            headers=headers,
        )

    def _readback_matches(
        self,
        command_type: str,
        payload: Mapping[str, Any],
        write: ProviderResponse,
        readback: ProviderResponse,
    ) -> bool:
        del payload, write
        status = readback.status.strip().lower()
        if command_type == "dispatch_scrape_job":
            # Read-back verifies the durable job exists; it need not have completed.
            return status in {"pending", "queued", "running", "completed"}
        return status in {"cancel_requested", "cancelled"}
