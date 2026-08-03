from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BLUEPRINT = (
    ROOT
    / "data"
    / "scenario_blueprints"
    / "erpnext-multiwarehouse-transfer-dev-001"
    / "scenario.json"
)


class ERPNextMultiwarehouseBlueprintTests(unittest.TestCase):
    def test_blueprint_matches_frozen_matrix_family(self) -> None:
        scenario = json.loads(BLUEPRINT.read_text(encoding="utf-8"))
        matrix = json.loads(
            (ROOT / "data" / "benchmark_matrix.json").read_text(encoding="utf-8")
        )
        family = next(
            family
            for domain in matrix["domains"]
            if domain["domain_id"] == "erpnext"
            for family in domain["families"]
            if family["family_id"] == scenario["family"]
        )

        self.assertEqual(scenario["scenario_id"], "erpnext-multiwarehouse-transfer-dev-001")
        self.assertEqual(scenario["runtime_id"], "erpnext-v15")
        self.assertFalse(scenario["hidden_test_eligible"])
        self.assertEqual(len(scenario["matched_variants"]), 4)
        self.assertGreaterEqual(
            len(
                {
                    variant["recovery_signature_class"]
                    for variant in scenario["matched_variants"]
                }
            ),
            family["variant_profile"]["minimum_recovery_signatures"],
        )
        self.assertGreaterEqual(
            len(
                {
                    variant["boundary_class_id"]
                    for variant in scenario["matched_variants"]
                }
            ),
            family["variant_profile"]["minimum_boundary_classes"],
        )
        self.assertEqual(
            set(scenario["required_semantic_recovery_directions"]),
            set(family["required_recovery_signatures"]),
        )

    def test_task_requires_native_stock_preservation(self) -> None:
        scenario = json.loads(BLUEPRINT.read_text(encoding="utf-8"))
        instruction = scenario["user_instruction"]
        self.assertIn("submitted first-leg Stock Entry", instruction)
        self.assertIn("exact units", instruction)
        self.assertIn("reservation", instruction)
        self.assertIn("Preserve", instruction)
        self.assertFalse(scenario["public_tool_policy"]["global_state_summary"])
        self.assertFalse(scenario["public_tool_policy"]["recommended_action_tool"])


if __name__ == "__main__":
    unittest.main()
