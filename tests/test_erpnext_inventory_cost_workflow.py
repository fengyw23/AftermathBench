from __future__ import annotations

import unittest

from aftermath_bench.schema import repository_root


class ERPNextInventoryCostWorkflowTest(unittest.TestCase):
    def test_workflow_builds_source_grounded_boundaries_and_references(self) -> None:
        workflow = (
            repository_root()
            / ".github"
            / "workflows"
            / "erpnext-inventory-cost-runtime.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("build_erpnext_inventory_cost_prefix.py", workflow)
        self.assertIn("run_erpnext_inventory_cost_boundary.py", workflow)
        self.assertIn("--run-reference", workflow)
        self.assertIn("audit_erpnext_inventory_cost_boundaries.py", workflow)
        self.assertNotIn("create_missing_reposting_owner", workflow)


if __name__ == "__main__":
    unittest.main()
