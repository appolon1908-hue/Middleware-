from __future__ import annotations

import copy
import importlib.util
import json
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "apply_production_reviewer_access.py"
CONFIG = ROOT / "config" / "production-reviewer-access.v1.json"

spec = importlib.util.spec_from_file_location("production_reviewer_access", SCRIPT)
assert spec and spec.loader
MODULE = importlib.util.module_from_spec(spec)
spec.loader.exec_module(MODULE)


class ProductionReviewerAccessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config: dict[str, Any] = json.loads(CONFIG.read_text(encoding="utf-8"))

    def test_exact_fixed_repository_set_validates(self) -> None:
        repositories = MODULE.validate_config(self.config)
        self.assertEqual(set(repositories), MODULE.EXPECTED_REPOSITORIES)
        self.assertEqual(len(repositories), 19)
        self.assertEqual(self.config["reviewer"], MODULE.EXPECTED_REVIEWER)

    def test_every_repository_is_owner_scoped(self) -> None:
        for repository in MODULE.validate_config(self.config):
            self.assertTrue(repository.startswith("appolon1908-hue/"))

    def test_foreign_or_unknown_repository_fails(self) -> None:
        broken = copy.deepcopy(self.config)
        broken["repositories"][0] = "another-owner/not-authorized"
        with self.assertRaises(MODULE.AccessError):
            MODULE.validate_config(broken)

    def test_duplicate_repository_fails(self) -> None:
        broken = copy.deepcopy(self.config)
        broken["repositories"][-1] = broken["repositories"][0]
        with self.assertRaises(MODULE.AccessError):
            MODULE.validate_config(broken)

    def test_admin_reviewer_permission_fails(self) -> None:
        broken = copy.deepcopy(self.config)
        broken["reviewer"]["admin"] = True
        with self.assertRaises(MODULE.AccessError):
            MODULE.validate_config(broken)

    def test_validate_mode_is_offline_and_non_mutating(self) -> None:
        document = MODULE.execute("validate", "")
        self.assertEqual(document["result"], "PASS")
        self.assertEqual(len(document["repositories"]), 19)
        self.assertFalse(document["runtime_contacted"])
        self.assertFalse(document["production_changed"])
        self.assertFalse(document["external_effects_enabled"])

    def test_permission_helper_accepts_write_but_not_read(self) -> None:
        self.assertTrue(MODULE.permission_is_write({"permission": "write"}))
        self.assertTrue(MODULE.permission_is_write({"permission": "push"}))
        self.assertFalse(MODULE.permission_is_write({"permission": "read"}))
        self.assertFalse(MODULE.permission_is_write(None))


if __name__ == "__main__":
    unittest.main()
