from __future__ import annotations

import json
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any


class KubernetesCommandError(RuntimeError):
    pass


@dataclass(frozen=True)
class KubernetesCommandResult:
    command: tuple[str, ...]
    stdout: str
    stderr: str


class KubernetesApi:
    """Small, auditable wrapper around ordinary kubectl operations."""

    def __init__(
        self,
        *,
        kubectl: str = "kubectl",
        context: str = "kind-aftermath-kubernetes",
    ) -> None:
        self.kubectl = kubectl
        self.context = context

    def _run(
        self,
        arguments: Sequence[str],
        *,
        stdin: str | None = None,
    ) -> KubernetesCommandResult:
        command = (
            self.kubectl,
            "--context",
            self.context,
            *tuple(arguments),
        )
        completed = subprocess.run(
            command,
            input=stdin,
            text=True,
            capture_output=True,
            check=False,
        )
        if completed.returncode:
            raise KubernetesCommandError(
                f"kubectl failed ({completed.returncode}): "
                f"{completed.stderr.strip()}"
            )
        return KubernetesCommandResult(
            command=command,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )

    def apply(self, manifest: Mapping[str, Any]) -> dict[str, Any]:
        result = self._run(
            ("apply", "-f", "-", "-o", "json"),
            stdin=json.dumps(manifest),
        )
        return json.loads(result.stdout)

    def get(
        self,
        resource: str,
        name: str,
        *,
        namespace: str | None = None,
    ) -> dict[str, Any]:
        arguments = ["get", resource, name, "-o", "json"]
        if namespace:
            arguments.extend(("-n", namespace))
        return json.loads(self._run(arguments).stdout)

    def list(
        self,
        resource: str,
        *,
        namespace: str | None = None,
        selector: str | None = None,
    ) -> list[dict[str, Any]]:
        arguments = ["get", resource, "-o", "json"]
        if namespace:
            arguments.extend(("-n", namespace))
        if selector:
            arguments.extend(("-l", selector))
        payload = json.loads(self._run(arguments).stdout)
        return list(payload.get("items", []))

    def patch(
        self,
        resource: str,
        name: str,
        patch: Mapping[str, Any],
        *,
        namespace: str | None = None,
        patch_type: str = "merge",
    ) -> dict[str, Any]:
        arguments = [
            "patch",
            resource,
            name,
            "--type",
            patch_type,
            "-p",
            json.dumps(patch, separators=(",", ":")),
            "-o",
            "json",
        ]
        if namespace:
            arguments.extend(("-n", namespace))
        return json.loads(self._run(arguments).stdout)

    def delete(
        self,
        resource: str,
        name: str,
        *,
        namespace: str | None = None,
        ignore_not_found: bool = True,
    ) -> str:
        arguments = ["delete", resource, name]
        if namespace:
            arguments.extend(("-n", namespace))
        if ignore_not_found:
            arguments.append("--ignore-not-found=true")
        return self._run(arguments).stdout.strip()

    def wait_deleted(
        self,
        resource: str,
        name: str,
        *,
        namespace: str | None = None,
        timeout: str = "120s",
    ) -> str:
        arguments = [
            "wait",
            "--for=delete",
            f"{resource}/{name}",
            f"--timeout={timeout}",
        ]
        if namespace:
            arguments.extend(("-n", namespace))
        return self._run(arguments).stdout.strip()

    def wait_rollout(
        self,
        deployment: str,
        *,
        namespace: str,
        timeout: str = "180s",
    ) -> str:
        return self._run(
            (
                "rollout",
                "status",
                f"deployment/{deployment}",
                "-n",
                namespace,
                f"--timeout={timeout}",
            )
        ).stdout.strip()

    def events(
        self,
        *,
        namespace: str,
    ) -> list[dict[str, Any]]:
        return self.list("events", namespace=namespace)

    def taint_node(
        self,
        name: str,
        taint: str,
        *,
        overwrite: bool = True,
    ) -> str:
        arguments = ["taint", "node", name, taint]
        if overwrite:
            arguments.append("--overwrite")
        return self._run(arguments).stdout.strip()

    def remove_node_taint(self, name: str, key: str) -> str:
        return self._run(
            ("taint", "node", name, f"{key}-")
        ).stdout.strip()
