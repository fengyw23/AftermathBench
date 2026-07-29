from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

from ..schema import repository_root


def default_lock_path() -> Path:
    return repository_root() / "runtimes" / "forgejo" / "runtime.lock.json"


def default_audit_path() -> Path:
    return (
        repository_root()
        / "data"
        / "runtimes"
        / "forgejo-main"
        / "source_audit.json"
    )


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


@dataclass(frozen=True)
class ForgejoBuildPlan:
    source_directory: Path
    repository: str
    revision: str
    image: str
    containerfile: str
    fetch_commands: tuple[tuple[str, ...], ...]
    build_command: tuple[str, ...]
    expected_hashes: tuple[tuple[str, str], ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_directory": str(self.source_directory),
            "repository": self.repository,
            "revision": self.revision,
            "image": self.image,
            "containerfile": self.containerfile,
            "fetch_commands": [list(command) for command in self.fetch_commands],
            "build_command": list(self.build_command),
            "expected_hashes": [
                {"path": path, "sha256": digest}
                for path, digest in self.expected_hashes
            ],
        }


def create_build_plan(
    source_directory: str | Path,
    *,
    container_cli: str = "docker",
    lock: dict[str, Any] | None = None,
    audit: dict[str, Any] | None = None,
) -> ForgejoBuildPlan:
    runtime_lock = lock or _load(default_lock_path())
    source_audit = audit or _load(default_audit_path())
    source = Path(source_directory).resolve()
    upstream = runtime_lock["source"]
    revision = str(upstream["revision"])
    if revision != str(source_audit["revision"]):
        raise ValueError("Forgejo lock and source audit revisions disagree")
    build: list[str] = [
        container_cli,
        "build",
        "--pull",
        "--tag",
        str(runtime_lock["image"]),
        "--file",
        str(source / str(upstream["containerfile"])),
    ]
    for name, value in sorted(runtime_lock.get("build_args", {}).items()):
        build.extend(("--build-arg", f"{name}={value}"))
    build.append(str(source))
    return ForgejoBuildPlan(
        source_directory=source,
        repository=str(upstream["repository"]),
        revision=revision,
        image=str(runtime_lock["image"]),
        containerfile=str(upstream["containerfile"]),
        fetch_commands=(
            ("git", "init", str(source)),
            (
                "git",
                "-C",
                str(source),
                "remote",
                "add",
                "origin",
                str(upstream["repository"]),
            ),
            (
                "git",
                "-C",
                str(source),
                "fetch",
                "--depth",
                "1",
                "origin",
                revision,
            ),
            ("git", "-C", str(source), "checkout", "--detach", "FETCH_HEAD"),
        ),
        build_command=tuple(build),
        expected_hashes=tuple(
            (str(item["path"]), str(item["sha256"]))
            for item in source_audit["audited_paths"]
        ),
    )


def _run(command: Sequence[str]) -> None:
    subprocess.run(command, check=True)


def verify_checkout(plan: ForgejoBuildPlan) -> dict[str, Any]:
    actual_revision = subprocess.check_output(
        ("git", "-C", str(plan.source_directory), "rev-parse", "HEAD"),
        text=True,
    ).strip()
    checks: dict[str, bool] = {
        "revision": actual_revision == plan.revision,
    }
    actual_hashes = {}
    for relative, expected in plan.expected_hashes:
        path = plan.source_directory / relative
        actual = sha256(path.read_bytes()).hexdigest() if path.is_file() else ""
        actual_hashes[relative] = actual
        checks[f"sha256:{relative}"] = actual == expected
    result = {
        "revision": actual_revision,
        "expected_revision": plan.revision,
        "checks": checks,
        "actual_hashes": actual_hashes,
        "passed": all(checks.values()),
    }
    if not result["passed"]:
        failures = [name for name, passed in checks.items() if not passed]
        raise RuntimeError(f"Forgejo source verification failed: {failures}")
    return result


def checkout_and_verify(plan: ForgejoBuildPlan) -> dict[str, Any]:
    if plan.source_directory.exists() and any(plan.source_directory.iterdir()):
        raise RuntimeError(
            "refusing to reuse non-empty Forgejo source directory: "
            f"{plan.source_directory}"
        )
    plan.source_directory.mkdir(parents=True, exist_ok=True)
    for command in plan.fetch_commands:
        _run(command)
    return verify_checkout(plan)


def execute_build(plan: ForgejoBuildPlan) -> None:
    if shutil.which(plan.build_command[0]) is None:
        raise RuntimeError(
            f"{plan.build_command[0]!r} is not installed; run the build on "
            "a Docker/Podman host."
        )
    verify_checkout(plan)
    _run(plan.build_command)
