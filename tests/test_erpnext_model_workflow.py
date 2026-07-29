import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from aftermath_bench.schema import repository_root
from scripts.summarize_erpnext_model_runs import summarize


class ERPNextModelWorkflowTest(unittest.TestCase):
    def test_workflow_runs_every_matched_state_and_uses_a_secret(self) -> None:
        workflow = (
            repository_root()
            / ".github"
            / "workflows"
            / "erpnext-model-pilot.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("secrets.BAILIAN_API_KEY", workflow)
        self.assertIn("run-erpnext-model", workflow)
        for variant in (
            "request_not_reached",
            "database_committed_response_lost",
            "after_commit_enqueue_failed",
            "async_job_pending",
        ):
            self.assertIn(variant, workflow)
        upload_section = workflow.split(
            "- name: Upload sanitized model trajectories",
            1,
        )[1]
        self.assertNotIn("credentials.json", upload_section)

    def test_hard_workflow_audits_the_control_condition(self) -> None:
        workflow = (
            repository_root()
            / ".github"
            / "workflows"
            / "erpnext-hard-model.yml"
        ).read_text(encoding="utf-8")
        self.assertIn(
            '--expected-execution-control "$EXECUTION_CONTROL"',
            workflow,
        )

    def test_sales_return_workflow_uses_native_family_runner(self) -> None:
        workflow = (
            repository_root()
            / ".github"
            / "workflows"
            / "erpnext-sales-return-model.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("secrets.BAILIAN_API_KEY", workflow)
        self.assertIn(
            "ws-ogjwl5f71op9q2jf.cn-beijing.maas.aliyuncs.com/"
            "compatible-mode/v1",
            workflow,
        )
        self.assertIn("run_erpnext_sales_return_failure.py", workflow)
        self.assertIn("run-native-model", workflow)
        self.assertIn(
            '--expected-execution-control "$EXECUTION_CONTROL"',
            workflow,
        )
        for variant in (
            "request_not_reached",
            "database_committed_response_lost",
            "after_commit_enqueue_failed",
            "async_job_pending",
        ):
            self.assertIn(variant, workflow)
        upload_section = workflow.split(
            "- name: Upload sanitized trajectories",
            1,
        )[1]
        self.assertNotIn("credentials.json", upload_section)

    def test_final_experiment_is_one_job_with_frozen_holdout(self) -> None:
        workflow = (
            repository_root()
            / ".github"
            / "workflows"
            / "erpnext-final-experiment.yml"
        ).read_text(encoding="utf-8")
        self.assertEqual(
            workflow.count(
                "python scripts/build_erpnext_runtime.py"
            ),
            1,
        )
        self.assertIn(
            "Run easy pilot, four variants by five repetitions",
            workflow,
        )
        self.assertIn(
            "Run frozen holdout, four variants by five repetitions",
            workflow,
        )
        self.assertIn("verify_native_freeze.py", workflow)
        self.assertIn("summarize_final_experiment.py", workflow)
        self.assertIn("test \"$requested_repetitions\" -eq 5", workflow)
        self.assertIn("provider_profile:", workflow)
        self.assertIn("default: bailian", workflow)
        self.assertIn("secrets.BAILIAN_API_KEY", workflow)
        self.assertIn("secrets.PARATERA_API_KEY", workflow)
        self.assertIn("https://llmapi.paratera.com/v1", workflow)
        self.assertIn(
            "AFTERMATH_API_KEY=$selected_api_key",
            workflow,
        )
        self.assertIn("for attempt in 1 2", workflow)
        self.assertIn("sleep 30", workflow)
        self.assertIn(
            '${variant}-attempt-${attempt}.log',
            workflow,
        )
        self.assertNotIn(
            "\n                    --execution-control",
            workflow,
        )

    def test_summary_distinguishes_task_failure_from_run_error(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            for repetition in (1,):
                run_dir = root / f"repetition-{repetition:02d}"
                run_dir.mkdir(parents=True)
                for index, variant in enumerate(
                    (
                        "request_not_reached",
                        "database_committed_response_lost",
                        "after_commit_enqueue_failed",
                        "async_job_pending",
                    )
                ):
                    report = {
                        "variant": variant,
                        "evaluation": {
                            "passed": index != 0,
                            "checks": {"complete": index != 0},
                        },
                        "turns": [{}, {}],
                        "stop_reason": "model_stopped",
                        "trajectory_diagnostics": {
                            "selected_mutations": [],
                            "inspected_payment_state": True,
                            "inspected_remittance_state": index != 0,
                            "unsafe_submit_retry": False,
                            "unnecessary_remittance_requeue": False,
                            "tool_error_count": 0,
                        },
                    }
                    (run_dir / f"{variant}.json").write_text(
                        json.dumps(report),
                        encoding="utf-8",
                    )
            summary = summarize(root)
            self.assertEqual(summary["completed_runs"], 4)
            self.assertEqual(summary["run_errors"], 0)
            self.assertEqual(summary["task_pass_rate"], 0.75)
            self.assertEqual(summary["matched_group_success_rate"], 0)

    def test_easy_summary_counts_a_missing_trajectory_as_run_error(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            run_dir = root / "repetition-01"
            run_dir.mkdir(parents=True)
            for variant in (
                "request_not_reached",
                "database_committed_response_lost",
                "after_commit_enqueue_failed",
            ):
                (run_dir / f"{variant}.json").write_text(
                    json.dumps(
                        {
                            "variant": variant,
                            "evaluation": {
                                "passed": True,
                                "checks": {"complete": True},
                            },
                        }
                    ),
                    encoding="utf-8",
                )
            summary = summarize(root)
        self.assertEqual(summary["completed_runs"], 3)
        self.assertEqual(summary["run_errors"], 1)
        missing = [
            run
            for run in summary["runs"]
            if run["status"] == "run_error"
        ]
        self.assertEqual(len(missing), 1)
        self.assertEqual(
            missing[0]["variant"],
            "async_job_pending",
        )


if __name__ == "__main__":
    unittest.main()
