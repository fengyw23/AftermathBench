from __future__ import annotations

import json
import unittest

from aftermath_bench.schema import repository_root


class KubernetesSettlementBlueprintTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        path = (
            repository_root()
            / "data"
            / "scenario_blueprints"
            / "k8s-cronjob-settlement-dev-001"
            / "scenario.json"
        )
        cls.scenario = json.loads(path.read_text(encoding="utf-8"))

    def test_blueprint_is_truthfully_retained_as_an_easy_control(self) -> None:
        self.assertEqual(self.scenario["benchmark_tier"], "easy")
        self.assertIn("rejected_from_hard", self.scenario["admission_status"])
        self.assertEqual(len(self.scenario["matched_variants"]), 4)

    def test_user_goal_exposes_every_scored_obligation(self) -> None:
        instruction = self.scenario["user_instruction"]
        for term in (
            "exactly one completed Kubernetes Job",
            "idempotency Lease",
            "one receiver delivery",
            "receipt ConfigMap",
            "settlement-ledger",
            "completed June settlement",
            "tax-export CronJob",
        ):
            self.assertIn(term, instruction)

    def test_tools_expose_evidence_without_recovery_answer(self) -> None:
        policy = self.scenario["public_tool_policy"]
        self.assertTrue(policy["ordinary_kubernetes_object_reads"])
        self.assertTrue(policy["pod_and_job_log_reads"])
        self.assertTrue(policy["ordinary_receiver_get_and_post"])
        self.assertFalse(policy["global_state_summary"])
        self.assertFalse(policy["recommended_action_tool"])
        self.assertFalse(policy["hidden_variant_label"])


if __name__ == "__main__":
    unittest.main()
