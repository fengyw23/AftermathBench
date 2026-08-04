from __future__ import annotations

import unittest

from aftermath_bench.schema import repository_root


class ERPNextInventoryCostModelWorkflowTest(unittest.TestCase):
    def test_model_workflow_restores_each_authoritative_boundary(self) -> None:
        workflow = (
            repository_root()
            / ".github"
            / "workflows"
            / "erpnext-inventory-cost-model.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("run-native-model", workflow)
        self.assertIn("boundary-$variant", workflow)
        self.assertIn("restore-bundle", workflow)
        self.assertIn("--expected-execution-control", workflow)
        self.assertIn("ZHIPU_CODING_API_KEY", workflow)
        self.assertNotIn("gold_scope", workflow)


if __name__ == "__main__":
    unittest.main()
