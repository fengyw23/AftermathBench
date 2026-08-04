from __future__ import annotations

import unittest
from pathlib import Path


class ERPNextMultiwarehouseWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = (
            Path(__file__).resolve().parents[1]
            / ".github"
            / "workflows"
            / "erpnext-multiwarehouse-runtime.yml"
        ).read_text(encoding="utf-8")

    def test_workflow_executes_matched_references_and_baselines(self) -> None:
        for variant in (
            "request_not_reached",
            "database_committed_response_lost",
            "after_commit_enqueue_failed",
            "async_job_pending",
        ):
            self.assertIn(variant, self.text)
        self.assertIn("run_erpnext_multiwarehouse_control.py", self.text)
        self.assertIn("run_erpnext_multiwarehouse_baseline.py", self.text)

    def test_workflow_derives_and_publishes_admission(self) -> None:
        self.assertIn("build_erpnext_multiwarehouse_admission.py", self.text)
        self.assertIn(
            "generated/erpnext-multiwarehouse-transfer-dev-001", self.text
        )
        self.assertIn("permissions:\n  contents: write", self.text)

    def test_workflow_freezes_formal_inputs_from_native_boundaries(self) -> None:
        for token in (
            "capture_erpnext_multiwarehouse_state_evidence.py",
            "--formal-contract",
            "generate_erpnext_multiwarehouse_formal_build_spec.py",
            "build_formal_evidence.py",
            "formal-input-lock.json",
            "run-native-model",
            "validate_native_control_summary.py",
            "completion/declarations.json",
            "generate_formal_release_binding.py",
        ):
            self.assertIn(token, self.text)


if __name__ == "__main__":
    unittest.main()
