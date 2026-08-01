from __future__ import annotations

import unittest
from pathlib import Path


class KubernetesInteractionPublicDevInstanceWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(__file__).parents[1]
        cls.workflow = (
            cls.root
            / ".github"
            / "workflows"
            / "kubernetes-interaction-public-dev-instance.yml"
        ).read_text(encoding="utf-8")

    def test_instance_spec_is_bound_before_native_runtime(self) -> None:
        self.assertIn(
            "AFTERMATH_KUBERNETES_INTERACTION_INSTANCE_SPEC", self.workflow
        )
        novelty = self.workflow.index(
            "verify_kubernetes_interaction_instance_novelty.py"
        )
        runtime = self.workflow.index("manage_kubernetes_stack.py up")
        self.assertLess(novelty, runtime)

    def test_workflow_proves_exact_replay_without_model_provider(self) -> None:
        self.assertIn("verify_kubernetes_snapshot_replay.py", self.workflow)
        lowered = self.workflow.lower()
        self.assertNotIn("api_key", lowered)
        self.assertNotIn("run-native-model", lowered)
        self.assertNotIn("secrets.", lowered)

    def test_checked_blueprint_is_byte_compared_to_renderer(self) -> None:
        self.assertIn("render_kubernetes_interaction_blueprint.py", self.workflow)
        self.assertIn("cmp ", self.workflow)


if __name__ == "__main__":
    unittest.main()
