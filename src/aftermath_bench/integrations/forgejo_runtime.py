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
    pinned_containerfile: Path
    fetch_commands: tuple[tuple[str, ...], ...]
    build_command: tuple[str, ...]
    expected_hashes: tuple[tuple[str, str], ...]
    base_images: tuple[tuple[str, str, str], ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_directory": str(self.source_directory),
            "repository": self.repository,
            "revision": self.revision,
            "image": self.image,
            "containerfile": self.containerfile,
            "pinned_containerfile": str(self.pinned_containerfile),
            "fetch_commands": [list(command) for command in self.fetch_commands],
            "build_command": list(self.build_command),
            "expected_hashes": [
                {"path": path, "sha256": digest}
                for path, digest in self.expected_hashes
            ],
            "base_images": [
                {
                    "reference": reference,
                    "digest": digest,
                    "upstream_from": upstream_from,
                }
                for reference, digest, upstream_from in self.base_images
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
    pinned_containerfile = source / ".aftermath" / "Dockerfile.pinned"
    build: list[str] = [
        container_cli,
        "build",
        "--pull",
        "--tag",
        str(runtime_lock["image"]),
        "--file",
        str(pinned_containerfile),
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
        pinned_containerfile=pinned_containerfile,
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
        base_images=tuple(
            (
                str(item["reference"]),
                str(item["digest"]),
                str(item["upstream_from"]),
            )
            for _, item in sorted(runtime_lock["base_images"].items())
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


def materialize_pinned_containerfile(plan: ForgejoBuildPlan) -> dict[str, Any]:
    source_path = plan.source_directory / plan.containerfile
    content = source_path.read_text(encoding="utf-8")
    replacements: dict[str, str] = {}
    for reference, digest, upstream_from in plan.base_images:
        pinned = f"{reference}@{digest}"
        occurrences = content.count(upstream_from)
        if occurrences != 1:
            raise RuntimeError(
                "expected exactly one Forgejo base-image occurrence for "
                f"{upstream_from!r}, found {occurrences}"
            )
        content = content.replace(upstream_from, pinned, 1)
        replacements[upstream_from] = pinned
    make_fragment = (
        "make FORGEJO_GENERATE_SKIP_HASH=true "
        "RELEASE_VERSION=$RELEASE_VERSION"
    )
    versioned_make_fragment = (
        "make FORGEJO_GENERATE_SKIP_HASH=true "
        "GITEA_VERSION=$RELEASE_VERSION "
        "RELEASE_VERSION=$RELEASE_VERSION"
    )
    occurrences = content.count(make_fragment)
    if occurrences != 1:
        raise RuntimeError(
            "expected exactly one Forgejo release build command, "
            f"found {occurrences}"
        )
    content = content.replace(
        make_fragment,
        versioned_make_fragment,
        1,
    )
    replacements["build_version"] = versioned_make_fragment
    plan.pinned_containerfile.parent.mkdir(parents=True, exist_ok=True)
    plan.pinned_containerfile.write_text(content, encoding="utf-8")
    return {
        "path": str(plan.pinned_containerfile),
        "sha256": sha256(content.encode("utf-8")).hexdigest(),
        "replacements": replacements,
        "all_digests_pinned": all(
            f"{reference}@{digest}" in content
            for reference, digest, _ in plan.base_images
        ),
        "semantic_version_pinned": versioned_make_fragment in content,
    }


def checkout_and_verify(plan: ForgejoBuildPlan) -> dict[str, Any]:
    if plan.source_directory.exists() and any(plan.source_directory.iterdir()):
        raise RuntimeError(
            "refusing to reuse non-empty Forgejo source directory: "
            f"{plan.source_directory}"
        )
    plan.source_directory.mkdir(parents=True, exist_ok=True)
    for command in plan.fetch_commands:
        _run(command)
    verification = verify_checkout(plan)
    verification["pinned_containerfile"] = materialize_pinned_containerfile(
        plan
    )
    return verification


def execute_build(plan: ForgejoBuildPlan) -> dict[str, Any]:
    if shutil.which(plan.build_command[0]) is None:
        raise RuntimeError(
            f"{plan.build_command[0]!r} is not installed; run the build on "
            "a Docker/Podman host."
        )
    verify_checkout(plan)
    pinned = materialize_pinned_containerfile(plan)
    _run(plan.build_command)
    image_id = subprocess.check_output(
        (
            plan.build_command[0],
            "image",
            "inspect",
            "--format",
            "{{.Id}}",
            plan.image,
        ),
        text=True,
    ).strip()
    if not image_id.startswith("sha256:"):
        raise RuntimeError(f"invalid Forgejo image ID: {image_id!r}")
    return {
        "image": plan.image,
        "image_id": image_id,
        "pinned_containerfile": pinned,
        "built_from_verified_revision": plan.revision,
    }
