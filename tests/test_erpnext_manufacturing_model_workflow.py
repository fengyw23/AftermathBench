from __future__ import annotations

import unittest
from pathlib import Path


class ERPNextManufacturingModelWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = (
            Path(__file__).resolve().parents[1]
            / ".github"
            / "workflows"
            / "erpnext-manufacturing-model.yml"
        ).read_text(encoding="utf-8")

    def test_public_workflow_uses_the_admitted_manufacturing_instance(self) -> None:
        self.assertIn("erpnext-manufacturing-model", self.text)
        self.assertIn(
            "data/scenarios/erpnext-manufacturing-rework-dev-001/scenario.json",
            self.text,
        )
        self.assertIn("validate-native-scenario", self.text)
        self.assertIn("ZHIPU_CODING_API_KEY", self.text)

    def test_each_variant_is_captured_then_restored_before_model_access(self) -> None:
        failure = self.text.index("run_erpnext_manufacturing_failure.py")
        boundary = self.text.index('boundary-$variant', failure)
        model = self.text.index("run-native-model")
        restore = self.text.rindex('boundary-$variant', 0, model)
        self.assertLess(failure, boundary)
        self.assertLess(boundary, restore)
        self.assertLess(restore, model)
        self.assertIn("matched_variants", self.text)

    def test_scope_control_and_full_summary_are_explicit(self) -> None:
        self.assertIn("--execution-control", self.text)
        self.assertIn("--expected-execution-control", self.text)
        self.assertIn("summarize_native_model_runs.py", self.text)
        self.assertIn("--max-turns 25", self.text)
        self.assertIn("for attempt in 1 2", self.text)

    def test_artifact_excludes_credentials_and_database_bundles(self) -> None:
        self.assertIn(
            "rm -f runtimes/erpnext/.runtime/credentials.json",
            self.text,
        )
        upload = self.text.index("Upload complete public experiment evidence")
        purge = self.text.index("remove database snapshots")
        self.assertLess(upload, purge)
        upload_block = self.text[upload:purge]
        self.assertNotIn("bundles/", upload_block)


if __name__ == "__main__":
    unittest.main()
