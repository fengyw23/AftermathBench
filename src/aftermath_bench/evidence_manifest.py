from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any


def build_file_manifest(
    root: str | Path,
    *,
    exclude: set[str] | None = None,
) -> dict[str, Any]:
    directory = Path(root)
    excluded = set(exclude or ())
    files = []
    candidates = sorted(
        directory.rglob("*"),
        key=lambda path: path.relative_to(directory).as_posix(),
    )
    for path in candidates:
        if not path.is_file():
            continue
        relative = path.relative_to(directory).as_posix()
        if relative in excluded:
            continue
        files.append(
            {
                "path": relative,
                "bytes": path.stat().st_size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    return {
        "schema_version": "0.1",
        "excluded_files": sorted(excluded),
        "file_count": len(files),
        "total_bytes": sum(item["bytes"] for item in files),
        "files": files,
    }
