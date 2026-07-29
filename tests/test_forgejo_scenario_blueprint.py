from __future__ import annotations

import json
import unittest

from aftermath_bench.schema import repository_root


class ForgejoScenarioBlueprintTest(unittest.TestCase):
    def test_blueprint_is_explicitly_unvalidated_and_counterfactual(self) -> None:
        path = (
            repository_root()
            / "data"
            / "scenario_blueprints"
            / "forgejo-pr-release-dev-001"
            / "scenario.json"
        )
        scenario = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(scenario["benchmark_tier"], "unvalidated")
        self.assertEqual(scenario["admission_status"], "unvalidated")
        variants = {
            item["id"] for item in scenario["matched_variants"]
        }
        self.assertEqual(len(variants), 4)
        self.assertIn(
            "merge_committed_receiver_accepted_response_lost",
            variants,
        )
        self.assertIn(
            "merge_committed_delivery_request_not_reached",
            variants,
        )
        tools = scenario["public_tool_policy"]
        self.assertFalse(tools["global_state_summary"])
        self.assertFalse(tools["recommended_action_tool"])


if __name__ == "__main__":
    unittest.main()
