from __future__ import annotations

import hashlib
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .strict_json import load_json_strict

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_GIT_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_IDENTIFIER = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
_EXACT_MANIFEST_FIELDS = frozenset(
    {
        "schema_version",
        "excluded_files",
        "file_count",
        "total_bytes",
        "files",
    }
)
_EXACT_MANIFEST_ENTRY_FIELDS = frozenset({"path", "bytes", "sha256"})


class NativeFormalSourceError(ValueError):
    """Raised when repository sources are not exact and safely addressable."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def strict_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        value = load_json_strict(path)
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as error:
        raise NativeFormalSourceError(
            f"{label} must be strict readable JSON"
        ) from error
    if not isinstance(value, dict):
        raise NativeFormalSourceError(f"{label} must be a JSON object")
    return value


def repository_file(
    root: Path,
    value: str | Path,
    *,
    label: str,
) -> tuple[Path, str]:
    source = Path(value)
    candidate = source if source.is_absolute() else root / source
    if ".." in source.parts:
        raise NativeFormalSourceError(
            f"{label} must not contain parent traversal"
        )
    try:
        resolved = candidate.resolve(strict=True)
        relative = resolved.relative_to(root).as_posix()
    except (OSError, ValueError) as error:
        raise NativeFormalSourceError(
            f"{label} must be an existing file inside the repository root"
        ) from error
    if not resolved.is_file():
        raise NativeFormalSourceError(f"{label} must be a regular file")
    for parent in (resolved, *resolved.parents):
        if parent == root.parent:
            break
        if parent.is_symlink():
            raise NativeFormalSourceError(
                f"{label} must not traverse a symbolic link"
            )
        if parent == root:
            break
    return resolved, relative


def repository_directory(
    root: Path,
    value: str | Path,
    *,
    label: str,
) -> tuple[Path, str]:
    source = Path(value)
    candidate = source if source.is_absolute() else root / source
    if ".." in source.parts:
        raise NativeFormalSourceError(
            f"{label} must not contain parent traversal"
        )
    try:
        resolved = candidate.resolve(strict=True)
        relative = resolved.relative_to(root).as_posix()
    except (OSError, ValueError) as error:
        raise NativeFormalSourceError(
            f"{label} must be an existing directory inside the repository root"
        ) from error
    if not resolved.is_dir():
        raise NativeFormalSourceError(f"{label} must be a directory")
    for parent in (resolved, *resolved.parents):
        if parent == root.parent:
            break
        if parent.is_symlink():
            raise NativeFormalSourceError(
                f"{label} must not traverse a symbolic link"
            )
        if parent == root:
            break
    return resolved, relative


def require_sha256(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise NativeFormalSourceError(
            f"{label} must be a lowercase SHA-256 digest"
        )
    return value


def require_identifier(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
        raise NativeFormalSourceError(
            f"{label} must be a canonical lowercase identifier"
        )
    return value


def current_git_commit(root: Path) -> str:
    try:
        process = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise NativeFormalSourceError(
            "cannot determine the producer commit"
        ) from error
    commit = process.stdout.strip()
    if _GIT_COMMIT.fullmatch(commit) is None:
        raise NativeFormalSourceError(
            "repository HEAD is not a full Git commit"
        )
    return commit


def canonical_relative_path(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise NativeFormalSourceError(f"{label} must be non-empty")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or path.as_posix() != value:
        raise NativeFormalSourceError(
            f"{label} must be a canonical relative POSIX path"
        )
    return value


@dataclass(frozen=True)
class ExactFileManifest:
    path: Path
    relative_path: str
    root: Path
    entries: dict[str, dict[str, Any]]

    def require_file(self, path: Path, *, label: str) -> dict[str, Any]:
        try:
            relative = path.relative_to(self.root).as_posix()
        except ValueError as error:
            raise NativeFormalSourceError(
                f"{label} is outside its exact bundle"
            ) from error
        entry = self.entries.get(relative)
        if entry is None:
            raise NativeFormalSourceError(
                f"{label} is not bound by {self.relative_path}"
            )
        return entry


def load_exact_file_manifest(
    root: Path,
    value: str | Path,
    *,
    label: str,
) -> ExactFileManifest:
    path, relative = repository_file(root, value, label=label)
    payload = strict_object(path, label=label)
    if set(payload) != _EXACT_MANIFEST_FIELDS:
        raise NativeFormalSourceError(f"{label} fields are not exact")
    if payload["schema_version"] != "0.1":
        raise NativeFormalSourceError(
            f"{label} schema_version must be 0.1"
        )
    excluded = payload["excluded_files"]
    files = payload["files"]
    if (
        not isinstance(excluded, list)
        or len(excluded) != len(set(map(str, excluded)))
        or not isinstance(files, list)
    ):
        raise NativeFormalSourceError(
            f"{label} has an invalid file inventory"
        )
    excluded_paths = {
        canonical_relative_path(
            item,
            label=f"{label} excluded_files[]",
        )
        for item in excluded
    }
    if path.name not in excluded_paths:
        raise NativeFormalSourceError(
            f"{label} must explicitly exclude itself"
        )

    entries: dict[str, dict[str, Any]] = {}
    ordered_paths: list[str] = []
    observed_total = 0
    for index, item in enumerate(files):
        if (
            not isinstance(item, dict)
            or set(item) != _EXACT_MANIFEST_ENTRY_FIELDS
        ):
            raise NativeFormalSourceError(
                f"{label} files[{index}] fields are not exact"
            )
        item_path = canonical_relative_path(
            item["path"],
            label=f"{label} files[{index}].path",
        )
        if item_path in entries or item_path in excluded_paths:
            raise NativeFormalSourceError(
                f"{label} contains duplicate or excluded file {item_path}"
            )
        if (
            type(item["bytes"]) is not int
            or item["bytes"] < 0
        ):
            raise NativeFormalSourceError(
                f"{label} has an invalid byte length"
            )
        digest = require_sha256(
            item["sha256"],
            label=f"{label} files[{index}].sha256",
        )
        source = path.parent / item_path
        if not source.is_file():
            raise NativeFormalSourceError(
                f"{label} is missing declared file {item_path}"
            )
        if (
            source.stat().st_size != item["bytes"]
            or sha256_file(source) != digest
        ):
            raise NativeFormalSourceError(
                f"{label} file bytes drifted for {item_path}"
            )
        entries[item_path] = {
            "path": item_path,
            "bytes": item["bytes"],
            "sha256": digest,
        }
        ordered_paths.append(item_path)
        observed_total += item["bytes"]

    if ordered_paths != sorted(ordered_paths):
        raise NativeFormalSourceError(
            f"{label} file paths must be sorted"
        )
    discovered = tuple(path.parent.rglob("*"))
    symlinks = [candidate for candidate in discovered if candidate.is_symlink()]
    if symlinks:
        raise NativeFormalSourceError(
            f"{label} exact bundle contains a symbolic link"
        )
    actual = {
        candidate.relative_to(path.parent).as_posix()
        for candidate in discovered
        if candidate.is_file()
        and candidate.relative_to(path.parent).as_posix()
        not in excluded_paths
    }
    if actual != set(entries):
        raise NativeFormalSourceError(
            f"{label} is not an exact inventory of its bundle"
        )
    if (
        type(payload["file_count"]) is not int
        or type(payload["total_bytes"]) is not int
        or payload["file_count"] != len(entries)
        or payload["total_bytes"] != observed_total
    ):
        raise NativeFormalSourceError(
            f"{label} aggregate fields do not match its files"
        )
    return ExactFileManifest(
        path=path,
        relative_path=relative,
        root=path.parent,
        entries=entries,
    )


def validate_output_directory(root: Path, value: str) -> str:
    path = Path(value)
    if (
        path.is_absolute()
        or ".." in path.parts
        or path.as_posix() != value
        or len(path.parts) < 3
        or path.parts[0] != "data"
    ):
        raise NativeFormalSourceError(
            "output_directory must be a canonical path below data/"
        )
    try:
        (root / path).resolve().relative_to(root)
    except ValueError as error:
        raise NativeFormalSourceError(
            "output_directory escapes the repository root"
        ) from error
    return value


def write_formal_build_spec(
    path: str | Path,
    spec: dict[str, Any],
    *,
    root: str | Path,
) -> str:
    resolved_root = Path(root).resolve()
    output = Path(path)
    candidate = output if output.is_absolute() else resolved_root / output
    try:
        resolved = candidate.resolve()
        resolved.relative_to(resolved_root)
    except ValueError as error:
        raise NativeFormalSourceError(
            "build-spec output must stay inside the repository root"
        ) from error
    if resolved.exists():
        raise NativeFormalSourceError(
            "build-spec output already exists"
        )
    try:
        content = (
            json.dumps(
                spec,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise NativeFormalSourceError(
            "generated build spec is not strict JSON"
        ) from error
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_bytes(content)
    return resolved.relative_to(resolved_root).as_posix()


__all__ = [
    "ExactFileManifest",
    "NativeFormalSourceError",
    "canonical_relative_path",
    "current_git_commit",
    "load_exact_file_manifest",
    "repository_directory",
    "repository_file",
    "require_identifier",
    "require_sha256",
    "sha256_file",
    "strict_object",
    "validate_output_directory",
    "write_formal_build_spec",
]
