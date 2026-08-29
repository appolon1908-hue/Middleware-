from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from middleware_automation import AutomationError, AutomationService


class AutomationControlPlaneTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = AutomationService()
        self.job = self.service.seed_job(
            job_id="job-odoo-1",
            tenant_id="tenant-a",
            actor_id="actor-a",
            workflow_key="CP-ODOO-CRM-STATE-SYNC",
            workflow_version="1",
            delivery_token="delivery-token",
            workflow_family="crm",
        )
        self.claim = self.service.claim_job(
            {
                "job_id": "job-odoo-1",
                "delivery_token": "delivery-token",
                "workflow_key": "CP-ODOO-CRM-STATE-SYNC",
                "workflow_version": "1",
                "execution_id": "exec-1",
            }
        )

    def test_claim_returns_active_lease(self) -> None:
        self.assertEqual("CLAIMED", self.claim["state"])
        self.assertEqual("tenant-a", self.claim["tenant_id"])
        self.assertTrue(self.claim["lease_token"])

    def test_command_is_middleware_governed_and_dry_run_by_default(self) -> None:
        command = self.service.submit_command(
            {
                "job_id": "job-odoo-1",
                "lease_token": self.claim["lease_token"],
                "execution_id": "exec-1",
                "workflow_key": "CP-ODOO-CRM-STATE-SYNC",
                "workflow_version": "1",
                "step_key": "sync-stage",
                "command_type": "crm.odoo.state-sync",
                "payload": {"lead_id": "L-1", "stage": "Qualified"},
            },
            "idem-1",
        )

        self.assertEqual("DRY_RUN_ACCEPTED", command["state"])
        self.assertEqual("automation.command.crm", command["scope"])
        self.assertEqual("NO_EFFECT", command["adapter_result"]["status"])
        self.assertEqual("odoo", command["adapter_result"]["adapter"])
        self.assertEqual("crm", command["adapter_result"]["domain"])
        self.assertEqual(command, self.service.get_command(command["command_id"]))

    def test_exact_idempotency_replay_returns_original_command(self) -> None:
        body = {
            "job_id": "job-odoo-1",
            "lease_token": self.claim["lease_token"],
            "execution_id": "exec-1",
            "workflow_key": "CP-ODOO-CRM-STATE-SYNC",
            "workflow_version": "1",
            "step_key": "sync-stage",
            "command_type": "crm.odoo.state-sync",
            "payload": {"lead_id": "L-1"},
        }
        first = self.service.submit_command(body, "idem-2")
        second = self.service.submit_command(body, "idem-2")
        self.assertEqual(first, second)

    def test_conflicting_idempotency_replay_is_rejected(self) -> None:
        body = {
            "job_id": "job-odoo-1",
            "lease_token": self.claim["lease_token"],
            "execution_id": "exec-1",
            "workflow_key": "CP-ODOO-CRM-STATE-SYNC",
            "workflow_version": "1",
            "step_key": "sync-stage",
            "command_type": "crm.odoo.state-sync",
            "payload": {"lead_id": "L-1"},
        }
        self.service.submit_command(body, "idem-3")
        changed = dict(body)
        changed["payload"] = {"lead_id": "L-2"}
        with self.assertRaises(AutomationError) as caught:
            self.service.submit_command(changed, "idem-3")
        self.assertEqual("IDEMPOTENCY_CONFLICT", caught.exception.code)

    def test_direct_or_unknown_command_prefix_is_denied(self) -> None:
        body = {
            "job_id": "job-odoo-1",
            "lease_token": self.claim["lease_token"],
            "execution_id": "exec-1",
            "workflow_key": "CP-ODOO-CRM-STATE-SYNC",
            "workflow_version": "1",
            "step_key": "direct-odoo",
            "command_type": "odoo.direct.write",
        }
        with self.assertRaises(AutomationError) as caught:
            self.service.submit_command(body, "idem-4")
        self.assertEqual("COMMAND_PREFIX_DENIED", caught.exception.code)

    def test_job_lifecycle_heartbeat_steps_complete(self) -> None:
        heartbeat = self.service.heartbeat_job(
            "job-odoo-1",
            {"lease_token": self.claim["lease_token"], "execution_id": "exec-1"},
        )
        self.assertEqual("CLAIMED", heartbeat["state"])
        step = self.service.record_step(
            "job-odoo-1",
            {
                "lease_token": self.claim["lease_token"],
                "execution_id": "exec-1",
                "step_key": "verify",
                "status": "PASS",
            },
        )
        self.assertEqual("verify", step["step"]["step_key"])
        completed = self.service.complete_job(
            "job-odoo-1",
            {
                "lease_token": self.claim["lease_token"],
                "execution_id": "exec-1",
                "result": {"odoo_state": "DRY_RUN_VERIFIED"},
            },
        )
        self.assertEqual("COMPLETED", completed["state"])

    def test_fail_creates_dead_letter_and_safe_replay_creates_new_job(self) -> None:
        failed = self.service.fail_job(
            "job-odoo-1",
            {
                "lease_token": self.claim["lease_token"],
                "execution_id": "exec-1",
                "error": {"code": "ADAPTER_TIMEOUT"},
                "safe_replay": True,
            },
        )
        replay = self.service.replay_dead_letter(
            failed["dead_letter_id"],
            {"expected_version": 1, "reason": "staging retry"},
        )
        self.assertEqual("REPLAY_REQUESTED", replay["state"])
        self.assertEqual("PENDING", replay["replay_job"]["state"])

    def test_reconciliation_reports_unknown_pending_adapter_commands(self) -> None:
        self.service.submit_command(
            {
                "job_id": "job-odoo-1",
                "lease_token": self.claim["lease_token"],
                "execution_id": "exec-1",
                "workflow_key": "CP-ODOO-CRM-STATE-SYNC",
                "workflow_version": "1",
                "step_key": "sync-stage",
                "command_type": "crm.odoo.state-sync",
                "dry_run": False,
            },
            "idem-5",
        )
        run = self.service.reconcile_jobs({"requested_by": "test"})
        self.assertEqual("COMPLETED", run["state"])
        self.assertEqual(1, run["checked_commands"])

    def test_file_backed_state_survives_service_restart(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            path = Path(tempdir) / "automation-state.json"
            first = AutomationService(state_path=path)
            first.seed_job(
                job_id="job-persisted",
                tenant_id="tenant-a",
                actor_id="actor-a",
                workflow_key="CP-ODOO-CRM-STATE-SYNC",
                workflow_version="1",
                delivery_token="delivery-token",
                workflow_family="crm",
            )
            claim = first.claim_job(
                {
                    "job_id": "job-persisted",
                    "delivery_token": "delivery-token",
                    "workflow_key": "CP-ODOO-CRM-STATE-SYNC",
                    "workflow_version": "1",
                    "execution_id": "exec-persisted",
                }
            )
            first.submit_command(
                {
                    "job_id": "job-persisted",
                    "lease_token": claim["lease_token"],
                    "execution_id": "exec-persisted",
                    "workflow_key": "CP-ODOO-CRM-STATE-SYNC",
                    "workflow_version": "1",
                    "step_key": "sync-stage",
                    "command_type": "crm.odoo.state-sync",
                },
                "persisted-idem",
            )

            second = AutomationService(state_path=path)
            self.assertEqual("CLAIMED", second.get_job("job-persisted")["state"])
            self.assertEqual(1, len(second.commands))

    def test_all_enterprise_adapters_are_registered(self) -> None:
        samples = {
            "crm.odoo.state-sync": "odoo",
            "email.klyrow.dispatch": "klyrow",
            "sms.telnexa.dispatch": "telnexa",
            "telephony.vicidial.reconcile": "vicidial",
            "crawler.kyqra.reconcile": "kyqra",
            "social.postly.publish": "postly",
            "provisioning.agent.lifecycle": "provisioning",
            "moneybee.loan.review": "moneybee",
            "beyvra.operations.report": "beyvra",
            "larim.booking.dispatch": "larim-a",
            "freight.shipment.reconcile": "freight",
            "breero.marketplace.booking": "breero",
            "booked4seasons.booking.sync": "booked4seasons",
            "trading.operations.report": "trading",
        }
        for index, (command_type, adapter_name) in enumerate(samples.items(), 10):
            service = AutomationService()
            service.seed_job(
                job_id=f"job-{index}",
                tenant_id="tenant-a",
                actor_id="actor-a",
                workflow_key="CP-PRODUCT",
                workflow_version="1",
                delivery_token="delivery-token",
                workflow_family="product",
            )
            claim = service.claim_job(
                {
                    "job_id": f"job-{index}",
                    "delivery_token": "delivery-token",
                    "workflow_key": "CP-PRODUCT",
                    "workflow_version": "1",
                    "execution_id": f"exec-{index}",
                }
            )
            command = service.submit_command(
                {
                    "job_id": f"job-{index}",
                    "lease_token": claim["lease_token"],
                    "execution_id": f"exec-{index}",
                    "workflow_key": "CP-PRODUCT",
                    "workflow_version": "1",
                    "step_key": "adapter",
                    "command_type": command_type,
                },
                f"idem-{index}",
            )
            self.assertEqual(adapter_name, command["adapter_result"]["adapter"])


if __name__ == "__main__":
    unittest.main()
