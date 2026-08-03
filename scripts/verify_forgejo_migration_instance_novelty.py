from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any

from aftermath_bench.integrations.forgejo_migration_instance import (
    ForgejoMigrationInstanceSpec,
)


IDENTITY_FIELDS = (
    "scenario_id",
    "owner",
    "repository",
    "migration_id",
    "schema_hash",
    "artifact_digest",
    "workflow_path",
    "migration_path",
    "artifact_manifest_path",
    "milestone_title",
    "change_issue_title",
    "protected_issue_title",
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


def validate_bound_blueprint(
    instance: ForgejoMigrationInstanceSpec,
    path: Path,
) -> Path:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(
            "bound migration blueprint must be readable JSON"
        ) from error
    if (
        not isinstance(payload, dict)
        or payload.get("scenario_id") != instance.scenario_id
        or payload.get("instance_spec_sha256") != instance.sha256
        or payload.get("family") != "forgejo-migration-deployment"
    ):
        raise ValueError(
            "bound migration blueprint does not match the instance"
        )
    return path.resolve()


def novelty_scan_paths(
    paths: list[Path],
    *,
    instance_spec_path: Path,
    instance: ForgejoMigrationInstanceSpec,
    bound_blueprint_path: Path,
) -> list[Path]:
    excluded = {
        instance_spec_path.resolve(),
        validate_bound_blueprint(instance, bound_blueprint_path),
    }
    return [path for path in paths if path.resolve() not in excluded]


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
    overlaps: list[dict[str, str]] = []
    for field in IDENTITY_FIELDS:
        value = str(instance.get(field, ""))
        if not value:
            raise ValueError(f"migration instance is missing {field}")
        for path, text in corpus:
            if value in text:
                overlaps.append({"field": field, "path": path.as_posix()})
    return overlaps


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Reject a Forgejo migration instance whose identity-bearing "
            "facts already occur in tracked benchmark material."
        )
    )
    parser.add_argument("--instance-spec", type=Path, required=True)
    parser.add_argument("--bound-blueprint", type=Path, required=True)
    parser.add_argument("--repository-root", type=Path, default=Path("."))
    args = parser.parse_args()
    root = args.repository_root.resolve()
    try:
        instance = ForgejoMigrationInstanceSpec.from_path(args.instance_spec)
        all_paths = tracked_paths(root)
        scan_paths = novelty_scan_paths(
            all_paths,
            instance_spec_path=args.instance_spec,
            instance=instance,
            bound_blueprint_path=args.bound_blueprint,
        )
        overlaps = find_overlaps(instance.as_dict(), scan_paths)
    except (OSError, TypeError, ValueError, subprocess.SubprocessError) as error:
        print(json.dumps({"passed": False, "error": str(error)}))
        return 2
    report = {
        "passed": not overlaps,
        "checked_field_count": len(IDENTITY_FIELDS),
        "tracked_file_count": len(all_paths),
        "scanned_file_count": len(scan_paths),
        "excluded_tracked_file_count": len(all_paths) - len(scan_paths),
        "overlaps": overlaps,
    }
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
