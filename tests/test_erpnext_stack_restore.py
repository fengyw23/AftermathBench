from __future__ import annotations

import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from aftermath_bench.integrations.erpnext_stack import ERPNextStack


class ERPNextStackRestoreTest(unittest.TestCase):
    def test_restore_keeps_stateless_http_services_running(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            snapshot = root / "prefix.sql"
            snapshot.write_bytes(b"-- deterministic test snapshot\n")
            commands: list[tuple[str, ...]] = []

            def runner(command, **kwargs):
                commands.append(tuple(command))
                return subprocess.CompletedProcess(command, 0, "", "")

            stack = ERPNextStack(
                compose_file=root / "compose.yaml",
                runner=runner,
            )
            stack._wait_http_service = (  # type: ignore[method-assign]
                lambda *args, **kwargs: None
            )
            stack._reset_http_service = (  # type: ignore[method-assign]
                lambda *args, **kwargs: None
            )
            stack.restore_database(snapshot)

            stop = next(
                command for command in commands if "stop" in command
            )
            start = next(
                command for command in commands if "start" in command
            )
            self.assertEqual(
                stop[-3:],
                ("stop", "queue-short", "queue-long"),
            )
            self.assertEqual(
                start[-3:],
                ("start", "queue-short", "queue-long"),
            )
            for service in (
                "backend",
                "frontend",
                "fault-gateway",
                "websocket",
            ):
                self.assertNotIn(service, stop)
                self.assertNotIn(service, start)


if __name__ == "__main__":
    unittest.main()
