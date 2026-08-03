from __future__ import annotations

import unittest

from scripts.summarize_frozen_candidate import (
    execution_control_status,
    fixed_policy_status,
)


class FrozenCandidateSummaryTests(unittest.TestCase):
    def test_native_heuristic_rows_are_summarized_without_legacy_fields(self) -> None:
        maximum, solvers = fixed_policy_status(
            {
                "heuristics": [
                    {
                        "name": "no_op",
                        "pass_rate": 0.0,
                        "matched_group_success": False,
                    },
                    {
                        "name": "assume",
                        "pass_rate": 0.25,
                        "matched_group_success": False,
                    },
                ]
            }
        )
        self.assertEqual(maximum, 0.25)
        self.assertEqual(solvers, 0)

    def test_consumed_run_without_summary_is_attempted_incomplete(self) -> None:
        self.assertEqual(
            execution_control_status(
                control=None,
                usage_events=[
                    "frozen",
                    "evaluation_locked",
                    "consumed",
                ],
                expected_cases=8,
            ),
            ("attempted_incomplete", False),
        )

    def test_complete_control_must_pass_all_structural_gates(self) -> None:
        status = execution_control_status(
            control={
                "completed_runs": 8,
                "run_errors": [],
                "task_pass_rate": 0.875,
                "execution_control_counts": {"true": 8},
            },
            usage_events=["frozen", "evaluation_locked", "consumed"],
            expected_cases=8,
        )

        self.assertEqual(status, ("completed_gate_pass", True))


if __name__ == "__main__":
    unittest.main()
