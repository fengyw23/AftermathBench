from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import tempfile
import time
import uuid
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..schema import repository_root

_BUNDLE_SCHEMA_VERSION = "1.0"
_BUNDLE_CAPTURE_MODE = "etcd_snapshot_and_quiesced_registry_sqlite"
_BUNDLE_FILES = {
    "etcd": "etcd.snapshot.db",
    "external_registry": "webhook-sink.sqlite3",
}
_ETCD_MANIFEST_PATH = "/etc/kubernetes/manifests/etcd.yaml"
_CONTROL_PLANE_MANIFEST_ROOT = "/etc/kubernetes/manifests"
_REPLAY_TOKEN_ANNOTATION = "aftermathbench.dev/replay-token"
_ETCD_BUNDLE_HOST_ROOT = "/var/lib/aftermath-etcd-bundles"
_ETCD_BUNDLE_MOUNT = "/aftermath-etcd-bundles"
_ETCD_BUNDLE_VOLUME = "aftermath-etcd-bundles"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _patch_etcd_manifest_snapshot_mount(text: str) -> str:
    """Add one stable host mount without depending on a YAML package."""

    if f"name: {_ETCD_BUNDLE_VOLUME}" in text:
        if (
            f"mountPath: {_ETCD_BUNDLE_MOUNT}" not in text
            or f"path: {_ETCD_BUNDLE_HOST_ROOT}" not in text
        ):
            raise ValueError("partial AftermathBench etcd snapshot mount")
        return text
    lines = text.splitlines()
    mount_indexes = [
        index
        for index, line in enumerate(lines)
        if line == "    volumeMounts:"
    ]
    volume_indexes = [
        index for index, line in enumerate(lines) if line == "  volumes:"
    ]
    if len(mount_indexes) != 1 or len(volume_indexes) != 1:
        raise ValueError("unsupported kubeadm etcd static-pod manifest shape")
    mount_index = mount_indexes[0]
    lines[mount_index + 1 : mount_index + 1] = [
        f"    - mountPath: {_ETCD_BUNDLE_MOUNT}",
        f"      name: {_ETCD_BUNDLE_VOLUME}",
    ]
    volume_index = volume_indexes[0] + 2
    lines[volume_index + 1 : volume_index + 1] = [
        "  - hostPath:",
        f"      path: {_ETCD_BUNDLE_HOST_ROOT}",
        "      type: DirectoryOrCreate",
        f"    name: {_ETCD_BUNDLE_VOLUME}",
    ]
    return "\n".join(lines) + "\n"


def _patch_etcd_manifest_data_path(text: str, data_path: str) -> str:
    """Point the kubeadm etcd static pod at one restored data directory."""

    if not data_path.startswith(f"{_ETCD_BUNDLE_HOST_ROOT}/restores/"):
        raise ValueError("etcd restore path escaped the dedicated host root")
    lines = text.splitlines()
    name_indexes = [
        index
        for index, line in enumerate(lines)
        if line == "    name: etcd-data"
    ]
    if len(name_indexes) != 1:
        raise ValueError("could not identify the etcd-data hostPath volume")
    name_index = name_indexes[0]
    item_start = None
    for index in range(name_index - 1, -1, -1):
        if lines[index].startswith("  - "):
            item_start = index
            break
    if item_start is None or lines[item_start].strip() != "- hostPath:":
        raise ValueError("etcd-data is not backed by a hostPath volume")
    path_indexes = [
        index
        for index in range(item_start + 1, name_index)
        if lines[index].strip().startswith("path:")
    ]
    if len(path_indexes) != 1:
        raise ValueError("could not identify the etcd-data hostPath path")
    path_index = path_indexes[0]
    indentation = lines[path_index][: len(lines[path_index]) - len(lines[path_index].lstrip())]
    lines[path_index] = f"{indentation}path: {data_path}"
    return "\n".join(lines) + "\n"


