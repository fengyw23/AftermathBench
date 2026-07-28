import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from aftermath_bench.integrations.erpnext_stack import (
    ERPNextStack,
    _parse_mapping_output,
)


class ERPNextStackTest(unittest.TestCase):
    def test_key_output_parser_accepts_bench_python_mapping(self) -> None:
        keys = _parse_mapping_output(
            "some log\n{'api_key': 'key-1', 'api_secret': 'secret-1'}\n"
        )
        self.assertEqual(keys["api_key"], "key-1")

    def test_stack_commands_are_project_and_file_scoped(self) -> None:
        runner = Mock(
            return_value=subprocess.CompletedProcess([], 0, stdout="")
        )
        stack = ERPNextStack(
            compose_file=Path("runtime/compose.yaml"),
            runner=runner,
        )
        stack.up()
        command = runner.call_args.args[0]
        self.assertEqual(command[0:2], ("docker", "compose"))
        self.assertIn("aftermath-erpnext", command)
        self.assertEqual(command[-3:], ("up", "--detach", "--build"))

    def test_setup_company_passes_one_argument_object_to_frappe(self) -> None:
        runner = Mock(
            return_value=subprocess.CompletedProcess([], 0, stdout="")
        )
        stack = ERPNextStack(
            compose_file=Path("runtime/compose.yaml"),
            runner=runner,
        )
        stack.setup_company()
        command = runner.call_args.args[0]
        kwargs = json.loads(command[command.index("--kwargs") + 1])
        self.assertEqual(set(kwargs), {"args"})
        self.assertEqual(kwargs["args"]["currency"], "USD")
        self.assertEqual(kwargs["args"]["company_abbr"], "AL")

    def test_remittance_requeue_calls_the_mounted_native_bridge(self) -> None:
        runner = Mock(
            return_value=subprocess.CompletedProcess(
                [],
                0,
                stdout=(
                    '{"job_id":"job-1","payment_entry":"PAY-1",'
                    '"webhook":"Aftermath Payment Remittance","queue":"short"}\n'
                ),
            )
        )
        stack = ERPNextStack(
            compose_file=Path("runtime/compose.yaml"),
            runner=runner,
        )

        result = stack.requeue_payment_remittance("PAY-1")

        command = runner.call_args.args[0]
        self.assertIn("PYTHONPATH=/opt/aftermath-bridge", command)
        self.assertIn(
            "aftermath_frappe_bridge.requeue_payment_remittance",
            command,
        )
        kwargs = json.loads(command[command.index("--kwargs") + 1])
        self.assertEqual(kwargs["payment_entry"], "PAY-1")
        self.assertEqual(result["job_id"], "job-1")

    def test_snapshot_writes_exact_dump_and_returns_digest(self) -> None:
        def runner(command, **kwargs):
            kwargs["stdout"].write(b"SQL-DUMP")
            return subprocess.CompletedProcess(command, 0)

        stack = ERPNextStack(
            compose_file=Path("runtime/compose.yaml"),
            runner=runner,
        )
        with tempfile.TemporaryDirectory() as directory:
            snapshot = Path(directory) / "baseline.sql"
            digest = stack.snapshot_database(snapshot)
            contents = snapshot.read_bytes()
        self.assertEqual(contents, b"SQL-DUMP")
        self.assertEqual(
            digest,
            "375f363a38dee36d85da50f28074820e62922163b99a1e61942d1c615fc2c5f0",
        )

    def test_reset_retries_until_restarted_service_is_ready(self) -> None:
        response = Mock()
        response.status = 200
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        opener = Mock(side_effect=[ConnectionResetError(), response])
        sleeper = Mock()

        ERPNextStack._reset_http_service(
            "http://127.0.0.1:9091/admin/reset",
            attempts=2,
            delay_seconds=0.01,
            opener=opener,
            sleeper=sleeper,
        )

        self.assertEqual(opener.call_count, 2)
        sleeper.assert_called_once_with(0.01)

    def test_erp_http_readiness_retries_a_transient_bad_gateway(self) -> None:
        response = Mock()
        response.status = 200
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        opener = Mock(side_effect=[ConnectionResetError(), response])
        sleeper = Mock()

        ERPNextStack._wait_http_service(
            "http://127.0.0.1:8080/api/method/ping",
            attempts=2,
            delay_seconds=0.01,
            opener=opener,
            sleeper=sleeper,
        )

        requests = [call.args[0] for call in opener.call_args_list]
        self.assertTrue(all(request.method == "GET" for request in requests))
        sleeper.assert_called_once_with(0.01)

    def test_reset_fails_after_bounded_readiness_attempts(self) -> None:
        opener = Mock(side_effect=ConnectionRefusedError())
        sleeper = Mock()

        with self.assertRaisesRegex(
            RuntimeError,
            "did not become ready after 3 attempts",
        ):
            ERPNextStack._reset_http_service(
                "http://127.0.0.1:9091/admin/reset",
                attempts=3,
                delay_seconds=0,
                opener=opener,
                sleeper=sleeper,
            )

        self.assertEqual(opener.call_count, 3)
        self.assertEqual(sleeper.call_count, 2)


if __name__ == "__main__":
    unittest.main()
