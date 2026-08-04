from __future__ import annotations

import unittest

from aftermath_bench.integrations.forgejo_interacting_recovery_design import (
    FORGEJO_INTERACTING_VARIANTS,
    FORGEJO_INTERACTING_WORKFLOW_INPUTS,
    build_forgejo_interacting_recovery_design,
)


class ForgejoInteractingRecoveryDesignTest(unittest.TestCase):
    def test_design_requires_composed_context_sensitive_native_actions(self) -> None:
        report = build_forgejo_interacting_recovery_design()
        self.assertTrue(report["passed_design_gate"], report)
        self.assertEqual(len(FORGEJO_INTERACTING_VARIANTS), 9)
        self.assertGreaterEqual(
            report["observed"]["multi_action_variant_count"], 7
        )
        self.assertGreaterEqual(
            report["observed"]["maximum_minimal_plan_length"], 3
        )
        self.assertGreaterEqual(
            len(report["observed"]["effect_overlap_pairs"]), 8
        )

    def test_every_declared_workflow_action_has_real_resume_inputs(self) -> None:
        for name, inputs in FORGEJO_INTERACTING_WORKFLOW_INPUTS.items():
            if name == "publish_metadata":
                self.assertIsNone(inputs)
                continue
            self.assertIsInstance(inputs, dict)
            self.assertIn(inputs["resume_stage"], {
                "start",
                "after_artifact",
                "after_bundle",
                "after_deployment",
            })
            self.assertIn(inputs["stop_after"], {
                "artifact",
                "bundle",
                "deployment",
                "none",
            })


if __name__ == "__main__":
    unittest.main()
