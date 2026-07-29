from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class KubernetesBoundaryWorkflowTests(unittest.TestCase):
    def test_workflow_replays_all_matched_variants(self):
        workflow = (
            ROOT / ".github" / "workflows" / "kubernetes-runtime.yml"
        ).read_text(encoding="utf-8")
        for variant in (
            "patch_request_not_reached",
            "deployment_spec_committed_response_lost",
            "deployment_spec_committed_reconcile_paused",
            "new_replicaset_created_rollout_pending",
        ):
            self.assertIn(variant, workflow)
        self.assertIn("run_kubernetes_rollout_boundary.py", workflow)
        self.assertIn("run_kubernetes_rollout_control.py", workflow)
        self.assertIn("${{ runner.temp }}/kubernetes-boundaries", workflow)


if __name__ == "__main__":
    unittest.main()
