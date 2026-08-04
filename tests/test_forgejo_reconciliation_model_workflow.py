from __future__ import annotations

import unittest

from aftermath_bench.schema import repository_root


class ForgejoReconciliationModelWorkflowTest(unittest.TestCase):
    def test_workflow_rebuilds_boundaries_and_runs_native_model(self) -> None:
        text = (
            repository_root()
            / ".github"
            / "workflows"
            / "forgejo-reconciliation-model.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("run_forgejo_reconciliation_boundary.py", text)
        self.assertIn("run_forgejo_reconciliation_reference.py", text)
        self.assertIn("audit_forgejo_reconciliation_runtime.py", text)
        self.assertIn("run-native-model", text)
        self.assertIn("--execution-control", text)
        self.assertIn("public-dev-001", text)
        self.assertIn("public-dev-002", text)
        self.assertIn("ZHIPU_CODING_API_KEY", text)


if __name__ == "__main__":
    unittest.main()
