from __future__ import annotations

import unittest

from aftermath_bench.schema import repository_root


class ERPNextSalesReturnWorkflowTest(unittest.TestCase):
    def test_workflow_builds_and_validates_native_prefix(self) -> None:
        workflow = (
            repository_root()
            / ".github"
            / "workflows"
            / "erpnext-sales-return-validation.yml"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "build_erpnext_sales_return_prefix.py",
            workflow,
        )
        self.assertIn(
            "validate_erpnext_sales_return_prefix.py",
            workflow,
        )
        self.assertIn("build_erpnext_runtime.py", workflow)
        self.assertNotIn("AFTERMATH_API_KEY", workflow)


if __name__ == "__main__":
    unittest.main()
