from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any


IDENTITY_FIELDS = (
    "scenario_id",
    "owner",
    "repository",
    "package_name",
    "package_slug",
    "build_id",
    "base_branch",
    "feature_branch",
    "protected_branch",
    "release_tag",
    "protected_release_tag",
    "manifest_path",
    "protected_file_path",
    "release_title",
    "release_body",
    "milestone_title",
    "target_issue_title",
    "protected_pull_title",
    "protected_issue_title",
    "protected_release_title",
    "coordinator_consumer",
    "provenance_consumer",
)


def tracked_paths(root: Path) -> list[Path]:
    completed = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    return [
        root / item.decode("utf-8")
        for item in completed.stdout.split(b"\0")
        if item
    ]


def find_overlaps(
    instance: dict[str, Any],
    paths: list[Path],
) -> list[dict[str, str]]:
    corpus: list[tuple[Path, str]] = []
    for path in paths:
        try:
            corpus.append(
                (path, path.read_text(encoding="utf-8", errors="ignore"))
            )
        except OSError:
            continue
    overlaps = []
    for field in IDENTITY_FIELDS:
        value = str(instance.get(field, ""))
        if not value:
            raise ValueError(f"private instance is missing {field}")
        for path, text in corpus:
            if value in text:
                overlaps.append({"field": field, "path": path.as_posix()})
    return overlaps


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Reject a private Forgejo instance whose identity-bearing "
            "surface facts already occur in tracked benchmark material."
        )
    )
    parser.add_argument("--instance-spec", type=Path, required=True)
    parser.add_argument(
        "--repository-root",
        type=Path,
        default=Path("."),
    )
    args = parser.parse_args()
    root = args.repository_root.resolve()
    instance = json.loads(
        args.instance_spec.read_text(encoding="utf-8")
    )
    overlaps = find_overlaps(instance, tracked_paths(root))
    report = {
        "passed": not overlaps,
        "checked_field_count": len(IDENTITY_FIELDS),
        "tracked_file_count": len(tracked_paths(root)),
        "overlaps": overlaps,
    }
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
