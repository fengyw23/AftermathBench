from __future__ import annotations

import hashlib
import io
import json
import subprocess
import tarfile
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
                        "queue-short\nqueue-long\nwebsocket\nfrontend\n"
                        "fault-gateway\n"
                        "remittance\n"
                    ),
                    "",
                )
            if "mariadb-dump" in command:
                kwargs["stdout"].write(b"database-state")
            elif "cat /home/frappe/frappe-bench/sites/" in command[-1]:
                return subprocess.CompletedProcess(
                    command,
                    0,
                    '{"db_password":"fresh","encryption_key":"source-key"}',
                    "",
                )
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
        self.assertEqual(len(resume), 5)
        self.assertTrue(all("--no-recreate" in command for command in resume))
        self.assertEqual(resume[0][-1], "redis-queue")
        self.assertEqual(resume[1][-1], "queue-fault")
        self.assertIn("backend", resume[2])
        self.assertIn("websocket", resume[2])
        self.assertEqual(resume[3][-1], "frontend")
        self.assertIn("fault-gateway", resume[4])

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
                        "websocket\nfrontend\nfault-gateway\nremittance\n"
                    ),
                    "",
                )
            if "mariadb-dump" in command:
                kwargs["stdout"].write(b"database-state")
            elif "cat /home/frappe/frappe-bench/sites/" in command[-1]:
                return subprocess.CompletedProcess(
                    command,
                    0,
                    '{"db_password":"fresh","encryption_key":"source-key"}',
                    "",
                )
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
        self.assertEqual(len(resume), 5)
        self.assertNotIn("queue-short", resume[2])
        self.assertNotIn("queue-long", resume[2])
        self.assertIn("websocket", resume[2])
        self.assertEqual(resume[3][-1], "frontend")
        self.assertIn("--no-recreate", resume[-1])

    def test_snapshot_quiesces_and_hashes_every_mutable_service(self) -> None:
        commands: list[tuple[str, ...]] = []

        def runner(command, **kwargs):
            command = tuple(command)
            commands.append(command)
            stdout = ""
            if "ps" in command and "--services" in command:
                stdout = (
                    "redis-queue\nqueue-fault\nbackend\nqueue-short\n"
                    "queue-long\nwebsocket\nfrontend\nfault-gateway\nremittance"
                )
            if "mariadb-dump" in command:
                kwargs["stdout"].write(b"database-state")
            elif "cat /home/frappe/frappe-bench/sites/" in command[-1]:
                stdout = '{"db_password":"fresh","encryption_key":"source-key"}'
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
                    "site_crypto",
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
                "websocket",
                "frontend",
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
        self.assertEqual(len(starts), 5)
        self.assertLess(
            commands.index(starts[0]),
            commands.index(starts[1]),
        )
        self.assertLess(
            commands.index(starts[1]),
            commands.index(starts[2]),
        )
        self.assertLess(
            commands.index(starts[2]),
            commands.index(starts[3]),
        )
        self.assertLess(
            commands.index(starts[3]),
            commands.index(starts[4]),
        )
        self.assertEqual(starts[0][-1], "redis-queue")
        self.assertIn("--wait", starts[0])
        self.assertEqual(starts[1][-1], "queue-fault")
        self.assertIn("backend", starts[2])
        self.assertIn("queue-short", starts[2])
        self.assertIn("websocket", starts[2])
        self.assertEqual(starts[3][-1], "frontend")
        self.assertIn("fault-gateway", starts[4])
        self.assertIn("--no-recreate", starts[4])

    def test_restore_verifies_hashes_before_replacing_native_state(self) -> None:
        commands: list[tuple[str, ...]] = []
        restored_inputs: list[bytes] = []
        restored_site_configs: list[dict[str, str]] = []

        def runner(command, **kwargs):
            command = tuple(command)
            commands.append(command)
            if "stdin" in kwargs:
                restored_inputs.append(kwargs["stdin"].read())
            if "input" in kwargs:
                restored_site_configs.append(json.loads(kwargs["input"]))
            stdout = ""
            if "cat /home/frappe/frappe-bench/sites/" in command[-1]:
                stdout = json.dumps(
                    {
                        "db_name": "fresh-db",
                        "db_password": "fresh-password",
                        "encryption_key": "fresh-key",
                    }
                )
            return subprocess.CompletedProcess(command, 0, stdout, "")

        with TemporaryDirectory() as directory:
            root = Path(directory)
            bundle = root / "boundary"
            bundle.mkdir()
            payloads = {
                "database": ("database.sql", b"database-state"),
                "site_crypto": (
                    "site-crypto.json",
                    b'{"encryption_key":"source-key"}\n',
                ),
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
                "schema_version": "1.2",
                "capture_mode": "simultaneous_service_quiescence",
                "running_services": [
                    "redis-queue",
                    "queue-fault",
                    "backend",
                    "queue-short",
                    "queue-long",
                    "websocket",
                    "frontend",
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
            self.assertEqual(
                restored_site_configs,
                [
                    {
                        "db_name": "fresh-db",
                        "db_password": "fresh-password",
                        "encryption_key": "source-key",
                    }
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
            self.assertEqual(len(starts), 5)
            self.assertEqual(starts[0][-1], "redis-queue")
            self.assertEqual(starts[1][-1], "queue-fault")
            self.assertIn("backend", starts[2])
            self.assertIn("websocket", starts[2])
            self.assertEqual(starts[3][-1], "frontend")
            self.assertIn("fault-gateway", starts[4])
            self.assertIn("--no-recreate", starts[4])

            commands.clear()
            self.assertEqual(
                stack.restore_bundle(bundle, resume_queue_workers=False),
                manifest,
            )
            starts = [
                command
                for command in commands
                if "up" in command and "--no-deps" in command
            ]
            self.assertEqual(len(starts), 5)
            self.assertTrue(
                all("queue-short" not in command for command in starts)
            )
            self.assertTrue(
                all("queue-long" not in command for command in starts)
            )

            commands.clear()
            (bundle / "redis-queue.tar").write_bytes(b"drift")
            with self.assertRaisesRegex(
                ValueError,
                "bundle file drift: redis_queue",
            ):
                stack.restore_bundle(bundle)
            self.assertEqual(commands, [])

    def test_legacy_site_config_restore_keeps_fresh_database_credentials(self) -> None:
        commands: list[tuple[str, ...]] = []
        restored_site_configs: list[dict[str, str]] = []

        def runner(command, **kwargs):
            command = tuple(command)
            commands.append(command)
            if "stdin" in kwargs:
                kwargs["stdin"].read()
            if "input" in kwargs:
                restored_site_configs.append(json.loads(kwargs["input"]))
            stdout = ""
            if "cat /home/frappe/frappe-bench/sites/" in command[-1]:
                stdout = json.dumps(
                    {
                        "db_name": "fresh-db",
                        "db_password": "fresh-password",
                        "encryption_key": "fresh-key",
                    }
                )
            return subprocess.CompletedProcess(command, 0, stdout, "")

        with TemporaryDirectory() as directory:
            root = Path(directory)
            bundle = root / "legacy"
            bundle.mkdir()
            site_config = io.BytesIO()
            source = b'{"db_password":"old","encryption_key":"source-key"}'
            with tarfile.open(fileobj=site_config, mode="w") as archive:
                member = tarfile.TarInfo("site_config.json")
                member.size = len(source)
                archive.addfile(member, io.BytesIO(source))
            payloads = {
                "database": ("database.sql", b"database-state"),
                "site_config": ("site-config.tar", site_config.getvalue()),
                "redis_queue": ("redis-queue.tar", b"redis-state"),
                "gateway_audit": ("gateway-audit.tar", b"gateway-state"),
                "remittance_audit": ("remittance-audit.tar", b"delivery-state"),
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
                "schema_version": "1.1",
                "capture_mode": "simultaneous_service_quiescence",
                "running_services": [
                    "redis-queue",
                    "queue-fault",
                    "backend",
                    "websocket",
                    "frontend",
                    "fault-gateway",
                    "remittance",
                ],
                "files": files,
            }
            (bundle / "bundle.json").write_text(json.dumps(manifest))
            stack = ERPNextStack(compose_file=root / "compose.yaml", runner=runner)
            stack._wait_http_service = lambda *args, **kwargs: None  # type: ignore[method-assign]

            self.assertEqual(stack.restore_bundle(bundle), manifest)
            self.assertEqual(restored_site_configs[0]["db_name"], "fresh-db")
            self.assertEqual(restored_site_configs[0]["db_password"], "fresh-password")
            self.assertEqual(restored_site_configs[0]["encryption_key"], "source-key")


if __name__ == "__main__":
    unittest.main()
