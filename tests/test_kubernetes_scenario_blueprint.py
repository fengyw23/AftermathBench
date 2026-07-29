from __future__ import annotations

import json
import unittest

from aftermath_bench.schema import repository_root


class KubernetesScenarioBlueprintTest(unittest.TestCase):
    def test_blueprint_is_counterfactual_and_explicitly_unvalidated(self) -> None:
        path = (
            repository_root()
            / "data"
            / "scenario_blueprints"
            / "k8s-deployment-rollout-dev-001"
            / "scenario.json"
        )
        scenario = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(scenario["benchmark_tier"], "unvalidated")
        self.assertEqual(scenario["admission_status"], "unvalidated")
        variants = {
            item["id"] for item in scenario["matched_variants"]
        }
        self.assertEqual(
            variants,
            {
                "patch_request_not_reached",
                "deployment_spec_committed_response_lost",
                "deployment_spec_committed_reconcile_paused",
                "new_replicaset_created_rollout_pending",
            },
        )
        tools = scenario["public_tool_policy"]
        self.assertFalse(tools["global_state_summary"])
        self.assertFalse(tools["recommended_action_tool"])
        self.assertFalse(tools["hidden_variant_label"])

    def test_blueprint_requires_cross_controller_evidence(self) -> None:
        path = (
            repository_root()
            / "data"
            / "scenario_blueprints"
            / "k8s-deployment-rollout-dev-001"
            / "scenario.json"
        )
        scenario = json.loads(path.read_text(encoding="utf-8"))
        evidence = " ".join(scenario["required_public_evidence"])
        for term in (
            "Deployment",
            "ReplicaSet",
            "Pod",
            "Service",
            "EndpointSlice",
            "HorizontalPodAutoscaler",
            "PodDisruptionBudget",
            "Events",
        ):
            self.assertIn(term, evidence)


if __name__ == "__main__":
    unittest.main()
