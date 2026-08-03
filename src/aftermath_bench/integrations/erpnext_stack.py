from __future__ import annotations

import ast
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import time
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_BUNDLE_SCHEMA_VERSION = "1.1"
_LEGACY_BUNDLE_SCHEMA_VERSION = "1.0"
_BUNDLE_CAPTURE_MODE = "simultaneous_service_quiescence"
_BUNDLE_FILES = {
    "database": "database.sql",
    "site_config": "site-config.tar",
    "redis_queue": "redis-queue.tar",
    "gateway_audit": "gateway-audit.tar",
    "remittance_audit": "remittance-audit.tar",
}
_LEGACY_BUNDLE_FILES = {
    key: value for key, value in _BUNDLE_FILES.items() if key != "site_config"
}
_MUTATING_SERVICES = (
    "backend",
    "queue-short",
    "queue-long",
    "fault-gateway",
    "remittance",
)
_BUNDLE_STOP_SERVICES = (
    *_MUTATING_SERVICES,
    "websocket",
    "frontend",
    "queue-fault",
    "redis-queue",
)
_BUNDLE_START_SERVICES = (
    "redis-queue",
    "queue-fault",
    "backend",
    "queue-short",
    "queue-long",
    "websocket",
    "frontend",
    "fault-gateway",
    "remittance",
)
_BUNDLE_REQUIRED_RUNNING = frozenset(
    {
        "redis-queue",
        "queue-fault",
        "backend",
        "websocket",
        "frontend",
        "fault-gateway",
        "remittance",
    }
)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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
            json.dumps({"args": setup_arguments}, separators=(",", ":")),
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

    def requeue_payment_remittance(
        self,
        payment_entry: str,
        webhook_name: str = "Aftermath Payment Remittance",
    ) -> dict[str, Any]:
        try:
            result = self.run(
                "exec",
                "-T",
                "backend",
                "bench",
                "--site",
                "aftermath.localhost",
                "execute",
                "frappe.aftermath_bridge.requeue_payment_remittance",
                "--kwargs",
                json.dumps(
                    {
                        "payment_entry": payment_entry,
                        "webhook_name": webhook_name,
                    },
                    separators=(",", ":"),
                ),
                capture_output=True,
            )
        except subprocess.CalledProcessError as error:
            detail = "\n".join(
                value.strip()
                for value in (
                    str(error.stdout or ""),
                    str(error.stderr or ""),
                )
                if value and value.strip()
            )
            raise RuntimeError(
                "native remittance requeue failed" + (f": {detail}" if detail else "")
            ) from error
        return _parse_mapping_output(result.stdout)

    def enqueue_document_webhook(
        self,
        *,
        doctype: str,
        document_name: str,
        webhook_name: str,
    ) -> dict[str, Any]:
        result = self.run(
            "exec",
            "-T",
            "backend",
            "bench",
            "--site",
            "aftermath.localhost",
            "execute",
            "frappe.aftermath_bridge.enqueue_document_webhook",
            "--kwargs",
            json.dumps(
                {
                    "doctype": doctype,
                    "document_name": document_name,
                    "webhook_name": webhook_name,
                },
                separators=(",", ":"),
            ),
            capture_output=True,
        )
        return _parse_mapping_output(result.stdout)

    def reconcile_supplier_documents(
        self,
        *,
        company: str,
        supplier: str,
    ) -> dict[str, Any]:
        result = self.run(
            "exec",
            "-T",
            "backend",
            "bench",
            "--site",
            "aftermath.localhost",
            "execute",
            "frappe.aftermath_bridge.reconcile_supplier_documents",
            "--kwargs",
            json.dumps(
                {"company": company, "supplier": supplier},
                separators=(",", ":"),
            ),
            capture_output=True,
        )
        return _parse_mapping_output(result.stdout)

    def reconcile_customer_documents(
        self,
        *,
        company: str,
        customer: str,
    ) -> dict[str, Any]:
        result = self.run(
            "exec",
            "-T",
            "backend",
            "bench",
            "--site",
            "aftermath.localhost",
            "execute",
            "frappe.aftermath_bridge.reconcile_customer_documents",
            "--kwargs",
            json.dumps(
                {"company": company, "customer": customer},
                separators=(",", ":"),
            ),
            capture_output=True,
        )
        return _parse_mapping_output(result.stdout)

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
        return _sha256_file(path)

    def _import_database(self, source: Path) -> None:
        command = self.compose_command(
            "exec",
            "-T",
            "db",
            "mariadb",
            "-uroot",
            f"-p{self.db_root_password}",
        )
        with source.open("rb") as handle:
            self.runner(command, check=True, stdin=handle)

    def _archive_service_volume(
        self,
        *,
        service: str,
        destination: Path,
    ) -> None:
        command = self.compose_command(
            "run",
            "--rm",
            "--no-deps",
            "--entrypoint",
            "sh",
            service,
            "-c",
            "tar -C /data -cf - .",
        )
        with destination.open("wb") as handle:
            self.runner(command, check=True, stdout=handle)

    def _archive_site_config(self, destination: Path) -> None:
        """Capture the site key material needed to decrypt Frappe secrets."""

        command = self.compose_command(
            "run",
            "--rm",
            "--no-deps",
            "--entrypoint",
            "sh",
            "backend",
            "-c",
            (
                "tar -C /home/frappe/frappe-bench/sites/"
                "aftermath.localhost -cf - site_config.json"
            ),
        )
        with destination.open("wb") as handle:
            self.runner(command, check=True, stdout=handle)

    def _restore_service_volume(
        self,
        *,
        service: str,
        source: Path,
    ) -> None:
        command = self.compose_command(
            "run",
            "--rm",
            "--no-deps",
            "--entrypoint",
            "sh",
            service,
            "-c",
            (
                "find /data -mindepth 1 -maxdepth 1 -exec rm -rf -- {} + "
                "&& tar -C /data -xf -"
            ),
        )
        with source.open("rb") as handle:
            self.runner(command, check=True, stdin=handle)

    def _restore_site_config(self, source: Path) -> None:
        command = self.compose_command(
            "run",
            "--rm",
            "--no-deps",
            "--entrypoint",
            "sh",
            "backend",
            "-c",
            ("tar -C /home/frappe/frappe-bench/sites/aftermath.localhost -xf -"),
        )
        with source.open("rb") as handle:
            self.runner(command, check=True, stdin=handle)

    def _resume_bundle_services(
        self,
        running_services: tuple[str, ...],
    ) -> None:
        """Resume a quiesced bundle in native dependency order.

        The queue proxy is intentionally part of the persisted boundary.  A
        concurrent Compose start can launch Frappe before that proxy accepts
        connections, causing gunicorn to exit and leaving the public gateway
        behind a permanent 502.  Resume the captured containers in three
        stages without traversing one-shot Compose dependencies or recreating
        container identities.
        """

        selected = set(running_services)
        common = (
            "up",
            "--detach",
            "--no-deps",
            "--no-recreate",
        )
        if "redis-queue" in selected:
            self.run(
                "up",
                "--detach",
                "--wait",
                "--wait-timeout",
                "60",
                "--no-deps",
                "--no-recreate",
                "redis-queue",
            )
        if "queue-fault" in selected:
            self.run(*common, "queue-fault")
            self._wait_http_service("http://127.0.0.1:8474/version")
        core_services = tuple(
            service
            for service in _BUNDLE_START_SERVICES
            if service in selected
            and service
            in {
                "backend",
                "queue-short",
                "queue-long",
                "websocket",
            }
        )
        if core_services:
            self.run(*common, *core_services)
        if "frontend" in selected:
            # Nginx resolves backend/websocket addresses when it starts.
            # Restart it after those containers have rejoined the network so
            # it cannot retain a pre-quiescence upstream IP.
            self.run(*common, "frontend")
        edge_services = tuple(
            service
            for service in ("fault-gateway", "remittance")
            if service in selected
        )
        if edge_services:
            self.run(*common, *edge_services)

    def snapshot_bundle(self, destination: str | Path) -> dict[str, Any]:
        """Capture every mutable service needed to replay one exact boundary."""

        bundle = Path(destination).resolve()
        if bundle.exists():
            raise FileExistsError(bundle)
        running_process = self.run(
            "ps",
            "--status",
            "running",
            "--services",
            capture_output=True,
        )
        running_services = tuple(
            service
            for service in _BUNDLE_START_SERVICES
            if service in set(running_process.stdout.splitlines())
        )
        if not _BUNDLE_REQUIRED_RUNNING <= set(running_services):
            missing = sorted(_BUNDLE_REQUIRED_RUNNING - set(running_services))
            raise RuntimeError(
                f"cannot snapshot incomplete ERPNext runtime; not running: {missing}"
            )
        bundle.parent.mkdir(parents=True, exist_ok=True)
        temporary: Path | None = Path(
            tempfile.mkdtemp(
                prefix=f".{bundle.name}.incomplete-",
                dir=bundle.parent,
            )
        )
        try:
            self.run("stop", *_BUNDLE_STOP_SERVICES)
            try:
                database = temporary / _BUNDLE_FILES["database"]
                self.snapshot_database(database)
                self._archive_site_config(temporary / _BUNDLE_FILES["site_config"])
                for key, service in (
                    ("redis_queue", "redis-queue"),
                    ("gateway_audit", "fault-gateway"),
                    ("remittance_audit", "remittance"),
                ):
                    self._archive_service_volume(
                        service=service,
                        destination=temporary / _BUNDLE_FILES[key],
                    )
            finally:
                if running_services:
                    self._resume_bundle_services(running_services)
            self._wait_http_service("http://127.0.0.1:8080/api/method/ping")
            self._wait_http_service("http://127.0.0.1:9091/audit")
            self._wait_http_service("http://127.0.0.1:9092/health")
            files = {
                key: {
                    "path": filename,
                    "bytes": (temporary / filename).stat().st_size,
                    "sha256": _sha256_file(temporary / filename),
                }
                for key, filename in _BUNDLE_FILES.items()
            }
            manifest = {
                "schema_version": _BUNDLE_SCHEMA_VERSION,
                "capture_mode": _BUNDLE_CAPTURE_MODE,
                "running_services": list(running_services),
                "files": files,
            }
            (temporary / "bundle.json").write_text(
                json.dumps(
                    manifest,
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
            os.replace(temporary, bundle)
            temporary = None
            return manifest
        finally:
            if temporary is not None and temporary.exists():
                shutil.rmtree(temporary)

    def restore_bundle(self, source: str | Path) -> dict[str, Any]:
        """Restore a quiesced native boundary bundle without replaying writes."""

        bundle = Path(source).resolve()
        manifest_path = bundle / "bundle.json"
        if not manifest_path.is_file():
            raise FileNotFoundError(manifest_path)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        schema_version = (
            manifest.get("schema_version") if isinstance(manifest, dict) else None
        )
        bundle_files = (
            _BUNDLE_FILES
            if schema_version == _BUNDLE_SCHEMA_VERSION
            else _LEGACY_BUNDLE_FILES
        )
        if (
            not isinstance(manifest, dict)
            or schema_version
            not in {_BUNDLE_SCHEMA_VERSION, _LEGACY_BUNDLE_SCHEMA_VERSION}
            or manifest.get("capture_mode") != _BUNDLE_CAPTURE_MODE
            or set(manifest.get("files", {})) != set(bundle_files)
            or not isinstance(manifest.get("running_services"), list)
            or len(manifest["running_services"])
            != len(set(map(str, manifest["running_services"])))
            or not set(map(str, manifest["running_services"]))
            <= set(_BUNDLE_START_SERVICES)
            or not _BUNDLE_REQUIRED_RUNNING
            <= set(map(str, manifest["running_services"]))
        ):
            raise ValueError("invalid ERPNext native bundle manifest")
        resolved_files: dict[str, Path] = {}
        for key, expected_name in bundle_files.items():
            declaration = manifest["files"].get(key)
            if (
                not isinstance(declaration, dict)
                or set(declaration) != {"path", "bytes", "sha256"}
                or declaration.get("path") != expected_name
            ):
                raise ValueError(
                    f"invalid ERPNext native bundle file declaration: {key}"
                )
            path = bundle / expected_name
            if (
                not path.is_file()
                or path.stat().st_size != int(declaration["bytes"])
                or _sha256_file(path) != str(declaration["sha256"])
            ):
                raise ValueError(f"ERPNext native bundle file drift: {key}")
            resolved_files[key] = path

        self.run("stop", *_BUNDLE_STOP_SERVICES)
        try:
            if "site_config" in resolved_files:
                self._restore_site_config(resolved_files["site_config"])
            self._import_database(resolved_files["database"])
            self._restore_service_volume(
                service="redis-queue",
                source=resolved_files["redis_queue"],
            )
            self._restore_service_volume(
                service="fault-gateway",
                source=resolved_files["gateway_audit"],
            )
            self._restore_service_volume(
                service="remittance",
                source=resolved_files["remittance_audit"],
            )
        finally:
            running_services = tuple(map(str, manifest["running_services"]))
            if running_services:
                self._resume_bundle_services(running_services)
        self.run("exec", "-T", "redis-cache", "redis-cli", "FLUSHALL")
        self._wait_http_service("http://127.0.0.1:8080/api/method/ping")
        self._wait_http_service("http://127.0.0.1:9091/audit")
        self._wait_http_service("http://127.0.0.1:9092/health")
        return manifest

    def restore_database(self, source: str | Path) -> None:
        path = Path(source).resolve()
        if not path.is_file():
            raise FileNotFoundError(path)
        # The benchmark runtime is isolated and receives no requests while a
        # snapshot is restored. Keep the stateless HTTP processes alive and
        # stop only queue consumers, so no job can observe the database during
        # import. Restarting every Frappe container concurrently can race in
        # the upstream image's shared-assets entrypoint and is unnecessary:
        # Frappe opens a fresh database connection for the next request.
        self.run(
            "stop",
            "queue-short",
            "queue-long",
        )
        self._import_database(path)
        self.run("exec", "-T", "redis-cache", "redis-cli", "FLUSHALL")
        self.run("exec", "-T", "redis-queue", "redis-cli", "FLUSHALL")
        self.run("start", "queue-short", "queue-long")
        self._wait_http_service("http://127.0.0.1:8080/api/method/ping")
        self._reset_http_service("http://127.0.0.1:9091/admin/reset")
        self._reset_http_service("http://127.0.0.1:9092/admin/reset")

    @staticmethod
    def _wait_http_service(
        url: str,
        *,
        attempts: int = 30,
        delay_seconds: float = 1.0,
        opener: Callable[..., Any] = urllib.request.urlopen,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        if attempts < 1:
            raise ValueError("attempts must be at least one")
        last_error: Exception | None = None
        for attempt in range(attempts):
            request = urllib.request.Request(url, method="GET")
            try:
                with opener(request, timeout=2) as response:
                    if response.status == 200:
                        return
                    last_error = RuntimeError(
                        f"readiness endpoint returned {response.status}"
                    )
            except OSError as error:
                last_error = error
            if attempt + 1 < attempts:
                sleeper(delay_seconds)
        raise RuntimeError(
            f"service did not become ready after {attempts} attempts: {url}"
        ) from last_error

    @staticmethod
    def _reset_http_service(
        url: str,
        *,
        attempts: int = 30,
        delay_seconds: float = 1.0,
        opener: Callable[..., Any] = urllib.request.urlopen,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        """Reset a restarted fault service once its HTTP listener is ready.

        Docker reports a container as started before the process inside it has
        necessarily accepted its first request.  Snapshot restoration restarts
        both fault services, so a bounded readiness retry is part of restoring a
        deterministic failure boundary rather than a tolerance for test errors.
        """
        if attempts < 1:
            raise ValueError("attempts must be at least one")
        last_error: Exception | None = None
        for attempt in range(attempts):
            request = urllib.request.Request(url, method="DELETE")
            try:
                with opener(request, timeout=2) as response:
                    if response.status == 200:
                        return
                    last_error = RuntimeError(
                        f"reset endpoint returned {response.status}"
                    )
            except OSError as error:
                last_error = error
            if attempt + 1 < attempts:
                sleeper(delay_seconds)
        raise RuntimeError(
            f"reset endpoint did not become ready after {attempts} attempts: {url}"
        ) from last_error
