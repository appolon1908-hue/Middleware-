from __future__ import annotations

import copy
import importlib.util
import json
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "validate_production_integration_lock.py"
LOCK = ROOT / "config" / "production-integration-lock.v1.json"

spec = importlib.util.spec_from_file_location("production_integration_lock", SCRIPT)
assert spec and spec.loader
MODULE = importlib.util.module_from_spec(spec)
spec.loader.exec_module(MODULE)


class ProductionIntegrationLockTests(unittest.TestCase):
    def setUp(self) -> None:
        self.lock: dict[str, Any] = json.loads(LOCK.read_text(encoding="utf-8"))

    def test_current_no_go_lock_is_valid(self) -> None:
        document = MODULE.validate_lock(self.lock)
        self.assertEqual(document["result"], "PASS")
        self.assertEqual(document["decision"], "NO_GO")
        self.assertEqual(document["runtime_certified_count"], 0)
        self.assertFalse(document["production_activated"])
        self.assertEqual(document["calls_placed"], 0)

    def test_live_effect_fails(self) -> None:
        broken = copy.deepcopy(self.lock)
        broken["release_policy"]["external_effects"]["email_delivery"] = True
        with self.assertRaises(MODULE.LockError):
            MODULE.validate_lock(broken)

    def test_duplicate_repository_fails(self) -> None:
        broken = copy.deepcopy(self.lock)
        broken["components"][1]["repository"] = broken["components"][0]["repository"]
        with self.assertRaises(MODULE.LockError):
            MODULE.validate_lock(broken)

    def test_candidate_state_without_pr_evidence_fails(self) -> None:
        broken = copy.deepcopy(self.lock)
        row = next(
            item for item in broken["components"]
            if item["source_state"] == "candidate_pending_review"
        )
        row["candidates"] = []
        with self.assertRaises(MODULE.LockError):
            MODULE.validate_lock(broken)

    def test_false_runtime_certification_fails_without_digest_and_evidence(self) -> None:
        broken = copy.deepcopy(self.lock)
        row = broken["components"][0]
        row["runtime"]["runtime_certified"] = True
        with self.assertRaises(MODULE.LockError):
            MODULE.validate_lock(broken)

    def test_unprotected_component_cannot_be_source_ready(self) -> None:
        broken = copy.deepcopy(self.lock)
        row = next(
            item for item in broken["components"]
            if item["governance"]["branch_protected"] is False
        )
        row["production_state"] = "SOURCE_READY"
        with self.assertRaises(MODULE.LockError):
            MODULE.validate_lock(broken)

    def test_invalid_source_sha_fails(self) -> None:
        broken = copy.deepcopy(self.lock)
        broken["components"][0]["source_sha"] = "main"
        with self.assertRaises(MODULE.LockError):
            MODULE.validate_lock(broken)

    def test_calls_placed_must_remain_zero(self) -> None:
        broken = copy.deepcopy(self.lock)
        broken["release_policy"]["calls_placed"] = 1
        with self.assertRaises(MODULE.LockError):
            MODULE.validate_lock(broken)


if __name__ == "__main__":
    unittest.main()
