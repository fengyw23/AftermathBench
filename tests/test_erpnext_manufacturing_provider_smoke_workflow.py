from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = (
    ROOT
    / ".github"
    / "workflows"
    / "erpnext-manufacturing-provider-smoke.yml"
)


class ERPNextManufacturingProviderSmokeWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = WORKFLOW.read_text(encoding="utf-8")

    def test_uses_public_manufacturing_data_and_bigmodel_secret(self) -> None:
        self.assertIn("erpnext-manufacturing-rework-dev-001", self.text)
        self.assertIn("secrets.ZHIPU_CODING_API_KEY", self.text)
        self.assertIn("https://open.bigmodel.cn/api/coding/paas/v4", self.text)
        self.assertNotIn("hidden_test", self.text)
        self.assertNotIn("HIDDEN_BUNDLE_ENCRYPTION_KEY", self.text)

    def test_exercises_the_exact_boundary_layout_and_runner_output(self) -> None:
        self.assertIn("run_erpnext_manufacturing_failure.py", self.text)
        self.assertIn("run-native-model", self.text)
        self.assertIn("--max-turns 2", self.text)
        self.assertIn("surface_failure_recorded", self.text)
        self.assertIn("trajectory_persisted", self.text)

    def test_model_failure_is_accepted_only_when_a_trajectory_exists(self) -> None:
        self.assertIn('elif [ -s "$trajectory" ]', self.text)
        self.assertIn('[ "$run_status" -eq 0 ]', self.text)
        self.assertIn("len(trajectory.get(\"turns\", [])) >= 1", self.text)


if __name__ == "__main__":
    unittest.main()
