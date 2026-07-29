from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..schema import repository_root


def default_lock_path() -> Path:
    return (
        repository_root()
        / "runtimes"
        / "kubernetes"
        / "runtime.lock.json"
    )


@dataclass(frozen=True)
class KubernetesStack:
    cluster_name: str
    node_image: str
    config: Path
    kind: str = "kind"
    kubectl: str = "kubectl"

    @classmethod
    def from_repository(cls) -> "KubernetesStack":
        root = repository_root()
        lock = json.loads(default_lock_path().read_text(encoding="utf-8"))
        return cls(
            cluster_name=str(lock["cluster_name"]),
            node_image=str(lock["kubernetes"]["node_image"]),
            config=root / "runtimes" / "kubernetes" / "kind-config.yaml",
        )

    @property
    def context(self) -> str:
        return f"kind-{self.cluster_name}"

    def _require_commands(self) -> None:
        missing = [
            command
            for command in (self.kind, self.kubectl)
            if shutil.which(command) is None
        ]
        if missing:
            raise RuntimeError(
                "missing Kubernetes runtime commands: "
                + ", ".join(missing)
            )

    def _run(self, command: tuple[str, ...]) -> str:
        completed = subprocess.run(
            command,
            text=True,
            capture_output=True,
            check=False,
        )
        if completed.returncode:
            raise RuntimeError(
                f"command failed ({completed.returncode}): "
                f"{' '.join(command)}\n{completed.stderr.strip()}"
            )
        return completed.stdout.strip()

    def clusters(self) -> tuple[str, ...]:
        self._require_commands()
        output = self._run((self.kind, "get", "clusters"))
        return tuple(line.strip() for line in output.splitlines() if line.strip())

    def up(self) -> dict[str, Any]:
        self._require_commands()
        if self.cluster_name not in self.clusters():
            self._run(
                (
                    self.kind,
                    "create",
                    "cluster",
                    "--name",
                    self.cluster_name,
                    "--config",
                    str(self.config),
                    "--image",
                    self.node_image,
                    "--wait",
                    "180s",
                )
            )
        version = json.loads(
            self._run(
                (
                    self.kubectl,
                    "--context",
                    self.context,
                    "version",
                    "-o",
                    "json",
                )
            )
        )
        return {
            "cluster_name": self.cluster_name,
            "context": self.context,
            "node_image": self.node_image,
            "server_version": version["serverVersion"]["gitVersion"],
        }

    def down(self) -> None:
        self._require_commands()
        if self.cluster_name in self.clusters():
            self._run(
                (
                    self.kind,
                    "delete",
                    "cluster",
                    "--name",
                    self.cluster_name,
                )
            )
