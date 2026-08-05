from __future__ import annotations

import unittest
from pathlib import Path


class ModelEvidenceImportWorkflowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = (
            Path(__file__).resolve().parents[1]
            / ".github"
            / "workflows"
            / "ordinary-model-evidence-import.yml"
        ).read_text(encoding="utf-8")

    def test_workflow_uses_reviewed_gate_and_github_token(self) -> None:
        self.assertIn(
            "ordinary-model-evidence-import-20260805.json", self.text
        )
        self.assertIn("actions: read", self.text)
        self.assertIn("github.token", self.text)
        self.assertIn("gh run download", self.text)

    def test_workflow_scans_secrets_and_has_narrow_commit_allowlist(self) -> None:
        self.assertIn("--secret-env MODEL_SECRET_ZHIPU", self.text)
        self.assertIn("--secret-env MODEL_SECRET_BAILIAN", self.text)
        self.assertIn("--secret-env MODEL_SECRET_PARATERA", self.text)
        self.assertIn("data/evidence/model-runs/", self.text)
        self.assertNotIn("run-native-model", self.text)
        self.assertNotIn("hidden-freeze", self.text)
        self.assertNotIn("hidden-usage-ledger", self.text)


if __name__ == "__main__":
    unittest.main()
