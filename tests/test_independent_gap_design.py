from __future__ import annotations

import unittest

from aftermath_bench.independent_gap_design import build_independent_gap_design


class IndependentGapDesignTest(unittest.TestCase):
    def test_five_independent_effects_force_all_five_obligations(self) -> None:
        result = build_independent_gap_design(
            scenario_id="design",
            obligations={f"effect_{index}": (f"surface_{index}",) for index in range(5)},
        )
        self.assertTrue(result["passed_design_gate"])
        self.assertEqual(result["observed"]["variant_count"], 6)
        self.assertEqual(result["observed"]["minimum_static_certificate_size"], 5)
        self.assertEqual(
            result["observed"]["optimal_adaptive_worst_case_depth"], 5
        )

    def test_joined_obligations_count_underlying_public_surfaces(self) -> None:
        result = build_independent_gap_design(
            scenario_id="joined",
            obligations={
                "bundle": ("approval", "artifact"),
                "deployment": ("artifact", "deployment"),
                "attestation": ("deployment", "attestation"),
            },
        )
        self.assertEqual(result["observed"]["public_query_surface_count"], 4)
        self.assertEqual(result["observed"]["minimum_static_certificate_size"], 4)
        self.assertEqual(
            result["observed"]["optimal_adaptive_worst_case_depth"], 4
        )
        self.assertFalse(result["observed"]["single_surface_solvers"])


if __name__ == "__main__":
    unittest.main()
