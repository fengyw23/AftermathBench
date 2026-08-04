from __future__ import annotations

import unittest

from aftermath_bench.schema import repository_root


class ERPNextSharedBatchModelWorkflowTest(unittest.TestCase):
    def test_workflow_can_evaluate_an_independent_checked_in_instance(self) -> None:
        workflow = (
            repository_root()
            / ".github"
            / "workflows"
            / "erpnext-shared-batch-model.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("scenario:\n        description:", workflow)
        self.assertIn(
            "SCENARIO: ${{ inputs.scenario || "
            "'data/scenario_blueprints/erpnext-shared-batch-recovery-dev-001/"
            "scenario.json' }}",
            workflow,
        )
        self.assertIn(
            "data/scenario_blueprints/erpnext-shared-batch-recovery-*/scenario.json",
            workflow,
        )
        self.assertIn("test -f \"$SCENARIO\"", workflow)
        self.assertNotIn(
            "RUN_ROOT: data/generated/erpnext-shared-batch-recovery-dev-001/model",
            workflow,
        )


if __name__ == "__main__":
    unittest.main()
