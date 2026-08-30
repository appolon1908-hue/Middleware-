#!/usr/bin/env python3
"""Certify route registration and fail-closed unauthenticated behavior."""

from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request


COMMAND_PATH = "/v1/commands"
OPERATION_TEMPLATE = "/v1/operations/{command_id}"
OPERATION_PROBE = "/v1/operations/00000000-0000-0000-0000-000000000000"
VICIDIAL_PATH = "/api/v1/vicidial/events"
OPERATIONS_DASHBOARD_PATHS = (
    "/v1/operations-dashboard/overview",
    "/v1/operations-dashboard/auth-gateway",
    "/v1/operations-dashboard/routes",
    "/v1/operations-dashboard/providers",
    "/v1/operations-dashboard/messages/lifecycle",
    "/v1/operations-dashboard/webhooks",
    "/v1/operations-dashboard/tenants/{tenant_id}",
    "/v1/operations-dashboard/queues",
    "/v1/operations-dashboard/release-gates",
    "/v1/operations-dashboard/canaries",
)


def request(
    base: str,
    method: str,
    path: str,
    body: dict | None = None,
    headers: dict | None = None,
) -> tuple[int, dict]:
    encoded = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        base.rstrip("/") + path,
        data=encoded,
        headers={"Content-Type": "application/json", **(headers or {})},
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode())


def assert_fail_closed(status_code: int, response_body: dict) -> None:
    assert status_code in {401, 403}
    assert response_body.get("error", {}).get("code") in {
        "authentication_failed",
        "authorization_denied",
    }
    assert response_body != {"detail": "Not Found"}


def certify(base: str) -> None:
    status, openapi = request(base, "GET", "/openapi.json")
    assert status == 200
    paths = openapi["paths"]
    assert "post" in paths[COMMAND_PATH]
    assert "get" in paths[OPERATION_TEMPLATE]
    assert "post" in paths[VICIDIAL_PATH]
    assert "/v1/operations" not in paths
    assert "/v1/integrations/n8n/operations" not in paths
    for path in OPERATIONS_DASHBOARD_PATHS:
        assert "get" in paths[path]

    command = {
        "command_id": "00000000-0000-4000-8000-000000000001",
        "command_type": "crm.lead.create.v1",
        "command_version": "1.0",
        "target": "odoo-19",
        "tenant_id": "tenant-certification",
        "requested_by": "n8n-service-subject",
        "correlation_id": "route-certification-request",
        "idempotency_key": "route-certification-idempotency",
        "capability": "ODOO_WRITE",
        "payload": {"name": "route certification"},
    }
    command_headers = {
        "X-Tenant-ID": command["tenant_id"],
        "X-Correlation-ID": command["correlation_id"],
        "Idempotency-Key": command["idempotency_key"],
    }
    submit_status, submit_body = request(
        base,
        "POST",
        COMMAND_PATH,
        command,
        command_headers,
    )
    read_status, read_body = request(
        base,
        "GET",
        OPERATION_PROBE,
        headers={"X-Tenant-ID": command["tenant_id"]},
    )
    dashboard_status, dashboard_body = request(
        base,
        "GET",
        "/v1/operations-dashboard/overview",
        headers={
            "X-Tenant-ID": command["tenant_id"],
            "X-Correlation-ID": command["correlation_id"],
        },
    )
    for status_code, response_body in (
        (submit_status, submit_body),
        (read_status, read_body),
        (dashboard_status, dashboard_body),
    ):
        assert_fail_closed(status_code, response_body)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    args = parser.parse_args()
    certify(args.base_url)
    print("PRODUCTION_ROUTE_CONTRACT=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
