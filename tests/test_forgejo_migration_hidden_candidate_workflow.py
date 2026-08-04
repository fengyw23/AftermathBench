from __future__ import annotations

import unittest
from pathlib import Path


class ForgejoMigrationHiddenCandidateWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = (Path(__file__).resolve().parents[1] / ".github" / "workflows" / "forgejo-migration-hidden-candidate.yml").read_text(encoding="utf-8")

    def test_freeze_and_seal_precede_any_model_access(self) -> None:
        self.assertIn("Admit and freeze before any provider request", self.text)
        self.assertIn("Seal the unseen private bundle", self.text)
        self.assertNotIn("run-native-model", self.text)
        self.assertNotIn("AFTERMATH_API_KEY", self.text)

    def test_native_replay_and_receipt_registration_are_bound(self) -> None:
        for token in ("snapshot-migration-bundle", "restore-migration-bundle", "run_forgejo_migration_reference.py", "run_forgejo_migration_baseline.py", "verify_hidden_test_eligibility.py", "Register the frozen-hidden receipt"):
            self.assertIn(token, self.text)


if __name__ == "__main__":
    unittest.main()
