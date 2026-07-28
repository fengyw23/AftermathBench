import unittest

from scripts.summarize_final_experiment import compare


class FinalExperimentSummaryTest(unittest.TestCase):
    def test_accepts_a_large_valid_drop(self) -> None:
        result = compare(
            {
                "completed_runs": 20,
                "task_pass_rate": 0.95,
                "matched_group_success_rate": 0.8,
                "run_errors": [],
            },
            {
                "completed_runs": 20,
                "task_pass_rate": 0.35,
                "matched_group_success_rate": 0.0,
                "component_pass_rates": {"goal_completion": 1.0},
                "failure_type_counts": {
                    "investigation_failure": 13
                },
                "run_errors": [],
            },
        )
        self.assertTrue(result["primary_experiment_acceptance"])
        self.assertAlmostEqual(
            result["absolute_pass_rate_drop"],
            0.6,
        )

    def test_rejects_low_scores_caused_by_run_errors(self) -> None:
        result = compare(
            {
                "completed_runs": 20,
                "task_pass_rate": 1.0,
                "matched_group_success_rate": 1.0,
                "run_errors": [],
            },
            {
                "completed_runs": 19,
                "task_pass_rate": 0.1,
                "matched_group_success_rate": 0.0,
                "run_errors": ["provider timeout"],
            },
        )
        self.assertFalse(result["primary_experiment_acceptance"])
        self.assertFalse(
            result["checks"][
                "provider_and_runtime_errors_are_zero"
            ]
        )
        self.assertFalse(
            result["checks"]["holdout_has_20_completed_runs"]
        )


if __name__ == "__main__":
    unittest.main()
