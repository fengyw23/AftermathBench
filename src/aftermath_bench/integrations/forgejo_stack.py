from __future__ import annotations

import hashlib
import json
import re
import subprocess
import time
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

TOKEN_PATTERN = re.compile(
    r"Access token was successfully created\.\.\.\s+(\S+)"
)
BUNDLE_SERVICES = (
    "api-fault-gateway",
    "forgejo",
    "runner-daemon",
    "webhook-fault-gateway",
    "provenance-webhook-fault-gateway",
    "webhook-sink",
)
MIGRATION_BUNDLE_SERVICES = (
    "api-fault-gateway",
    "forgejo",
    "runner-daemon",
    "deployment-fault-gateway",
    "deployment-target",
)
PROMOTION_BUNDLE_SERVICES = (
    "api-fault-gateway",
    "forgejo",
    "runner-daemon",
    "deployment-fault-gateway",
    "deployment-target",
    "webhook-fault-gateway",
    "webhook-sink",
)
QUIESCE_TIMEOUT_SECONDS = "2"


@dataclass
class ForgejoStack:
    compose_file: Path
    project_name: str = "aftermath-forgejo"
    container_cli: str = "docker"
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run

    def compose_command(self, *arguments: str) -> tuple[str, ...]:
        return (
            self.container_cli,
            "compose",
            "--project-name",
            self.project_name,
            "--file",
            str(self.compose_file),
            *arguments,
        )

    def run(
        self,
        *arguments: str,
        capture_output: bool = False,
        stdin: Any = None,
        stdout: Any = None,
    ) -> subprocess.CompletedProcess:
        return self.runner(
            self.compose_command(*arguments),
            check=True,
            capture_output=capture_output,
            stdin=stdin,
            stdout=stdout,
            text=capture_output,
        )

    def up(self) -> None:
        self.run("up", "--detach", "--build")
        self.wait_ready()

    def down(self, *, remove_volumes: bool = False) -> None:
        arguments = ["down", "--remove-orphans"]
        if remove_volumes:
            arguments.append("--volumes")
        self.run(*arguments)

    def create_administrator(
        self,
        *,
        username: str = "aftermath",
        password: str,
        email: str = "admin@aftermath.invalid",
    ) -> dict[str, str]:
        result = self.run(
            "exec",
            "-T",
            "-u",
            "git",
            "forgejo",
            "forgejo",
            "admin",
            "user",
            "create",
            "--username",
            username,
            "--password",
            password,
            "--email",
            email,
            "--admin",
            "--must-change-password=false",
            "--access-token",
            "--access-token-name",
            "aftermath-bench",
            "--access-token-scopes",
            "all",
            capture_output=True,
        )
        match = TOKEN_PATTERN.search(result.stdout)
        if match is None:
            raise RuntimeError("Forgejo did not return an administrator token")
        return {
            "base_url": "http://127.0.0.1:8080/api/v1",
            "web_base_url": "http://127.0.0.1:8080",
            "username": username,
            "password": password,
            "token": match.group(1),
        }

    def register_action_runner(
        self,
        *,
        name: str = "aftermath-native-runner",
        label: str = "aftermath-native:host",
    ) -> None:
        """Register the pinned native runner without exposing Docker itself.

        The short-lived registration token is obtained from the source-built
        Forgejo server and passed directly to the official pinned runner.  It
        is never written to the benchmark repository or its evidence files.
        """

        token_result = self.run(
            "exec",
            "-T",
            "-u",
            "git",
            "forgejo",
            "forgejo",
            "actions",
            "generate-runner-token",
            capture_output=True,
        )
        token = token_result.stdout.strip().splitlines()[-1].strip()
        if not token:
            raise RuntimeError("Forgejo did not return an Actions runner token")
        self.run(
            "run",
            "--rm",
            "--no-deps",
            "--entrypoint",
            "forgejo-runner",
            "runner-register",
            "register",
            "--no-interactive",
            "--instance",
            "http://forgejo:3000",
            "--name",
            name,
            "--token",
            token,
            "--labels",
            label,
        )
        self.run(
            "run",
            "--rm",
            "--no-deps",
            "--entrypoint",
            "sh",
            "runner-register",
            "-ec",
            "forgejo-runner generate-config > /data/config.yml",
        )
        self.run("restart", "runner-daemon")

    def start_action_runner(self) -> None:
        self.run("start", "runner-daemon")

    def snapshot(self, destination: str | Path) -> str:
        path = Path(destination).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        self.run(
            "stop",
            "--timeout",
            QUIESCE_TIMEOUT_SECONDS,
            "api-fault-gateway",
            "forgejo",
        )
        command = self.compose_command(
            "run",
            "--rm",
            "--no-deps",
            "--entrypoint",
            "tar",
            "forgejo",
            "-C",
            "/data",
            "-czf",
            "-",
            ".",
        )
        try:
            with path.open("wb") as handle:
                self.runner(command, check=True, stdout=handle)
        finally:
            self.run("start", "forgejo", "api-fault-gateway")
            self.wait_ready()
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def restore(self, source: str | Path) -> None:
        path = Path(source).resolve()
        if not path.is_file():
            raise FileNotFoundError(path)
        self.run(
            "stop",
            "--timeout",
            QUIESCE_TIMEOUT_SECONDS,
            "api-fault-gateway",
            "forgejo",
            "webhook-fault-gateway",
            "provenance-webhook-fault-gateway",
            "webhook-sink",
        )
        command = self.compose_command(
            "run",
            "--rm",
            "--no-deps",
            "--entrypoint",
            "sh",
            "forgejo",
            "-c",
            "find /data -mindepth 1 -maxdepth 1 -exec rm -rf -- {} +; "
            "tar -C /data -xzf -",
        )
        with path.open("rb") as handle:
            self.runner(command, check=True, stdin=handle)
        self.run(
            "start",
            "forgejo",
            "api-fault-gateway",
            "webhook-sink",
            "webhook-fault-gateway",
            "provenance-webhook-fault-gateway",
        )
        self.wait_ready()
        for url in (
            "http://127.0.0.1:9091/admin/reset",
            "http://127.0.0.1:9092/admin/reset",
            "http://127.0.0.1:9093/admin/reset",
            "http://127.0.0.1:9094/admin/reset",
        ):
            self.reset_service(url)

    def snapshot_bundle(self, destination: str | Path) -> dict[str, str]:
        """Capture Forgejo and the downstream receiver's durable state."""

        directory = Path(destination).resolve()
        directory.mkdir(parents=True, exist_ok=True)
        forgejo_archive = directory / "forgejo-data.tar.gz"
        sink_archive = directory / "webhook-sink-data.tar.gz"
        self.run(
            "stop", "--timeout", QUIESCE_TIMEOUT_SECONDS, *BUNDLE_SERVICES
        )
        try:
            for service, archive in (
                ("forgejo", forgejo_archive),
                ("webhook-sink", sink_archive),
            ):
                command = self.compose_command(
                    "run",
                    "--rm",
                    "--no-deps",
                    "--entrypoint",
                    "tar",
                    service,
                    "-C",
                    "/data",
                    "-czf",
                    "-",
                    ".",
                )
                with archive.open("wb") as handle:
                    self.runner(command, check=True, stdout=handle)
        finally:
            self.run("start", *BUNDLE_SERVICES)
            self.wait_ready()
        result = {
            "schema_version": "1.0",
            "capture_mode": "simultaneous_service_quiescence",
            "forgejo_sha256": hashlib.sha256(
                forgejo_archive.read_bytes()
            ).hexdigest(),
            "webhook_sink_sha256": hashlib.sha256(
                sink_archive.read_bytes()
            ).hexdigest(),
        }
        (directory / "bundle.json").write_text(
            json.dumps(result, indent=2) + "\n",
            encoding="utf-8",
        )
        return result

    def restore_bundle(self, source: str | Path) -> None:
        """Restore the exact native repository and receiver ledger."""

        directory = Path(source).resolve()
        forgejo_archive = directory / "forgejo-data.tar.gz"
        sink_archive = directory / "webhook-sink-data.tar.gz"
        manifest = json.loads(
            (directory / "bundle.json").read_text(encoding="utf-8")
        )
        observed = {
            "schema_version": "1.0",
            "capture_mode": "simultaneous_service_quiescence",
            "forgejo_sha256": hashlib.sha256(
                forgejo_archive.read_bytes()
            ).hexdigest(),
            "webhook_sink_sha256": hashlib.sha256(
                sink_archive.read_bytes()
            ).hexdigest(),
        }
        if observed != manifest:
            raise RuntimeError(
                "Forgejo state bundle hash mismatch: "
                f"expected={manifest}, observed={observed}"
            )
        self.run(
            "stop", "--timeout", QUIESCE_TIMEOUT_SECONDS, *BUNDLE_SERVICES
        )
        try:
            for service, archive in (
                ("forgejo", forgejo_archive),
                ("webhook-sink", sink_archive),
            ):
                command = self.compose_command(
                    "run",
                    "--rm",
                    "--no-deps",
                    "--entrypoint",
                    "sh",
                    service,
                    "-c",
                    (
                        "find /data -mindepth 1 -maxdepth 1 "
                        "-exec rm -rf -- {} +; tar -C /data -xzf -"
                    ),
                )
                with archive.open("rb") as handle:
                    self.runner(command, check=True, stdin=handle)
        finally:
            self.run("start", *BUNDLE_SERVICES)
            self.wait_ready()
        # Gateway audit databases are control-plane telemetry, not model or
        # evaluator state. Every replay starts them from the same empty state.
        for url in (
            "http://127.0.0.1:9091/admin/reset",
            "http://127.0.0.1:9093/admin/reset",
            "http://127.0.0.1:9094/admin/reset",
        ):
            self.reset_service(url)

    def snapshot_migration_bundle(
        self,
        destination: str | Path,
        *,
        runner_enabled: bool,
    ) -> dict[str, Any]:
        """Capture Actions and deployment state at one failure boundary."""

        directory = Path(destination).resolve()
        directory.mkdir(parents=True, exist_ok=True)
        archives = {
            "forgejo": directory / "forgejo-data.tar.gz",
            "deployment-target": directory / "deployment-target-data.tar.gz",
        }
        self.run(
            "stop",
            "--timeout",
            QUIESCE_TIMEOUT_SECONDS,
            *MIGRATION_BUNDLE_SERVICES,
        )
        try:
            for service, archive in archives.items():
                command = self.compose_command(
                    "run",
                    "--rm",
                    "--no-deps",
                    "--entrypoint",
                    "tar",
                    service,
                    "-C",
                    "/data",
                    "-czf",
                    "-",
                    ".",
                )
                with archive.open("wb") as handle:
                    self.runner(command, check=True, stdout=handle)
        finally:
            services = [
                service
                for service in MIGRATION_BUNDLE_SERVICES
                if service != "runner-daemon" or runner_enabled
            ]
            self.run("start", *services)
            self.wait_ready()
        result: dict[str, Any] = {
            "schema_version": "1.0",
            "capture_mode": "simultaneous_actions_and_deployment_quiescence",
            "runner_enabled": runner_enabled,
            "forgejo_sha256": hashlib.sha256(
                archives["forgejo"].read_bytes()
            ).hexdigest(),
            "deployment_target_sha256": hashlib.sha256(
                archives["deployment-target"].read_bytes()
            ).hexdigest(),
        }
        (directory / "bundle.json").write_text(
            json.dumps(result, indent=2) + "\n", encoding="utf-8"
        )
        return result

    def restore_migration_bundle(self, source: str | Path) -> None:
        directory = Path(source).resolve()
        manifest = json.loads(
            (directory / "bundle.json").read_text(encoding="utf-8")
        )
        archives = {
            "forgejo": directory / "forgejo-data.tar.gz",
            "deployment-target": directory / "deployment-target-data.tar.gz",
        }
        observed = {
            "schema_version": "1.0",
            "capture_mode": "simultaneous_actions_and_deployment_quiescence",
            "runner_enabled": bool(manifest.get("runner_enabled")),
            "forgejo_sha256": hashlib.sha256(
                archives["forgejo"].read_bytes()
            ).hexdigest(),
            "deployment_target_sha256": hashlib.sha256(
                archives["deployment-target"].read_bytes()
            ).hexdigest(),
        }
        if observed != manifest:
            raise RuntimeError(
                "Forgejo migration state bundle hash mismatch: "
                f"expected={manifest}, observed={observed}"
            )
        self.run(
            "stop",
            "--timeout",
            QUIESCE_TIMEOUT_SECONDS,
            *MIGRATION_BUNDLE_SERVICES,
        )
        try:
            for service, archive in archives.items():
                command = self.compose_command(
                    "run",
                    "--rm",
                    "--no-deps",
                    "--entrypoint",
                    "sh",
                    service,
                    "-c",
                    (
                        "find /data -mindepth 1 -maxdepth 1 "
                        "-exec rm -rf -- {} +; tar -C /data -xzf -"
                    ),
                )
                with archive.open("rb") as handle:
                    self.runner(command, check=True, stdin=handle)
        finally:
            services = [
                service
                for service in MIGRATION_BUNDLE_SERVICES
                if service != "runner-daemon" or manifest["runner_enabled"]
            ]
            self.run("start", *services)
            self.wait_ready()
        for url in (
            "http://127.0.0.1:9091/admin/reset",
            "http://127.0.0.1:9096/admin/reset",
        ):
            self.reset_service(url)

    def snapshot_promotion_bundle(
        self,
        destination: str | Path,
        *,
        runner_enabled: bool,
    ) -> dict[str, Any]:
        """Capture Forgejo, deployment and external-attestation state together."""

        directory = Path(destination).resolve()
        directory.mkdir(parents=True, exist_ok=True)
        archives = {
            "forgejo": directory / "forgejo-data.tar.gz",
            "deployment-target": directory / "deployment-target-data.tar.gz",
            "webhook-sink": directory / "webhook-sink-data.tar.gz",
        }
        self.run(
            "stop",
            "--timeout",
            QUIESCE_TIMEOUT_SECONDS,
            *PROMOTION_BUNDLE_SERVICES,
        )
        try:
            for service, archive in archives.items():
                command = self.compose_command(
                    "run",
                    "--rm",
                    "--no-deps",
                    "--entrypoint",
                    "tar",
                    service,
                    "-C",
                    "/data",
                    "-czf",
                    "-",
                    ".",
                )
                with archive.open("wb") as handle:
                    self.runner(command, check=True, stdout=handle)
        finally:
            services = [
                service
                for service in PROMOTION_BUNDLE_SERVICES
                if service != "runner-daemon" or runner_enabled
            ]
            self.run("start", *services)
            self.wait_ready()
        result: dict[str, Any] = {
            "schema_version": "1.0",
            "capture_mode": (
                "simultaneous_actions_deployment_and_attestation_quiescence"
            ),
            "runner_enabled": runner_enabled,
        }
        for service, archive in archives.items():
            key = service.replace("-", "_") + "_sha256"
            result[key] = hashlib.sha256(archive.read_bytes()).hexdigest()
        (directory / "bundle.json").write_text(
            json.dumps(result, indent=2) + "\n", encoding="utf-8"
        )
        return result

    def restore_promotion_bundle(self, source: str | Path) -> None:
        directory = Path(source).resolve()
        manifest = json.loads(
            (directory / "bundle.json").read_text(encoding="utf-8")
        )
        archives = {
            "forgejo": directory / "forgejo-data.tar.gz",
            "deployment-target": directory / "deployment-target-data.tar.gz",
            "webhook-sink": directory / "webhook-sink-data.tar.gz",
        }
        observed: dict[str, Any] = {
            "schema_version": "1.0",
            "capture_mode": (
                "simultaneous_actions_deployment_and_attestation_quiescence"
            ),
            "runner_enabled": bool(manifest.get("runner_enabled")),
        }
        for service, archive in archives.items():
            key = service.replace("-", "_") + "_sha256"
            observed[key] = hashlib.sha256(archive.read_bytes()).hexdigest()
        if observed != manifest:
            raise RuntimeError(
                "Forgejo promotion state bundle hash mismatch: "
                f"expected={manifest}, observed={observed}"
            )
        self.run(
            "stop",
            "--timeout",
            QUIESCE_TIMEOUT_SECONDS,
            *PROMOTION_BUNDLE_SERVICES,
        )
        try:
            for service, archive in archives.items():
                command = self.compose_command(
                    "run",
                    "--rm",
                    "--no-deps",
                    "--entrypoint",
                    "sh",
                    service,
                    "-c",
                    (
                        "find /data -mindepth 1 -maxdepth 1 "
                        "-exec rm -rf -- {} +; tar -C /data -xzf -"
                    ),
                )
                with archive.open("rb") as handle:
                    self.runner(command, check=True, stdin=handle)
        finally:
            services = [
                service
                for service in PROMOTION_BUNDLE_SERVICES
                if service != "runner-daemon" or manifest["runner_enabled"]
            ]
            self.run("start", *services)
            self.wait_ready()
        for url in (
            "http://127.0.0.1:9091/admin/reset",
            "http://127.0.0.1:9093/admin/reset",
            "http://127.0.0.1:9096/admin/reset",
        ):
            self.reset_service(url)

    def wait_ready(self) -> None:
        self.wait_for_url("http://127.0.0.1:8080/api/healthz")
        self.wait_for_url("http://127.0.0.1:9092/health")

    @staticmethod
    def wait_for_url(
        url: str,
        *,
        attempts: int = 60,
        delay_seconds: float = 1.0,
        opener: Callable[..., Any] = urllib.request.urlopen,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        ForgejoStack._request_until_ready(
            urllib.request.Request(url, method="GET"),
            attempts=attempts,
            delay_seconds=delay_seconds,
            opener=opener,
            sleeper=sleeper,
        )

    @staticmethod
    def reset_service(
        url: str,
        *,
        attempts: int = 30,
        delay_seconds: float = 1.0,
        opener: Callable[..., Any] = urllib.request.urlopen,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        ForgejoStack._request_until_ready(
            urllib.request.Request(url, method="DELETE"),
            attempts=attempts,
            delay_seconds=delay_seconds,
            opener=opener,
            sleeper=sleeper,
        )

    @staticmethod
    def _request_until_ready(
        request: urllib.request.Request,
        *,
        attempts: int,
        delay_seconds: float,
        opener: Callable[..., Any],
        sleeper: Callable[[float], None],
    ) -> None:
        if attempts < 1:
            raise ValueError("attempts must be at least one")
        last_error: Exception | None = None
        for attempt in range(attempts):
            try:
                with opener(request, timeout=3) as response:
                    if response.status == 200:
                        return
                    last_error = RuntimeError(
                        f"service returned HTTP {response.status}"
                    )
            except OSError as error:
                last_error = error
            if attempt + 1 < attempts:
                sleeper(delay_seconds)
        raise RuntimeError(
            f"service did not become ready after {attempts} attempts: "
            f"{request.full_url}"
        ) from last_error
