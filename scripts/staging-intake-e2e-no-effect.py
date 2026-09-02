#!/usr/bin/env python3
"""No-effect staging certification for the unified intake edge path.

This script intentionally performs only read/validation requests and synthetic intake
requests whose downstream external effects must remain disabled by staging config.
It never enables any capability or changes server configuration.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid


def fail(message: str) -> None:
    print(f"FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def request(url: str, *, method: str = "GET", headers: dict[str, str] | None = None, body: dict | None = None) -> tuple[int, str]:
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            return response.status, response.read(8192).decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(8192).decode("utf-8", "replace")


def require_disabled(name: str) -> None:
    value = os.environ.get(name, "").strip().lower()
    if value not in {"false", "0", "disabled", "off"}:
        fail(f"{name} must be explicitly disabled, got {value!r}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True, help="Staging Caddy public API base, e.g. https://staging-api.example")
    parser.add_argument("--tenant", required=True)
    parser.add_argument("--token-env", default="STAGING_SDK_INTAKE_TOKEN")
    args = parser.parse_args()

    for flag in (
        "LIVE_WRITES",
        "ODOO_WRITE",
        "N8N_DELIVERY_ENABLED",
        "LIVE_SMS_DELIVERY",
        "LIVE_EMAIL_DELIVERY",
        "LIVE_PSTN_DIALING",
    ):
        require_disabled(flag)

    token = os.environ.get(args.token_env, "").strip()
    if not token:
        fail(f"missing staging bearer token in {args.token_env}")

    base = args.base_url.rstrip("/")
    correlation = f"stg-cert-{uuid.uuid4()}"
    idem = f"stg-lead-{uuid.uuid4()}"
    submitted_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    lead_url = f"{base}/v1/intake/leads"
    survey_url = f"{base}/v1/intake/surveys/responses"

    # Negative control: no token must be rejected by gateway/auth, never accepted.
    status, _ = request(
        lead_url,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Tenant-ID": args.tenant,
            "X-Correlation-ID": correlation,
            "Idempotency-Key": idem,
        },
        body={"tenantId": args.tenant, "siteId": "staging-cert", "source": "api", "submittedAt": submitted_at},
    )
    if status < 400:
        fail(f"unauthenticated lead request unexpectedly accepted with HTTP {status}")

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "X-Tenant-ID": args.tenant,
        "X-Correlation-ID": correlation,
        "Idempotency-Key": idem,
    }
    lead = {
        "tenantId": args.tenant,
        "siteId": "staging-cert",
        "source": "api",
        "submittedAt": submitted_at,
        "formId": "staging-cert-v1",
        "name": "Synthetic Staging Certification",
        "email": "staging-cert@example.invalid",
        "metadata": {"certification": "no-effect"},
    }

    status, first_body = request(lead_url, method="POST", headers=headers, body=lead)
    if status not in {200, 202}:
        fail(f"authenticated lead intake failed: HTTP {status}: {first_body[:500]}")

    status, retry_body = request(lead_url, method="POST", headers=headers, body=lead)
    if status != 200:
        fail(f"exact retry did not return duplicate semantics: HTTP {status}: {retry_body[:500]}")

    changed = dict(lead)
    changed["name"] = "Synthetic Staging Certification Changed"
    status, conflict_body = request(lead_url, method="POST", headers=headers, body=changed)
    if status != 409:
        fail(f"changed-payload idempotency reuse did not conflict: HTTP {status}: {conflict_body[:500]}")

    survey_headers = dict(headers)
    survey_headers["Idempotency-Key"] = f"stg-survey-{uuid.uuid4()}"
    survey_headers["X-Correlation-ID"] = f"stg-survey-{uuid.uuid4()}"
    survey = {
        "tenantId": args.tenant,
        "siteId": "staging-cert",
        "source": "api",
        "submittedAt": submitted_at,
        "surveyId": "staging-cert",
        "surveyVersion": "1.0.0",
        "surveyCategory": "custom",
        "anonymous": True,
        "answers": {"certification": "pass"},
        "metadata": {"certification": "no-effect"},
    }
    status, survey_body = request(survey_url, method="POST", headers=survey_headers, body=survey)
    if status not in {200, 202}:
        fail(f"anonymous survey intake failed: HTTP {status}: {survey_body[:500]}")

    print("STAGING_INTAKE_NO_EFFECT=PASS")
    print(f"correlation_id={correlation}")
    print("external_effects_expected=DISABLED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
