from __future__ import annotations

import unittest

from aftermath_bench.scope_decision_audit import analyze_scope_decision_matrix


class ScopeDecisionAuditTest(unittest.TestCase):
    def test_detects_a_single_query_scope_solver(self) -> None:
        audit = analyze_scope_decision_matrix(
            {
                "rows": [
                    {
                        "variant": "valid",
                        "recovery_signature": "preserve",
                        "observations": {"inventory": "valid", "policy": "same"},
                    },
                    {
                        "variant": "corrupt",
                        "recovery_signature": "rebuild",
                        "observations": {"inventory": "corrupt", "policy": "same"},
                    },
                ]
            }
        )
        self.assertTrue(audit.identifiable)
        self.assertEqual(audit.minimum_static_certificate_size, 1)
        self.assertEqual(audit.optimal_adaptive_worst_case_depth, 1)
        self.assertEqual(audit.single_surface_solvers, ("inventory",))

    def test_two_independent_facts_require_depth_two(self) -> None:
        rows = []
        for package in ("missing", "present"):
            for delivery in ("missing", "present"):
                rows.append(
                    {
                        "variant": f"{package}-{delivery}",
                        "recovery_signature": f"{package}-{delivery}",
                        "observations": {
                            "package": package,
                            "delivery": delivery,
                            "constant": "same",
                        },
                    }
                )
        audit = analyze_scope_decision_matrix({"rows": rows})
        self.assertEqual(audit.minimum_static_certificate_size, 2)
        self.assertEqual(audit.optimal_adaptive_worst_case_depth, 2)
        self.assertEqual(audit.single_surface_solvers, ())

    def test_rejects_indistinguishable_different_scopes(self) -> None:
        audit = analyze_scope_decision_matrix(
            {
                "rows": [
                    {
                        "variant": "a",
                        "recovery_signature": "keep",
                        "observations": {"state": "same"},
                    },
                    {
                        "variant": "b",
                        "recovery_signature": "replace",
                        "observations": {"state": "same"},
                    },
                ]
            }
        )
        self.assertFalse(audit.identifiable)
        self.assertIsNone(audit.minimum_static_certificate_size)
        self.assertIsNone(audit.optimal_adaptive_worst_case_depth)
        self.assertEqual(audit.indistinguishable_variant_pairs, (("a", "b"),))

    def test_requires_complete_surface_matrix(self) -> None:
        with self.assertRaisesRegex(ValueError, "same surfaces"):
            analyze_scope_decision_matrix(
                {
                    "rows": [
                        {
                            "variant": "a",
                            "recovery_signature": "keep",
                            "observations": {"state": 1},
                        },
                        {
                            "variant": "b",
                            "recovery_signature": "replace",
                            "observations": {"other": 2},
                        },
                    ]
                }
            )


if __name__ == "__main__":
    unittest.main()
