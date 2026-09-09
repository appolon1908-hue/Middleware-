from __future__ import annotations

import copy
import importlib.util
import json
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "apply_integration_main_release_authorities_v2.py"
CONFIG = ROOT / "config" / "integration-main-release-authorities.v1.json"

spec = importlib.util.spec_from_file_location("integration_authority_v2", SCRIPT)
assert spec and spec.loader
V2 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(V2)
V2.configure_base()
MODULE = V2.BASE


class IntegrationMainReleaseAuthorityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config: dict[str, Any] = json.loads(CONFIG.read_text(encoding="utf-8"))

    def test_exact_fixed_repository_set_validates(self) -> None:
        rows = MODULE.validate_config(self.config)
        self.assertEqual({row["repository"] for row in rows}, set(V2.EXPECTED_REPOSITORIES))
        self.assertEqual(len(rows), 7)
        self.assertEqual(self.config["reviewer"], MODULE.EXPECTED_REVIEWER)

    def test_every_ruleset_is_fail_closed(self) -> None:
        for row in MODULE.validate_config(self.config):
            normalized = MODULE.normalize_ruleset(MODULE.desired_ruleset(row))
            self.assertEqual(normalized["bypass_actors"], [])
            self.assertEqual(normalized["conditions"]["ref_name"]["include"], ["~DEFAULT_BRANCH"])
            pull = normalized["rules"]["pull_request"]
            self.assertEqual(pull["required_approving_review_count"], 1)
            self.assertTrue(pull["dismiss_stale_reviews_on_push"])
            self.assertTrue(pull["require_last_push_approval"])
            self.assertTrue(pull["required_review_thread_resolution"])
            self.assertEqual(pull["allowed_merge_methods"], ["squash"])
            status = normalized["rules"]["required_status_checks"]
            self.assertTrue(status["strict_required_status_checks_policy"])
            self.assertFalse(status["do_not_enforce_on_create"])
            self.assertEqual(
                status["contexts"],
                sorted(row["required_status_checks"]),
            )

    def stronger_live_ruleset(self) -> tuple[dict[str, Any], dict[str, Any]]:
        row = MODULE.validate_config(self.config)[0]
        baseline = MODULE.desired_ruleset(row)
        existing = copy.deepcopy(baseline)
        pull = next(rule for rule in existing["rules"] if rule["type"] == "pull_request")
        pull["parameters"]["require_code_owner_review"] = True
        pull["parameters"]["require_extra_approval_for_unattributed_changes"] = True
        pull["parameters"]["required_approving_review_count"] = 2
        pull["parameters"]["automatic_copilot_code_review_enabled"] = True
        status = next(
            rule for rule in existing["rules"] if rule["type"] == "required_status_checks"
        )
        status["parameters"]["future_enforcement_mode"] = "strict"
        status["parameters"]["required_status_checks"][0]["integration_id"] = 98765
        status["parameters"]["required_status_checks"][0]["provider_slug"] = "github-actions"
        status["parameters"]["required_status_checks"].append(
            {"context": "existing-security-gate", "integration_id": 54321}
        )
        existing["rules"].append({"type": "required_signatures"})
        return baseline, existing

    def test_merge_preserves_stronger_live_controls_and_bindings(self) -> None:
        baseline, existing = self.stronger_live_ruleset()
        merged = MODULE.merge_ruleset_preserving_stronger_controls(existing, baseline)
        normalized = MODULE.normalize_ruleset(merged)
        pull = normalized["rules"]["pull_request"]
        self.assertTrue(pull["require_code_owner_review"])
        self.assertTrue(pull["require_extra_approval_for_unattributed_changes"])
        self.assertEqual(pull["required_approving_review_count"], 2)
        self.assertTrue(
            pull["additional_parameters"]["automatic_copilot_code_review_enabled"]
        )
        status = normalized["rules"]["required_status_checks"]
        self.assertEqual(
            status["additional_parameters"]["future_enforcement_mode"],
            "strict",
        )
        checks = {check["context"]: check for check in status["checks"]}
        bound_check = checks[baseline["rules"][-1]["parameters"]["required_status_checks"][0]["context"]]
        self.assertEqual(bound_check["integration_id"], 98765)
        self.assertEqual(bound_check["provider_slug"], "github-actions")
        self.assertIn(
            {"context": "existing-security-gate", "integration_id": 54321},
            checks,
        )
        self.assertIn("required_signatures", normalized["additional_rules"])

    def test_stronger_live_ruleset_satisfies_baseline(self) -> None:
        baseline, existing = self.stronger_live_ruleset()
        self.assertTrue(MODULE.ruleset_meets_baseline(existing, baseline))
        merged = MODULE.merge_ruleset_preserving_stronger_controls(existing, baseline)
        self.assertEqual(
            MODULE.normalize_ruleset(existing),
            MODULE.normalize_ruleset(merged),
        )

    def test_status_check_order_does_not_force_a_ruleset_write(self) -> None:
        baseline, existing = self.stronger_live_ruleset()
        status = next(
            rule for rule in existing["rules"] if rule["type"] == "required_status_checks"
        )
        status["parameters"]["required_status_checks"].reverse()

        self.assertTrue(MODULE.ruleset_meets_baseline(existing, baseline))

    def test_effective_policy_rejects_dropped_extension_controls(self) -> None:
        baseline, existing = self.stronger_live_ruleset()
        effective = MODULE.merge_ruleset_preserving_stronger_controls(existing, baseline)

        weakened_pull = copy.deepcopy(effective)
        pull = next(
            rule for rule in weakened_pull["rules"] if rule["type"] == "pull_request"
        )
        pull["parameters"].pop("automatic_copilot_code_review_enabled")
        self.assertFalse(MODULE.ruleset_meets_baseline(weakened_pull, effective))

        weakened_status = copy.deepcopy(effective)
        status = next(
            rule
            for rule in weakened_status["rules"]
            if rule["type"] == "required_status_checks"
        )
        status["parameters"].pop("future_enforcement_mode")
        self.assertFalse(MODULE.ruleset_meets_baseline(weakened_status, effective))

        weakened_check = copy.deepcopy(effective)
        status = next(
            rule
            for rule in weakened_check["rules"]
            if rule["type"] == "required_status_checks"
        )
        status["parameters"]["required_status_checks"][0].pop("provider_slug")
        self.assertFalse(MODULE.ruleset_meets_baseline(weakened_check, effective))

    def test_effective_policy_rejects_dropped_provider_binding(self) -> None:
        baseline, existing = self.stronger_live_ruleset()
        effective = MODULE.merge_ruleset_preserving_stronger_controls(existing, baseline)
        weakened = copy.deepcopy(effective)
        status = next(
            rule for rule in weakened["rules"] if rule["type"] == "required_status_checks"
        )
        status["parameters"]["required_status_checks"][0].pop("integration_id")
        self.assertFalse(MODULE.ruleset_meets_baseline(weakened, effective))

    def test_merge_repairs_missing_baseline_rule_type(self) -> None:
        baseline, existing = self.stronger_live_ruleset()
        existing["rules"] = [
            rule
            for rule in existing["rules"]
            if rule["type"] != "required_status_checks"
        ]

        self.assertFalse(MODULE.ruleset_meets_baseline(existing, baseline))
        merged = MODULE.merge_ruleset_preserving_stronger_controls(existing, baseline)
        normalized = MODULE.normalize_ruleset(merged)

        self.assertIn("required_status_checks", normalized["rules"])
        self.assertIn("required_signatures", normalized["additional_rules"])

    def test_weaker_live_ruleset_fails_baseline(self) -> None:
        baseline, existing = self.stronger_live_ruleset()
        status = next(
            rule for rule in existing["rules"] if rule["type"] == "required_status_checks"
        )
        status["parameters"]["required_status_checks"].pop(0)
        self.assertFalse(MODULE.ruleset_meets_baseline(existing, baseline))

    def test_duplicate_live_status_context_fails_closed(self) -> None:
        baseline, existing = self.stronger_live_ruleset()
        status = next(
            rule for rule in existing["rules"] if rule["type"] == "required_status_checks"
        )
        status["parameters"]["required_status_checks"].append(
            copy.deepcopy(status["parameters"]["required_status_checks"][0])
        )
        with self.assertRaises(MODULE.PolicyError):
            MODULE.merge_ruleset_preserving_stronger_controls(existing, baseline)

    def test_unknown_repository_fails(self) -> None:
        broken = copy.deepcopy(self.config)
        broken["repositories"][0]["repository"] = "appolon1908-hue/not-authorized"
        with self.assertRaises(MODULE.PolicyError):
            MODULE.validate_config(broken)

    def test_stable_repository_id_drift_fails(self) -> None:
        broken = copy.deepcopy(self.config)
        broken["repositories"][0]["repository_id"] += 1
        with self.assertRaises(MODULE.PolicyError):
            MODULE.validate_config(broken)

    def test_reviewer_drift_fails(self) -> None:
        broken = copy.deepcopy(self.config)
        broken["reviewer"]["permission"] = "admin"
        with self.assertRaises(MODULE.PolicyError):
            MODULE.validate_config(broken)

    def test_validate_mode_is_offline_and_non_mutating(self) -> None:
        document = MODULE.execute("validate", "")
        self.assertEqual(document["result"], "PASS")
        self.assertFalse(document["production_changed"])
        self.assertFalse(document["runtime_contacted"])
        self.assertFalse(document["external_effects_enabled"])
        self.assertEqual(len(document["repositories"]), 7)


if __name__ == "__main__":
    unittest.main()
