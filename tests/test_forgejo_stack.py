from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from typing import Self
from unittest.mock import Mock, patch

from aftermath_bench.integrations.forgejo_stack import ForgejoStack
from scripts.manage_forgejo_stack import _administrator_password


class _ReadyResponse:
    status = 200

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_args: object) -> None:
        return None


class ForgejoStackTest(unittest.TestCase):
    def test_default_administrator_password_is_ephemeral(self) -> None:
        with (
            patch.dict(os.environ, {}, clear=True),
            patch(
                "scripts.manage_forgejo_stack.secrets.token_urlsafe",
                return_value="generated-ephemeral-password",
            ) as generate,
        ):
            password = _administrator_password()

        self.assertEqual(password, "generated-ephemeral-password")
        generate.assert_called_once_with(32)

    def test_explicit_administrator_password_is_preserved(self) -> None:
        with patch.dict(
            os.environ,
            {"AFTERMATH_FORGEJO_ADMIN_PASSWORD": "configured-password"},
            clear=True,
        ):
            password = _administrator_password()

        self.assertEqual(password, "configured-password")

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

    def test_create_administrator_returns_ephemeral_web_credentials(self) -> None:
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
        credentials = stack.create_administrator(
            password="ephemeral-test-password",
        )
        self.assertEqual(credentials["token"], "secret-token")
        self.assertEqual(credentials["username"], "aftermath")
        self.assertEqual(
            credentials["password"],
            "ephemeral-test-password",
        )
        self.assertEqual(
            credentials["web_base_url"],
            "http://127.0.0.1:8080",
        )
        self.assertEqual(
            credentials["base_url"],
            "http://127.0.0.1:8080/api/v1",
        )
        command = runner.call_args.args[0]
        self.assertIn("--access-token", command)
        self.assertIn("--access-token-scopes", command)

    def test_register_action_runner_uses_ephemeral_server_token(self) -> None:
        calls = []

        def runner(command, **kwargs):
            calls.append(tuple(command))
            stdout = "temporary-runner-token\n" if "generate-runner-token" in command else ""
            return subprocess.CompletedProcess(command, 0, stdout=stdout)

        stack = ForgejoStack(compose_file=Path("compose.yaml"), runner=runner)
        stack.register_action_runner()

        self.assertEqual(len(calls), 4)
        register = calls[1]
        self.assertIn("register", register)
        self.assertIn("temporary-runner-token", register)
        self.assertIn("aftermath-native:host", register)
        self.assertNotIn("/var/run/docker.sock", " ".join(register))
        self.assertIn("generate-config", " ".join(calls[2]))
        self.assertIn("runner-daemon", calls[3])

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

    def test_bundle_snapshot_and_restore_quiesce_all_services_together(
        self,
    ) -> None:
        calls = []

        def runner(command, **kwargs):
            calls.append(tuple(command))
            output = kwargs.get("stdout")
            if output is not None:
                output.write(b"archive")
            return subprocess.CompletedProcess(command, 0)

        stack = ForgejoStack(
            compose_file=Path("compose.yaml"),
            runner=runner,
        )
        stack.wait_ready = Mock()  # type: ignore[method-assign]
        stack.reset_service = Mock()  # type: ignore[method-assign]
        with tempfile.TemporaryDirectory() as directory:
            bundle = Path(directory) / "bundle"
            stack.snapshot_bundle(bundle)
            stack.restore_bundle(bundle)

        stop_calls = [
            call for call in calls if "stop" in call
        ]
        start_calls = [
            call for call in calls if "start" in call
        ]
        self.assertEqual(len(stop_calls), 2)
        self.assertEqual(len(start_calls), 2)
        for call in stop_calls:
            self.assertIn("--timeout", call)
            self.assertIn("2", call)
        for call in (*stop_calls, *start_calls):
            for service in (
                "forgejo",
                "api-fault-gateway",
                "webhook-sink",
                "webhook-fault-gateway",
                "provenance-webhook-fault-gateway",
            ):
                self.assertIn(service, call)
        reset_urls = {
            call.args[0]
            for call in stack.reset_service.call_args_list
        }
        self.assertNotIn("http://127.0.0.1:9092/admin/reset", reset_urls)

    def test_migration_bundle_preserves_runner_pause_and_both_databases(self) -> None:
        calls = []

        def runner(command, **kwargs):
            calls.append(tuple(command))
            output = kwargs.get("stdout")
            if output is not None:
                output.write(b"archive")
            return subprocess.CompletedProcess(command, 0)

        stack = ForgejoStack(compose_file=Path("compose.yaml"), runner=runner)
        stack.wait_ready = Mock()  # type: ignore[method-assign]
        stack.reset_service = Mock()  # type: ignore[method-assign]
        with tempfile.TemporaryDirectory() as directory:
            bundle = Path(directory) / "migration"
            manifest = stack.snapshot_migration_bundle(
                bundle, runner_enabled=False
            )
            stack.restore_migration_bundle(bundle)

        self.assertFalse(manifest["runner_enabled"])
        self.assertIn("deployment_target_sha256", manifest)
        start_calls = [call for call in calls if "start" in call]
        self.assertEqual(len(start_calls), 2)
        self.assertTrue(
            all("runner-daemon" not in call for call in start_calls)
        )
        self.assertTrue(
            any("deployment-target" in call for call in calls)
        )
        reset_urls = {
            call.args[0] for call in stack.reset_service.call_args_list
        }
        self.assertEqual(
            reset_urls,
            {
                "http://127.0.0.1:9091/admin/reset",
                "http://127.0.0.1:9096/admin/reset",
            },
        )


if __name__ == "__main__":
    unittest.main()
