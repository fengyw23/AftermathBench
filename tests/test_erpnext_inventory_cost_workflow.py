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
        self.assertIn("run_erpnext_inventory_cost_baseline.py", workflow)
        self.assertIn("summarize_erpnext_inventory_cost_baselines.py", workflow)
        self.assertIn("boundary-bundles", workflow)
        self.assertIn("public-dev-001", workflow)
        self.assertIn("public-dev-002", workflow)
        self.assertIn("matrix.scenario", workflow)
        self.assertIn("matrix.instance", workflow)
        self.assertNotIn("create_missing_reposting_owner", workflow)
        boundary_runner = (
            repository_root()
            / "scripts"
            / "run_erpnext_inventory_cost_boundary.py"
        ).read_text(encoding="utf-8")
        self.assertIn("http://127.0.0.1:9091/audit", boundary_runner)
        self.assertNotIn("http://127.0.0.1:9091/events", boundary_runner)


if __name__ == "__main__":
    unittest.main()
