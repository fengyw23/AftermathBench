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


if __name__ == "__main__":
    unittest.main()
