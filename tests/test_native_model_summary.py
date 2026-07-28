import json
import tempfile
import unittest
from pathlib import Path

from scripts.summarize_native_model_runs import summarize


class NativeModelSummaryTest(unittest.TestCase):
    def test_aggregates_matched_group_and_failure_types(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_dir = root / "repetition-01"
            run_dir.mkdir()
            variants = (
                "request_not_reached",
                "database_committed_response_lost",
                "after_commit_enqueue_failed",
                "async_job_pending",
            )
            for index, variant in enumerate(variants):
                (run_dir / f"{variant}.json").write_text(
                    json.dumps(
                        {
                            "scenario_id": "hard-1",
                            "variant": variant,
                            "evaluation": {
                                "passed": index != 0,
                                "components": {
                                    "goal_completion": index != 0
                                },
                            },
                            "trajectory_diagnostics": {
                                "primary_error": (
                                    "investigation_failure"
                                    if index == 0
                                    else None
                                )
                            },
                        }
                    ),
                    encoding="utf-8",
                )
            summary = summarize(root)
        self.assertEqual(summary["completed_runs"], 4)
        self.assertEqual(summary["task_pass_rate"], 0.75)
        self.assertEqual(summary["matched_group_success_rate"], 0)
        self.assertEqual(
            summary["failure_type_counts"],
            {"investigation_failure": 1},
        )


if __name__ == "__main__":
    unittest.main()
