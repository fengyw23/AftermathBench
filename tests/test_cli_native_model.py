import sys
import unittest
from unittest.mock import patch

from aftermath_bench import cli


class NativeModelCLIForwardingTest(unittest.TestCase):
    def test_execution_control_flag_reaches_native_runner(self) -> None:
        report = {
            "run_id": "control-run",
            "evaluation": {"passed": True},
            "trajectory_diagnostics": {},
            "stop_reason": "model_stopped",
        }
        argv = [
            "aftermath-bench",
            "run-native-model",
            "--provider",
            "openai-compatible",
            "--model",
            "test-model",
            "--scenario",
            "scenario.json",
            "--credentials",
            "credentials.json",
            "--prefix",
            "prefix.json",
            "--failure-report",
            "failure.json",
            "--execution-control",
            "--output",
            "trajectory.json",
        ]
        with (
            patch.object(sys, "argv", argv),
            patch.object(cli, "client_from_environment") as client_factory,
            patch.object(
                cli,
                "run_live_native_agent",
                return_value=report,
            ) as runner,
        ):
            self.assertEqual(cli.main(), 0)

        self.assertIs(
            runner.call_args.kwargs["execution_control"],
            True,
        )
        self.assertIs(
            client_factory.call_args.kwargs["model"],
            "test-model",
        )

    def test_easy_model_command_does_not_forward_native_only_control(
        self,
    ) -> None:
        report = {
            "run_id": "easy-run",
            "evaluation": {"passed": True},
            "trajectory_diagnostics": {},
            "stop_reason": "model_stopped",
        }
        argv = [
            "aftermath-bench",
            "run-erpnext-model",
            "--provider",
            "openai-compatible",
            "--model",
            "test-model",
            "--variant",
            "request_not_reached",
            "--credentials",
            "credentials.json",
            "--prefix",
            "prefix.json",
            "--failure-report",
            "failure.json",
            "--output",
            "trajectory.json",
        ]
        with (
            patch.object(sys, "argv", argv),
            patch.object(cli, "client_from_environment"),
            patch.object(
                cli,
                "run_live_erpnext_agent",
                return_value=report,
            ) as runner,
            patch("builtins.print"),
        ):
            self.assertEqual(cli.main(), 0)

        self.assertNotIn(
            "execution_control",
            runner.call_args.kwargs,
        )


if __name__ == "__main__":
    unittest.main()
