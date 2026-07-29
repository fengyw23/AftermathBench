from __future__ import annotations

import subprocess
import unittest
from pathlib import Path
from typing import Self
from unittest.mock import Mock

from aftermath_bench.integrations.forgejo_stack import ForgejoStack


class _ReadyResponse:
    status = 200

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_args: object) -> None:
        return None


class ForgejoStackTest(unittest.TestCase):
    def test_compose_commands_are_scoped_to_the_runtime_project(self) -> None:
        runner = Mock(return_value=subprocess.CompletedProcess([], 0))
        stack = ForgejoStack(
            compose_file=Path("runtimes/forgejo/compose.yaml"),
            runner=runner,
        )
        stack.down(remove_volumes=True)
        command = runner.call_args.args[0]
        self.assertEqual(command[:4], (
            "docker",
            "compose",
            "--project-name",
            "aftermath-forgejo",
        ))
        self.assertIn("--volumes", command)

    def test_create_administrator_extracts_only_the_token(self) -> None:
        runner = Mock(
            return_value=subprocess.CompletedProcess(
                [],
                0,
                stdout=(
                    "New user 'aftermath' has been successfully created!\n"
                    "Access token was successfully created... secret-token\n"
                ),
            )
        )
        stack = ForgejoStack(
            compose_file=Path("compose.yaml"),
            runner=runner,
        )
        credentials = stack.create_administrator()
        self.assertEqual(credentials["token"], "secret-token")
        self.assertEqual(
            credentials["base_url"],
            "http://127.0.0.1:8080/api/v1",
        )
        command = runner.call_args.args[0]
        self.assertIn("--access-token", command)
        self.assertIn("--access-token-scopes", command)

    def test_readiness_retries_transient_connection_errors(self) -> None:
        ready = _ReadyResponse()
        opener = Mock(side_effect=[OSError("starting"), ready])
        sleeper = Mock()
        ForgejoStack.wait_for_url(
            "http://example.invalid/health",
            attempts=2,
            delay_seconds=0,
            opener=opener,
            sleeper=sleeper,
        )
        self.assertEqual(opener.call_count, 2)
        sleeper.assert_called_once_with(0)


if __name__ == "__main__":
    unittest.main()
