from __future__ import annotations

import unittest
from pathlib import Path

from aftermath_bench.integrations.kubernetes_interaction_faults import SURFACE_ERROR
from aftermath_bench.integrations.kubernetes_interaction_scope import (
    INTERACTION_VARIANT_FACTS,
)
from aftermath_bench.kubernetes_interaction_prompt_audit import (
    build_interaction_prompt_audit,
)
from aftermath_bench.native_admission import _constraint_prompt_admission
from aftermath_bench.native_scenario import load_native_scenario


class KubernetesInteractionPromptAuditTest(unittest.TestCase):
    def test_complete_ordinary_surface_has_no_scope_leak(self) -> None:
        scenario = load_native_scenario(
            Path(
                "data/scenario_blueprints/"
                "k8s-constraint-interactions-dev-005/scenario.json"
            )
        )
        audit = build_interaction_prompt_audit(
            scenario,
            variant_facts=INTERACTION_VARIANT_FACTS,
            prefix_trace=[],
            visible_failure={"ok": False, "error": SURFACE_ERROR},
        )
        checks, observed = _constraint_prompt_admission(
            audit,
            minimum_counterfactual_flips=8,
            expected_variants=set(scenario.variants),
        )
        self.assertTrue(all(checks.values()), checks)
        self.assertEqual(observed["ordinary_direction_label_leak_count"], 0)
        self.assertGreaterEqual(observed["single_fact_direction_flip_count"], 8)
        self.assertEqual(observed["minimum_derivation_evidence_groups"], 6)


if __name__ == "__main__":
    unittest.main()
