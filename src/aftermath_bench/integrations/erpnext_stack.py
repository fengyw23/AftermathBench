from __future__ import annotations

import ast
import hashlib
import json
import subprocess
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Sequence


def _parse_mapping_output(output: str) -> dict[str, Any]:
    for line in reversed([line.strip() for line in output.splitlines()]):
        if not line:
            continue
        for parser in (json.loads, ast.literal_eval):
            try:
                value = parser(line)
            except (ValueError, SyntaxError, json.JSONDecodeError):
                continue
            if isinstance(value, dict):
                return value
    raise RuntimeError(f"no mapping found in command output: {output!r}")


@dataclass
class ERPNextStack:
    compose_file: Path
    project_name: str = "aftermath-erpnext"
    container_cli: str = "docker"
    db_root_password: str = "aftermath-root"
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
    ) -> subprocess.CompletedProcess:
        return self.runner(
            self.compose_command(*arguments),
            check=True,
            capture_output=capture_output,
            text=True,
        )

    def up(self) -> None:
        self.run("up", "--detach", "--build")

    def down(self, *, remove_volumes: bool = False) -> None:
        arguments = ["down", "--remove-orphans"]
        if remove_volumes:
            arguments.append("--volumes")
        self.run(*arguments)

    def setup_company(self) -> None:
        setup_arguments = {
            "currency": "USD",
            "full_name": "Aftermath Administrator",
            "company_name": "Aftermath Laboratories LLC",
            "timezone": "America/New_York",
            "company_abbr": "AL",
            "industry": "Healthcare",
            "country": "United States",
            "fy_start_date": "2026-01-01",
            "fy_end_date": "2026-12-31",
            "language": "english",
            "company_tagline": "Recovery benchmark fixture",
            "email": "admin@aftermath.invalid",
            "password": "not-used-for-api-auth",
            "chart_of_accounts": "Standard",
        }
        self.run(
            "exec",
            "-T",
            "backend",
            "bench",
            "--site",
            "aftermath.localhost",
            "execute",
            "frappe.desk.page.setup_wizard.setup_wizard.setup_complete",
            "--kwargs",
            json.dumps(setup_arguments, separators=(",", ":")),
        )

    def generate_administrator_keys(self) -> dict[str, str]:
        result = self.run(
            "exec",
            "-T",
            "backend",
            "bench",
            "--site",
            "aftermath.localhost",
            "execute",
            "frappe.core.doctype.user.user.generate_keys",
            "--kwargs",
            '{"user":"Administrator"}',
            capture_output=True,
        )
        keys = _parse_mapping_output(result.stdout)
        if not keys.get("api_key") or not keys.get("api_secret"):
            raise RuntimeError("Frappe did not return an API key and secret")
        return {
            "api_key": str(keys["api_key"]),
            "api_secret": str(keys["api_secret"]),
        }

    def snapshot_database(self, destination: str | Path) -> str:
        path = Path(destination).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        command = self.compose_command(
            "exec",
            "-T",
            "db",
            "mariadb-dump",
            "-uroot",
            f"-p{self.db_root_password}",
            "--all-databases",
            "--single-transaction",
            "--routines",
            "--events",
        )
        with path.open("wb") as handle:
            self.runner(command, check=True, stdout=handle)
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def restore_database(self, source: str | Path) -> None:
        path = Path(source).resolve()
        if not path.is_file():
            raise FileNotFoundError(path)
        self.run(
            "stop",
            "fault-gateway",
            "frontend",
            "backend",
            "websocket",
            "queue-short",
            "queue-long",
        )
        command = self.compose_command(
            "exec",
            "-T",
            "db",
            "mariadb",
            "-uroot",
            f"-p{self.db_root_password}",
        )
        with path.open("rb") as handle:
            self.runner(command, check=True, stdin=handle)
        self.run("exec", "-T", "redis-cache", "redis-cli", "FLUSHALL")
        self.run("exec", "-T", "redis-queue", "redis-cli", "FLUSHALL")
        self.run(
            "start",
            "backend",
            "websocket",
            "queue-short",
            "queue-long",
            "frontend",
            "fault-gateway",
        )
        self._reset_http_service("http://127.0.0.1:9091/admin/reset")
        self._reset_http_service("http://127.0.0.1:9092/admin/reset")

    @staticmethod
    def _reset_http_service(url: str) -> None:
        request = urllib.request.Request(url, method="DELETE")
        with urllib.request.urlopen(request, timeout=30) as response:
            if response.status != 200:
                raise RuntimeError(f"reset endpoint returned {response.status}")

