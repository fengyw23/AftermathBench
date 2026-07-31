from __future__ import annotations

import hashlib
import json
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from aftermath_bench.integrations.erpnext_stack import ERPNextStack


class ERPNextStackBundleTest(unittest.TestCase):
    def test_failed_snapshot_removes_incomplete_directory(self) -> None:
        commands: list[tuple[str, ...]] = []

        def runner(command, **kwargs):
            command = tuple(command)
            commands.append(command)
            if "ps" in command and "--services" in command:
                return subprocess.CompletedProcess(
                    command,
                    0,
                    (
                        "redis-queue\nqueue-fault\nbackend\n"
                        "queue-short\nqueue-long\nfault-gateway\n"
                        "remittance\n"
                    ),
                    "",
                )
            if "mariadb-dump" in command:
                kwargs["stdout"].write(b"database-state")
            elif "tar -C /data -cf - ." in command:
                raise subprocess.CalledProcessError(1, command)
            return subprocess.CompletedProcess(command, 0, "", "")

        with TemporaryDirectory() as directory:
            root = Path(directory)
            stack = ERPNextStack(
                compose_file=root / "compose.yaml",
                runner=runner,
            )
            stack._wait_http_service = (  # type: ignore[method-assign]
                lambda *args, **kwargs: None
            )
            destination = root / "failed-boundary"
            with self.assertRaises(subprocess.CalledProcessError):
                stack.snapshot_bundle(destination)
            self.assertFalse(destination.exists())
            self.assertEqual(
                list(root.glob(".failed-boundary.incomplete-*")),
                [],
            )
        resume = [
            command
            for command in commands
            if "up" in command and "--no-deps" in command
        ]
        self.assertEqual(len(resume), 3)
        self.assertTrue(
            all("--no-recreate" in command for command in resume)
        )
        self.assertEqual(resume[0][-1], "redis-queue")
        self.assertEqual(resume[1][-1], "queue-fault")
        self.assertIn("backend", resume[2])

    def test_snapshot_preserves_a_pending_boundary_worker_state(self) -> None:
        commands: list[tuple[str, ...]] = []

        def runner(command, **kwargs):
            command = tuple(command)
            commands.append(command)
            if "ps" in command and "--services" in command:
                return subprocess.CompletedProcess(
                    command,
                    0,
                    (
                        "redis-queue\nqueue-fault\nbackend\n"
                        "fault-gateway\nremittance\n"
                    ),
                    "",
                )
            if "mariadb-dump" in command:
                kwargs["stdout"].write(b"database-state")
            elif "tar -C /data -cf - ." in command:
                kwargs["stdout"].write(b"archive")
            return subprocess.CompletedProcess(command, 0, "", "")

        with TemporaryDirectory() as directory:
            root = Path(directory)
            stack = ERPNextStack(
                compose_file=root / "compose.yaml",
                runner=runner,
            )
            stack._wait_http_service = (  # type: ignore[method-assign]
                lambda *args, **kwargs: None
            )
            manifest = stack.snapshot_bundle(root / "pending")

        self.assertNotIn("queue-short", manifest["running_services"])
        self.assertNotIn("queue-long", manifest["running_services"])
        resume = [
            command
            for command in commands
            if "up" in command and "--no-deps" in command
        ]
        self.assertEqual(len(resume), 3)
        self.assertNotIn("queue-short", resume[-1])
        self.assertNotIn("queue-long", resume[-1])
        self.assertIn("--no-recreate", resume[-1])

    def test_snapshot_quiesces_and_hashes_every_mutable_service(self) -> None:
        commands: list[tuple[str, ...]] = []

        def runner(command, **kwargs):
            command = tuple(command)
            commands.append(command)
            stdout = ""
            if "ps" in command and "--services" in command:
                stdout = "\n".join(
                    (
                        "redis-queue",
                        "queue-fault",
                        "backend",
                        "queue-short",
                        "queue-long",
                        "fault-gateway",
                        "remittance",
                    )
                )
            if "mariadb-dump" in command:
                kwargs["stdout"].write(b"database-state")
            elif "tar -C /data -cf - ." in command:
                service = command[command.index("--entrypoint") + 2]
                kwargs["stdout"].write(f"archive:{service}".encode())
            return subprocess.CompletedProcess(command, 0, stdout, "")

        with TemporaryDirectory() as directory:
            root = Path(directory)
            stack = ERPNextStack(
                compose_file=root / "compose.yaml",
                runner=runner,
            )
            stack._wait_http_service = (  # type: ignore[method-assign]
                lambda *args, **kwargs: None
            )
            bundle = root / "boundary"
            manifest = stack.snapshot_bundle(bundle)

            self.assertEqual(
                manifest["capture_mode"],
                "simultaneous_service_quiescence",
            )
            self.assertEqual(
                set(manifest["files"]),
                {
                    "database",
                    "redis_queue",
                    "gateway_audit",
                    "remittance_audit",
                },
            )
            for declaration in manifest["files"].values():
                path = bundle / declaration["path"]
                self.assertEqual(path.stat().st_size, declaration["bytes"])
                self.assertEqual(
                    hashlib.sha256(path.read_bytes()).hexdigest(),
                    declaration["sha256"],
                )
            self.assertEqual(
                json.loads((bundle / "bundle.json").read_text()),
                manifest,
            )

        stop = next(command for command in commands if "stop" in command)
        self.assertTrue(
            {
                "backend",
                "queue-short",
                "queue-long",
                "fault-gateway",
                "remittance",
                "queue-fault",
                "redis-queue",
            }
            <= set(stop)
        )
        starts = [
            command
            for command in commands
            if "up" in command and "--no-deps" in command
        ]
        self.assertEqual(len(starts), 3)
        self.assertLess(
            commands.index(starts[0]),
            commands.index(starts[1]),
        )
        self.assertLess(
            commands.index(starts[1]),
            commands.index(starts[2]),
        )
        self.assertEqual(starts[0][-1], "redis-queue")
        self.assertIn("--wait", starts[0])
        self.assertEqual(starts[1][-1], "queue-fault")
        self.assertIn("backend", starts[2])
        self.assertIn("queue-short", starts[2])
        self.assertIn("--no-recreate", starts[2])

    def test_restore_verifies_hashes_before_replacing_native_state(self) -> None:
        commands: list[tuple[str, ...]] = []
        restored_inputs: list[bytes] = []

        def runner(command, **kwargs):
            command = tuple(command)
            commands.append(command)
            if "stdin" in kwargs:
                restored_inputs.append(kwargs["stdin"].read())
            return subprocess.CompletedProcess(command, 0, "", "")

        with TemporaryDirectory() as directory:
            root = Path(directory)
            bundle = root / "boundary"
            bundle.mkdir()
            payloads = {
                "database": ("database.sql", b"database-state"),
                "redis_queue": ("redis-queue.tar", b"redis-state"),
                "gateway_audit": ("gateway-audit.tar", b"gateway-state"),
                "remittance_audit": (
                    "remittance-audit.tar",
                    b"delivery-state",
                ),
            }
            files = {}
            for key, (name, content) in payloads.items():
                (bundle / name).write_bytes(content)
                files[key] = {
                    "path": name,
                    "bytes": len(content),
                    "sha256": hashlib.sha256(content).hexdigest(),
                }
            manifest = {
                "schema_version": "1.0",
                "capture_mode": "simultaneous_service_quiescence",
                "running_services": [
                    "redis-queue",
                    "queue-fault",
                    "backend",
                    "queue-short",
                    "queue-long",
                    "fault-gateway",
                    "remittance",
                ],
                "files": files,
            }
            (bundle / "bundle.json").write_text(
                json.dumps(manifest),
                encoding="utf-8",
            )
            stack = ERPNextStack(
                compose_file=root / "compose.yaml",
                runner=runner,
            )
            stack._wait_http_service = (  # type: ignore[method-assign]
                lambda *args, **kwargs: None
            )

            self.assertEqual(stack.restore_bundle(bundle), manifest)
            self.assertEqual(
                restored_inputs,
                [
                    b"database-state",
                    b"redis-state",
                    b"gateway-state",
                    b"delivery-state",
                ],
            )
            self.assertTrue(
                all(
                    "find /data -mindepth 1" in command
                    for command in commands
                    if "tar -C /data -xf -" in command
                )
            )
            starts = [
                command
                for command in commands
                if "up" in command and "--no-deps" in command
            ]
            self.assertEqual(len(starts), 3)
            self.assertEqual(starts[0][-1], "redis-queue")
            self.assertEqual(starts[1][-1], "queue-fault")
            self.assertIn("backend", starts[2])
            self.assertIn("--no-recreate", starts[2])

            commands.clear()
            (bundle / "redis-queue.tar").write_bytes(b"drift")
            with self.assertRaisesRegex(
                ValueError,
                "bundle file drift: redis_queue",
            ):
                stack.restore_bundle(bundle)
            self.assertEqual(commands, [])


if __name__ == "__main__":
    unittest.main()
