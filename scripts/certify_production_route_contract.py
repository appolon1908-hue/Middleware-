#!/usr/bin/env python3
"""Certify route registration and fail-closed unauthenticated behavior."""

from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request


# These are intentionally the deprecated compatibility aliases. The canonical
# automation routes are /v2/automation/commands and /commands/{command_id}.
COMMAND_PATH = "/v1/integrations/n8n/commands"
OPERATION_TEMPLATE = "/v1/integrations/n8n/operations/{command_id}"
OPERATION_PROBE = "/v1/integrations/n8n/operations/00000000-0000-0000-0000-000000000000"
VICIDIAL_PATH = "/api/v1/vicidial/events"


def request(base: str, method: str, path: str, body: dict | None = None) -> tuple[int, dict]:
    encoded = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        base.rstrip("/") + path,
        data=encoded,
        headers={"Content-Type": "application/json"},
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode())


def certify(base: str) -> None:
    status, openapi = request(base, "GET", "/openapi.json")
    assert status == 200
    paths = openapi["paths"]
    assert "post" in paths[COMMAND_PATH]
    assert "get" in paths[OPERATION_TEMPLATE]
    assert "post" in paths[VICIDIAL_PATH]
    assert "/v1/integrations/n8n/operations" not in paths

    command = {
        "command_id": "00000000-0000-4000-8000-000000000001",
        "command_type": "crm.lead.upsert",
        "command_version": "1.0",
        "target": "odoo-19",
        "tenant_id": "tenant-certification",
        "requested_by": "n8n-service-subject",
        "correlation_id": "route-certification-request",
        "idempotency_key": "route-certification-idempotency",
        "capability": "ODOO_WRITE",
        "payload": {
            "lead_source": "synthetic-certification",
            "source_record_id": "route-certification-source",
            "initial_stage": "review_pending",
            "review_required": True,
            "allow_external_contact": False,
            "provenance": {
                "method": "submitted_by_person",
                "captured_by": "route-certification",
                "source_reference": "synthetic://route-certification",
                "legal_basis": "unknown_review_required",
                "content_digest": "a" * 64,
            },
            "consent": {
                "status": "unknown",
                "captured_at": "2026-08-30T16:00:00+00:00",
                "policy_version": "test-v1",
                "channels": {"email": False, "sms": False, "phone": False},
            },
            "lead": {
                "name": "route certification",
                "description": "Synthetic route test only.",
                "contact": {
                    "name": "Synthetic Contact",
                    "email": "synthetic@example.invalid",
                    "phone": "+18095550199",
                    "preferred_language": "en",
                },
                "company": {
                    "name": "Synthetic Company",
                    "domain": "example.invalid",
                    "industry": "Testing",
                },
                "campaign_code": None,
                "tags": [],
            },
        },
    }
    submit_status, submit_body = request(base, "POST", COMMAND_PATH, command)
    read_status, read_body = request(base, "GET", OPERATION_PROBE)
    for status_code, response_body in (
        (submit_status, submit_body),
        (read_status, read_body),
    ):
        assert status_code in {401, 403}
        assert response_body.get("error", {}).get("code") in {
            "authentication_failed",
            "authorization_denied",
        }
        assert response_body != {"detail": "Not Found"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    args = parser.parse_args()
    certify(args.base_url)
    print("PRODUCTION_ROUTE_CONTRACT=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
