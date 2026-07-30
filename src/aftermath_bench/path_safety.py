from __future__ import annotations

from pathlib import Path, PurePosixPath


def safe_relative_path(
    root: str | Path,
    value: str,
    *,
    required_prefix: str | None = None,
    must_exist: bool = False,
    require_file: bool = False,
) -> Path:
    """Resolve a repository artifact path without allowing path escape.

    Manifest paths are deliberately POSIX-relative so the same manifest is
    portable across Linux CI and Windows development hosts. Existing symbolic
    links are rejected because containment after ``resolve`` alone is not
    enough to make a frozen file list auditable.
    """

    if not isinstance(value, str) or not value:
        raise ValueError("artifact path must be a non-empty string")
    if "\\" in value:
        raise ValueError("artifact paths must use POSIX separators")
    relative = PurePosixPath(value)
    if relative.is_absolute() or relative.anchor:
        raise ValueError(f"artifact path must be relative: {value}")
    if any(":" in part for part in relative.parts):
        raise ValueError(f"artifact path must not contain a drive: {value}")
    if any(part in {"", ".", ".."} for part in relative.parts):
        raise ValueError(f"artifact path is not canonical: {value}")
    if relative.as_posix() != value:
        raise ValueError(f"artifact path is not canonical POSIX: {value}")
    if required_prefix is not None and (
        not relative.parts or relative.parts[0] != required_prefix
    ):
        raise ValueError(
            f"artifact path must be under {required_prefix}/: {value}"
        )

    resolved_root = Path(root).resolve()
    candidate = resolved_root.joinpath(*relative.parts)
    cursor = resolved_root
    for part in relative.parts:
        cursor = cursor / part
        if cursor.exists() and cursor.is_symlink():
            raise ValueError(f"artifact path traverses a symlink: {value}")
    resolved = candidate.resolve(strict=must_exist)
    try:
        resolved.relative_to(resolved_root)
    except ValueError as error:
        raise ValueError(f"artifact path escapes its root: {value}") from error
    if require_file and not resolved.is_file():
        raise ValueError(f"artifact path is not a file: {value}")
    return resolved


__all__ = ["safe_relative_path"]
