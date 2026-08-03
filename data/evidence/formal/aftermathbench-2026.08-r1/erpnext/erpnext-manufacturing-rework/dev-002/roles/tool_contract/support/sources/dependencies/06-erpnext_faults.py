from __future__ import annotations

import json
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Sequence


ERP_NEXT_FAULT_VARIANTS = (
    "request_not_reached",
    "database_committed_response_lost",
    "after_commit_enqueue_failed",
    "async_job_pending",
)


def _json_request(
    base_url: str,
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}{path}",
        data=data,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            body = response.read()
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"fault-control request failed ({error.code}): {detail}"
        ) from error
    return json.loads(body) if body else {}


@dataclass(frozen=True)
class ComposeWorkerControl:
    compose_file: Path
    project_name: str = "aftermath-erpnext"
    container_cli: str = "docker"
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run

    def _command(self, action: str) -> tuple[str, ...]:
        return (
            self.container_cli,
            "compose",
            "--project-name",
            self.project_name,
            "--file",
            str(self.compose_file),
            action,
            "queue-short",
            "queue-long",
        )

    def start(self) -> None:
        self.runner(self._command("start"), check=True)

    def stop(self) -> None:
        self.runner(self._command("stop"), check=True)


class ERPNextFaultController:
    def __init__(
        self,
        *,
        gateway_control_url: str = "http://127.0.0.1:9091",
        toxiproxy_url: str = "http://127.0.0.1:8474",
        queue_proxy_name: str = "redis_queue",
        worker_control: ComposeWorkerControl | None = None,
        requester: Callable[
            [str, str, str, dict[str, Any] | None],
            dict[str, Any],
        ] = _json_request,
    ):
        self.gateway_control_url = gateway_control_url
        self.toxiproxy_url = toxiproxy_url
        self.queue_proxy_name = queue_proxy_name
        self.worker_control = worker_control
        self.requester = requester

    def set_gateway_mode(self, mode: str) -> None:
        response = self.requester(
            self.gateway_control_url,
            "PUT",
            "/mode",
            {"mode": mode},
        )
        if response.get("mode") != mode:
            raise RuntimeError(f"gateway did not enter {mode!r}: {response}")

    def set_queue_enabled(self, enabled: bool) -> None:
        path = f"/proxies/{self.queue_proxy_name}"
        current = self.requester(self.toxiproxy_url, "GET", path, None)
        update = {
            "name": current["name"],
            "listen": current["listen"],
            "upstream": current["upstream"],
            "enabled": enabled,
        }
        response = self.requester(
            self.toxiproxy_url,
            "POST",
            path,
            update,
        )
        if bool(response.get("enabled")) is not enabled:
            raise RuntimeError(
                f"queue proxy did not enter enabled={enabled}: {response}"
            )

    def restore(self) -> None:
        self.set_gateway_mode("normal")
        self.set_queue_enabled(True)
        if self.worker_control:
            self.worker_control.start()

    def arm(self, variant: str) -> None:
        if variant not in ERP_NEXT_FAULT_VARIANTS:
            raise ValueError(f"unknown ERPNext fault variant: {variant}")
        self.restore()
        if variant == "request_not_reached":
            self.set_gateway_mode("suppress_request")
        elif variant == "database_committed_response_lost":
            self.set_gateway_mode("drop_response")
        elif variant == "after_commit_enqueue_failed":
            self.set_queue_enabled(False)
            self.set_gateway_mode("drop_response")
        elif variant == "async_job_pending":
            if not self.worker_control:
                raise RuntimeError("async_job_pending requires worker control")
            self.worker_control.stop()
            self.set_gateway_mode("drop_response")

    def disarm_transport_after_failure(self, variant: str) -> None:
        """Make investigation possible without erasing the hidden outcome."""
        if variant not in ERP_NEXT_FAULT_VARIANTS:
            raise ValueError(f"unknown ERPNext fault variant: {variant}")
        self.set_gateway_mode("normal")
        self.set_queue_enabled(True)
        # A pending job must remain pending at the recovery boundary. The
        # agent-facing operational tool, not this harness method, resumes it.
        if variant != "async_job_pending" and self.worker_control:
            self.worker_control.start()


def default_worker_control(
    repository_root: str | Path,
    *,
    container_cli: str = "docker",
) -> ComposeWorkerControl:
    return ComposeWorkerControl(
        compose_file=(
            Path(repository_root)
            / "runtimes"
            / "erpnext"
            / "compose.yaml"
        ),
        container_cli=container_cli,
    )
