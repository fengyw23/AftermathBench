from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class KubernetesModelWorkflowTests(unittest.TestCase):
    def test_model_workflow_runs_all_native_variants_and_sanitizes(self):
        workflow = (
            ROOT / ".github" / "workflows" / "kubernetes-model.yml"
        ).read_text(encoding="utf-8")
        for variant in (
            "patch_request_not_reached",
            "deployment_spec_committed_response_lost",
            "deployment_spec_committed_reconcile_paused",
            "new_replicaset_created_rollout_pending",
        ):
            self.assertIn(variant, workflow)
        self.assertIn("run-native-model", workflow)
        self.assertIn("--scenario \"$SCENARIO\"", workflow)
        self.assertIn("rm -f \"$run_root/credentials.json\"", workflow)
        self.assertNotIn("credentials.json\n", workflow.split("path:")[1])


if __name__ == "__main__":
    unittest.main()
