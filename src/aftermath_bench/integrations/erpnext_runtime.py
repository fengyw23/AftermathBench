from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from ..schema import repository_root


def default_lock_path() -> Path:
    return repository_root() / "runtimes" / "erpnext" / "runtime.lock.json"


def load_runtime_lock(path: str | Path | None = None) -> dict[str, Any]:
    lock_path = Path(path) if path is not None else default_lock_path()
    with lock_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


@dataclass(frozen=True)
class ERPNextBuildPlan:
    source_directory: Path
    image: str
    expected_driver_revision: str
    source_refs: tuple[tuple[str, str, str], ...]
    fetch_commands: tuple[tuple[str, ...], ...]
    prepare_commands: tuple[tuple[str, ...], ...]
    build_command: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_directory": str(self.source_directory),
            "image": self.image,
            "expected_driver_revision": self.expected_driver_revision,
            "source_refs": [
                {"repository": repo, "tag": tag, "revision": revision}
                for repo, tag, revision in self.source_refs
            ],
            "fetch_commands": [list(command) for command in self.fetch_commands],
            "prepare_commands": [
                list(command) for command in self.prepare_commands
            ],
            "build_command": list(self.build_command),
        }


def create_build_plan(
    source_directory: str | Path,
    *,
    container_cli: str = "docker",
    lock: dict[str, Any] | None = None,
) -> ERPNextBuildPlan:
    runtime_lock = lock or load_runtime_lock()
    source = Path(source_directory).resolve()
    driver = runtime_lock["build_driver"]
    fetch_commands = (
        ("git", "init", str(source)),
        (
            "git",
            "-C",
            str(source),
            "remote",
            "add",
            "origin",
            str(driver["repository"]),
        ),
        (
            "git",
            "-C",
            str(source),
            "fetch",
            "--depth",
            "1",
            "origin",
            str(driver["revision"]),
        ),
        ("git", "-C", str(source), "checkout", "--detach", "FETCH_HEAD"),
    )
    patch = (
        repository_root()
        / "runtimes"
        / "erpnext"
        / "patches"
        / "pin-python-base.patch"
    ).resolve()
    prepare_commands = (
        (
            "git",
            "-C",
            str(source),
            "apply",
            "--check",
            str(patch),
        ),
        ("git", "-C", str(source), "apply", str(patch)),
    )
    build: list[str] = [
        container_cli,
        "build",
        "--pull",
        "--tag",
        str(runtime_lock["image"]),
        "--file",
        str(source / driver["containerfile"]),
    ]
    for name, value in sorted(runtime_lock["build_args"].items()):
        build.extend(("--build-arg", f"{name}={value}"))
    build.append(str(source))
    return ERPNextBuildPlan(
        source_directory=source,
        image=str(runtime_lock["image"]),
        expected_driver_revision=str(driver["revision"]),
        source_refs=tuple(
            (
                str(runtime_lock[name]["repository"]),
                str(runtime_lock[name]["tag"]),
                str(runtime_lock[name]["revision"]),
            )
            for name in ("frappe", "erpnext")
        ),
        fetch_commands=fetch_commands,
        prepare_commands=prepare_commands,
        build_command=tuple(build),
    )


def _run(command: Sequence[str]) -> None:
    subprocess.run(command, check=True)


def verify_source_refs(plan: ERPNextBuildPlan) -> None:
    for repository, tag, expected_revision in plan.source_refs:
        output = subprocess.check_output(
            ("git", "ls-remote", repository, f"refs/tags/{tag}"),
            text=True,
        ).strip()
        actual_revision = output.split(maxsplit=1)[0] if output else ""
        if actual_revision != expected_revision:
            raise RuntimeError(
                f"source tag mismatch for {repository} {tag}: "
                f"{actual_revision or '<missing>'} != {expected_revision}"
            )


def execute_build_plan(plan: ERPNextBuildPlan) -> None:
    if shutil.which(plan.build_command[0]) is None:
        raise RuntimeError(
            f"{plan.build_command[0]!r} is not installed; print the build plan "
            "with --dry-run or run it on a Docker/Podman host."
        )
    if plan.source_directory.exists() and any(plan.source_directory.iterdir()):
        raise RuntimeError(
            f"refusing to reuse non-empty source directory: "
            f"{plan.source_directory}"
        )
    verify_source_refs(plan)
    plan.source_directory.mkdir(parents=True, exist_ok=True)
    for command in plan.fetch_commands:
        _run(command)
    actual_revision = subprocess.check_output(
        ("git", "-C", str(plan.source_directory), "rev-parse", "HEAD"),
        text=True,
    ).strip()
    expected_revision = plan.expected_driver_revision
    if actual_revision != expected_revision:
        raise RuntimeError(
            f"build-driver revision mismatch: {actual_revision} != "
            f"{expected_revision}"
        )
    for command in plan.prepare_commands:
        _run(command)
    _run(plan.build_command)
