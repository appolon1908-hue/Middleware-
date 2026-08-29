#!/usr/bin/env python3
"""Run a no-effect CP-ODOO automation control-plane smoke test."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from middleware_automation import AutomationService


def main() -> int:
    service = AutomationService()
    service.seed_job(
        job_id="smoke-cp-odoo",
        tenant_id="staging-tenant",
        actor_id="staging-operator",
        workflow_key="CP-ODOO-CRM-STATE-SYNC",
        workflow_version="1",
        delivery_token="smoke-delivery-token",
        workflow_family="crm",
    )
    claim = service.claim_job(
        {
            "job_id": "smoke-cp-odoo",
            "delivery_token": "smoke-delivery-token",
            "workflow_key": "CP-ODOO-CRM-STATE-SYNC",
            "workflow_version": "1",
            "execution_id": "smoke-execution",
        }
    )
    service.heartbeat_job(
        "smoke-cp-odoo",
        {"lease_token": claim["lease_token"], "execution_id": "smoke-execution"},
    )
    service.record_step(
        "smoke-cp-odoo",
        {
            "lease_token": claim["lease_token"],
            "execution_id": "smoke-execution",
            "step_key": "odoo-state-sync",
            "status": "STARTED",
        },
    )
    command = service.submit_command(
        {
            "job_id": "smoke-cp-odoo",
            "lease_token": claim["lease_token"],
            "execution_id": "smoke-execution",
            "workflow_key": "CP-ODOO-CRM-STATE-SYNC",
            "workflow_version": "1",
            "step_key": "odoo-state-sync",
            "command_type": "crm.odoo.state-sync",
            "dry_run": True,
            "payload": {"lead_id": "staging-lead", "target_state": "qualified"},
        },
        "smoke-cp-odoo:smoke-execution:odoo-state-sync",
    )
    completed = service.complete_job(
        "smoke-cp-odoo",
        {
            "lease_token": claim["lease_token"],
            "execution_id": "smoke-execution",
            "result": {
                "command_id": command["command_id"],
                "odoo_state": "DRY_RUN_VERIFIED",
            },
        },
    )
    result = {
        "SMOKE_CP_ODOO": "PASS",
        "job_state": completed["state"],
        "command_state": command["state"],
        "adapter_status": command["adapter_result"]["status"],
        "unexpected_dlq": len(service.dead_letters),
    }
    print(json.dumps(result, sort_keys=True))
    return 0 if result["unexpected_dlq"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
