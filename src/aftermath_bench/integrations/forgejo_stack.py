from __future__ import annotations

import hashlib
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
        password: str = "aftermath-admin",
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
            "username": username,
            "token": match.group(1),
        }

    def snapshot(self, destination: str | Path) -> str:
        path = Path(destination).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        self.run(
            "stop",
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
            "api-fault-gateway",
            "forgejo",
            "webhook-fault-gateway",
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
        )
        self.wait_ready()
        for url in (
            "http://127.0.0.1:9091/admin/reset",
            "http://127.0.0.1:9092/admin/reset",
            "http://127.0.0.1:9093/admin/reset",
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
