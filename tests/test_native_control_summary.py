from __future__ import annotations

import unittest

from scripts.validate_native_control_summary import validate_control_summary


class NativeControlSummaryTests(unittest.TestCase):
    def test_accepts_complete_control_above_threshold(self) -> None:
        summary = {
            "completed_runs": 8,
            "run_errors": [],
            "task_pass_rate": 0.875,
            "execution_control_counts": {"true": 8},
        }

        self.assertEqual(
            validate_control_summary(
                summary,
                expected_cases=8,
                minimum_pass_rate=0.8,
            ),
            [],
        )

    def test_rejects_failed_or_incomplete_control(self) -> None:
        summary = {
            "completed_runs": 7,
            "run_errors": ["missing"],
            "task_pass_rate": 0.5,
            "execution_control_counts": {"true": 6, "false": 1},
        }

        self.assertEqual(
            validate_control_summary(
                summary,
                expected_cases=8,
                minimum_pass_rate=0.8,
            ),
            [
                "completed_runs",
                "run_errors",
                "task_pass_rate",
                "execution_control_counts",
            ],
        )


if __name__ == "__main__":
    unittest.main()