def _patch_static_pod_manifest_replay_token(text: str, token: str) -> str:
    """Force one kubeadm static Pod to restart without crash-loop backoff."""

    if len(token) != 32 or any(
        character not in "0123456789abcdef" for character in token
    ):
        raise ValueError(
            "replay token must be 32 lowercase hexadecimal characters"
        )
    lines = text.splitlines()
    metadata_indexes = [
        index for index, line in enumerate(lines) if line == "metadata:"
    ]
    if len(metadata_indexes) != 1:
        raise ValueError("unsupported kubeadm static-pod metadata shape")
    metadata_index = metadata_indexes[0]
    block_end = len(lines)
    for index in range(metadata_index + 1, len(lines)):
        if lines[index] and not lines[index][0].isspace():
            block_end = index
            break
    annotation_headers = [
        index
        for index in range(metadata_index + 1, block_end)
        if lines[index] == "  annotations:"
    ]
    token_prefix = f"    {_REPLAY_TOKEN_ANNOTATION}:"
    token_indexes = [
        index
        for index in range(metadata_index + 1, block_end)
        if lines[index].startswith(token_prefix)
    ]
    if len(annotation_headers) > 1 or len(token_indexes) > 1:
        raise ValueError("ambiguous kubeadm static-pod annotations")
    token_line = f"{token_prefix} {token}"
    if token_indexes:
        if not annotation_headers:
            raise ValueError("replay token is outside an annotations mapping")
        lines[token_indexes[0]] = token_line
    elif annotation_headers:
        lines.insert(annotation_headers[0] + 1, token_line)
    else:
        lines[metadata_index + 1 : metadata_index + 1] = [
            "  annotations:",
            token_line,
        ]
    return "\n".join(lines) + "\n"


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
    docker: str = "docker"
    etcdutl: str = "etcdutl"
    external_registry_container: str = "aftermath-interaction-registry"

    @classmethod
    def from_repository(cls) -> KubernetesStack:
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

    @property
    def node_container(self) -> str:
        return f"{self.cluster_name}-control-plane"

    def _require_bundle_commands(self) -> None:
        self._require_commands()
        missing = [
            command
            for command in (self.docker, self.etcdutl)
            if shutil.which(command) is None
        ]
        if missing:
            raise RuntimeError(
                "missing Kubernetes bundle commands: " + ", ".join(missing)
            )

    def _docker(self, *arguments: str) -> str:
        return self._run((self.docker, *arguments))

    def _etcd_container(self) -> str:
        return self._control_plane_container("etcd")

    def _control_plane_container(self, component: str) -> str:
        output = self._docker(
            "exec",
            self.node_container,
            "crictl",
            "ps",
            "--name",
            component,
            "--state",
            "Running",
            "-q",
        )
        matches = tuple(line.strip() for line in output.splitlines() if line.strip())
        if len(matches) != 1:
            raise RuntimeError(
                f"expected exactly one running {component} container; "
                f"observed={matches}"
            )
        return matches[0]

    def _wait_control_plane_container_restarted(
        self,
        component: str,
        previous_container: str,
        *,
        attempts: int = 180,
        delay_seconds: float = 1.0,
    ) -> str:
        last_error = ""
        for _attempt in range(attempts):
            try:
                current = self._control_plane_container(component)
                if current != previous_container:
                    return current
            except RuntimeError as error:
                last_error = str(error)
            time.sleep(delay_seconds)
        raise RuntimeError(
            f"{component} static pod did not restart: "
            f"previous={previous_container}, last_error={last_error}"
        )

    def _restart_control_plane_consumers(
        self,
        previous: dict[str, str],
        *,
        attempts: int = 180,
        delay_seconds: float = 1.0,
    ) -> dict[str, str]:
        """Clear API and controller caches after rewinding the keyspace."""

        components = (
            "kube-apiserver",
            "kube-controller-manager",
            "kube-scheduler",
        )
        if set(previous) != set(components) or any(
            not previous[component] for component in components
        ):
            raise ValueError("previous control-plane identities are incomplete")
        replay_token = uuid.uuid4().hex
        for component in components:
            path = f"{_CONTROL_PLANE_MANIFEST_ROOT}/{component}.yaml"
            original = self._docker(
                "exec", self.node_container, "cat", path
            )
            patched = _patch_static_pod_manifest_replay_token(
                original,
                replay_token,
            )
            with tempfile.TemporaryDirectory(
                prefix=f"aftermath-{component}-manifest-"
            ) as raw:
                local = Path(raw) / f"{component}.yaml"
                local.write_text(patched, encoding="utf-8", newline="\n")
                remote = f"{path}.aftermath"
                self._docker(
                    "cp", str(local), f"{self.node_container}:{remote}"
                )
                self._docker(
                    "exec", self.node_container, "mv", remote, path
                )
        restarted = {
            component: self._wait_control_plane_container_restarted(
                component,
                previous[component],
                attempts=attempts,
                delay_seconds=delay_seconds,
            )
            for component in components
        }
        self._wait_api_ready(
            attempts=attempts,
            delay_seconds=delay_seconds,
        )
        return restarted

    def _read_etcd_manifest(self) -> str:
        return self._docker(
            "exec", self.node_container, "cat", _ETCD_MANIFEST_PATH
        )

    def _replace_etcd_manifest(self, content: str) -> None:
        with tempfile.TemporaryDirectory(prefix="aftermath-etcd-manifest-") as raw:
            local = Path(raw) / "etcd.yaml"
            local.write_text(content, encoding="utf-8", newline="\n")
            remote = f"{_ETCD_MANIFEST_PATH}.aftermath"
            self._docker("cp", str(local), f"{self.node_container}:{remote}")
            self._docker(
                "exec",
                self.node_container,
                "mv",
                remote,
                _ETCD_MANIFEST_PATH,
            )

    def _wait_api_ready(
        self,
        *,
        attempts: int = 180,
        delay_seconds: float = 1.0,
    ) -> None:
        command = (
            self.kubectl,
            "--context",
            self.context,
            "get",
            "--raw=/readyz",
        )
        last_error = ""
        for _attempt in range(attempts):
            try:
                if self._run(command).strip() == "ok":
                    return
            except RuntimeError as error:
                last_error = str(error)
            time.sleep(delay_seconds)
        raise RuntimeError(f"Kubernetes API did not recover: {last_error}")

    def _wait_etcd_restarted(
        self,
        previous_container: str,
        *,
        attempts: int = 180,
        delay_seconds: float = 1.0,
    ) -> str:
        last_error = ""
        restarted_container = ""
        for _attempt in range(attempts):
            try:
                current = self._etcd_container()
                if current != previous_container:
                    restarted_container = current
                    break
            except RuntimeError as error:
                last_error = str(error)
            time.sleep(delay_seconds)
        if restarted_container:
            self._wait_api_ready(
                attempts=attempts,
                delay_seconds=delay_seconds,
            )
            return restarted_container
        raise RuntimeError(
            "etcd static pod did not restart after manifest replacement: "
            f"previous={previous_container}, last_error={last_error}"
        )

    def _ensure_snapshot_mount(self) -> None:
        self._docker(
            "exec",
            self.node_container,
            "mkdir",
            "-p",
            f"{_ETCD_BUNDLE_HOST_ROOT}/inputs",
            f"{_ETCD_BUNDLE_HOST_ROOT}/restores",
        )
        original = self._read_etcd_manifest()
        patched = _patch_etcd_manifest_snapshot_mount(original)
        if patched != original:
            previous_etcd = self._etcd_container()
            self._replace_etcd_manifest(patched)
            self._wait_etcd_restarted(previous_etcd)

    def prepare_snapshot_runtime(self) -> dict[str, str]:
        """Install the stable etcd bundle mount before a boundary is built."""

        self._require_bundle_commands()
        self._ensure_snapshot_mount()
        return {
            "cluster_name": self.cluster_name,
            "node_container": self.node_container,
            "etcd_bundle_host_root": _ETCD_BUNDLE_HOST_ROOT,
            "etcd_bundle_mount": _ETCD_BUNDLE_MOUNT,
        }

    def _stop_registry(self) -> None:
        self._docker("stop", self.external_registry_container)

    def _start_registry(self) -> None:
        self._docker("start", self.external_registry_container)
        # The service is intentionally tested through its public health route.
        import urllib.request

        last_error = ""
        for _attempt in range(60):
            try:
                with urllib.request.urlopen(
                    "http://127.0.0.1:9092/health", timeout=2
                ) as response:
                    if response.status == 200:
                        return
            except Exception as error:  # noqa: BLE001
                last_error = str(error)
            time.sleep(1)
        raise RuntimeError(f"external registry did not recover: {last_error}")

    @staticmethod
    def _snapshot_sqlite(source: Path, destination: Path) -> None:
        if not source.is_file():
            raise FileNotFoundError(source)
        # The live database belongs to the unprivileged container user. Once
        # the service is stopped, copy the complete WAL set to a runner-owned
        # staging directory before asking SQLite to compact it into one file.
        # Opening the bind-mounted source directly may attempt WAL recovery and
        # fail because the runner cannot write the container-owned database.
        with tempfile.TemporaryDirectory(
            prefix="aftermath-registry-snapshot-",
            dir=destination.parent,
        ) as raw:
            staging = Path(raw) / source.name
            shutil.copy2(source, staging)
            for suffix in ("-wal", "-shm"):
                sidecar = Path(f"{source}{suffix}")
                if sidecar.is_file():
                    shutil.copy2(sidecar, Path(f"{staging}{suffix}"))
            with (
                closing(sqlite3.connect(staging)) as input_database,
                closing(sqlite3.connect(destination)) as output_database,
            ):
                input_database.backup(output_database)

    @staticmethod
    def _restore_sqlite(source: Path, destination: Path) -> None:
        if not source.is_file():
            raise FileNotFoundError(source)
        destination.parent.mkdir(parents=True, exist_ok=True)
        for path in (
            destination,
            Path(f"{destination}-wal"),
            Path(f"{destination}-shm"),
        ):
            if path.exists():
                path.unlink()
        shutil.copy2(source, destination)

    def snapshot_bundle(
        self,
        destination: str | Path,
        *,
        registry_database: str | Path,
    ) -> dict[str, Any]:
        """Capture etcd and the external idempotency ledger at one boundary."""

        self._require_bundle_commands()
        bundle = Path(destination).resolve()
        registry = Path(registry_database).resolve()
        if bundle.exists():
            raise FileExistsError(bundle)
        bundle.parent.mkdir(parents=True, exist_ok=True)
        temporary: Path | None = Path(
            tempfile.mkdtemp(prefix=f".{bundle.name}.incomplete-", dir=bundle.parent)
        )
        registry_stopped = False
        try:
            self._ensure_snapshot_mount()
            self._stop_registry()
            registry_stopped = True
            etcd_container = self._etcd_container()
            remote_snapshot = f"{_ETCD_BUNDLE_MOUNT}/snapshot.db"
            self._docker(
                "exec",
                self.node_container,
                "rm",
                "-f",
                f"{_ETCD_BUNDLE_HOST_ROOT}/snapshot.db",
            )
            self._docker(
                "exec",
                self.node_container,
                "crictl",
                "exec",
                etcd_container,
                "etcdctl",
                "--endpoints=https://127.0.0.1:2379",
                "--cacert=/etc/kubernetes/pki/etcd/ca.crt",
                "--cert=/etc/kubernetes/pki/etcd/healthcheck-client.crt",
                "--key=/etc/kubernetes/pki/etcd/healthcheck-client.key",
                "snapshot",
                "save",
                remote_snapshot,
            )
            etcd_path = temporary / _BUNDLE_FILES["etcd"]
            self._docker(
                "cp",
                f"{self.node_container}:{_ETCD_BUNDLE_HOST_ROOT}/snapshot.db",
                str(etcd_path),
            )
            registry_path = temporary / _BUNDLE_FILES["external_registry"]
            self._snapshot_sqlite(registry, registry_path)
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
                "cluster_name": self.cluster_name,
                "node_image": self.node_image,
                "files": files,
            }
            (temporary / "bundle.json").write_text(
                json.dumps(manifest, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            os.replace(temporary, bundle)
            temporary = None
            return manifest
        finally:
            if registry_stopped:
                self._start_registry()
            if temporary is not None and temporary.exists():
                shutil.rmtree(temporary)

    def _validated_bundle(self, source: str | Path) -> tuple[Path, dict[str, Any]]:
        bundle = Path(source).resolve()
        manifest_path = bundle / "bundle.json"
        if not manifest_path.is_file():
            raise FileNotFoundError(manifest_path)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if (
            not isinstance(manifest, dict)
            or manifest.get("schema_version") != _BUNDLE_SCHEMA_VERSION
            or manifest.get("capture_mode") != _BUNDLE_CAPTURE_MODE
            or manifest.get("cluster_name") != self.cluster_name
            or manifest.get("node_image") != self.node_image
            or set(manifest.get("files", {})) != set(_BUNDLE_FILES)
        ):
            raise ValueError("invalid Kubernetes native bundle manifest")
        for key, filename in _BUNDLE_FILES.items():
            declaration = manifest["files"].get(key)
            path = bundle / filename
            if (
                not isinstance(declaration, dict)
                or set(declaration) != {"path", "bytes", "sha256"}
                or declaration.get("path") != filename
                or not path.is_file()
                or path.stat().st_size != int(declaration["bytes"])
                or _sha256_file(path) != str(declaration["sha256"])
            ):
                raise ValueError(f"Kubernetes native bundle file drift: {key}")
        return bundle, manifest

    def restore_bundle(
        self,
        source: str | Path,
        *,
        registry_database: str | Path,
    ) -> dict[str, Any]:
        """Restore one exact etcd keyspace and external registry database."""

        self._require_bundle_commands()
        bundle, manifest = self._validated_bundle(source)
        registry = Path(registry_database).resolve()
        self._ensure_snapshot_mount()
        restore_token = uuid.uuid4().hex
        remote_data_host = f"{_ETCD_BUNDLE_HOST_ROOT}/restores/{restore_token}"
        etcd_container = self._etcd_container()
        control_plane_before_restore = {
            component: self._control_plane_container(component)
            for component in (
                "kube-apiserver",
                "kube-controller-manager",
                "kube-scheduler",
            )
        }
        node_ip = self._docker(
            "inspect",
            "--format",
            "{{range.NetworkSettings.Networks}}{{.IPAddress}}{{end}}",
            self.node_container,
        ).strip()
        if not node_ip:
            raise RuntimeError("kind control-plane container has no IP address")
        registry_stopped = False
        restarted_control_plane: dict[str, str] = {}
        try:
            self._stop_registry()
            registry_stopped = True
            with tempfile.TemporaryDirectory(
                prefix="aftermath-etcd-restore-"
            ) as raw:
                local_data = Path(raw) / "member-data"
                self._run(
                    (
                        self.etcdutl,
                        "snapshot",
                        "restore",
                        str(bundle / _BUNDLE_FILES["etcd"]),
                        f"--data-dir={local_data}",
                        f"--name={self.node_container}",
                        (
                            "--initial-cluster="
                            f"{self.node_container}=https://{node_ip}:2380"
                        ),
                        (
                            "--initial-advertise-peer-urls="
                            f"https://{node_ip}:2380"
                        ),
                        f"--initial-cluster-token=aftermath-{restore_token}",
                        "--bump-revision=1000000000",
                        "--mark-compacted",
                    )
                )
                self._docker(
                    "exec",
                    self.node_container,
                    "mkdir",
                    "-p",
                    remote_data_host,
                )
                self._docker(
                    "cp",
                    f"{local_data}/.",
                    f"{self.node_container}:{remote_data_host}",
                )
            original = self._read_etcd_manifest()
            patched = _patch_etcd_manifest_data_path(original, remote_data_host)
            previous_etcd = etcd_container
            self._replace_etcd_manifest(patched)
            self._wait_etcd_restarted(previous_etcd)
            restarted_control_plane = self._restart_control_plane_consumers(
                control_plane_before_restore
            )
            self._restore_sqlite(
                bundle / _BUNDLE_FILES["external_registry"], registry
            )
        finally:
            if registry_stopped:
                self._start_registry()
        return manifest | {
            "restore_token": restore_token,
            "restarted_control_plane": restarted_control_plane,
        }
