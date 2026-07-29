from __future__ import annotations

import unittest

from aftermath_bench.schema import repository_root


class KubernetesWorkflowTest(unittest.TestCase):
    def test_workflow_builds_kind_and_pins_kubernetes_image(self) -> None:
        workflow = (
            repository_root()
            / ".github"
            / "workflows"
            / "kubernetes-runtime.yml"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "9a205e8c8540557602240f8766d3c95c51c23c4c",
            workflow,
        )
        self.assertIn("verify_kubernetes_sources.py", workflow)
        self.assertIn("validate-reset", workflow)
        self.assertIn("kind export logs", workflow)

    def test_workflow_does_not_claim_fault_admission(self) -> None:
        workflow = (
            repository_root()
            / ".github"
            / "workflows"
            / "kubernetes-runtime.yml"
        ).read_text(encoding="utf-8")
        self.assertNotIn("admitted", workflow.lower())
        self.assertNotIn("run-native-model", workflow)


if __name__ == "__main__":
    unittest.main()
