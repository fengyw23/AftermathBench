from __future__ import annotations

import argparse
import io
import json
import re
import subprocess
import tarfile
from pathlib import Path
from typing import Any

from aftermath_bench.integrations.forgejo_publication_instance import (
    ForgejoPublicationInstanceSpec,
)

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
        root / item.decode("utf-8") for item in completed.stdout.split(b"\0") if item
    ]


def validate_bound_blueprint(
    instance: ForgejoPublicationInstanceSpec,
    path: Path,
) -> Path:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("bound blueprint must be a readable JSON object") from exc
    if not isinstance(payload, dict):
        raise TypeError("bound blueprint must be a JSON object")
    if (
        not isinstance(payload.get("scenario_id"), str)
        or payload["scenario_id"] != instance.scenario_id
    ):
        raise ValueError("bound blueprint scenario_id does not match instance spec")
    if (
        not isinstance(payload.get("instance_spec_sha256"), str)
        or payload["instance_spec_sha256"] != instance.sha256
    ):
        raise ValueError(
            "bound blueprint instance_spec_sha256 does not match instance spec"
        )
    return path.resolve()


def novelty_scan_paths(
    paths: list[Path],
    *,
    instance_spec_path: Path,
    instance: ForgejoPublicationInstanceSpec,
    bound_blueprint_path: Path | None = None,
) -> list[Path]:
    excluded = {instance_spec_path.resolve()}
    if bound_blueprint_path is not None:
        excluded.add(validate_bound_blueprint(instance, bound_blueprint_path))
    return [path for path in paths if path.resolve() not in excluded]


def find_overlaps(
    instance: dict[str, Any],
    paths: list[Path],
) -> list[dict[str, str]]:
    corpus: list[tuple[Path, str]] = []
    for path in paths:
        try:
            corpus.append((path, path.read_text(encoding="utf-8", errors="ignore")))
        except OSError:
            continue
    return _find_overlaps_in_corpus(instance, corpus)


def _find_overlaps_in_corpus(
    instance: dict[str, Any],
    corpus: list[tuple[Path, str]],
) -> list[dict[str, str]]:
    overlaps = []
    for field in IDENTITY_FIELDS:
        value = str(instance.get(field, ""))
        if not value:
            raise ValueError(f"private instance is missing {field}")
        for path, text in corpus:
            if value in text:
                overlaps.append({"field": field, "path": path.as_posix()})
    return overlaps


def find_overlaps_in_commit(
    instance: dict[str, Any],
    *,
    root: Path,
    commit: str,
    excluded_paths: set[str],
) -> list[dict[str, str]]:
    """Replay the novelty scan against the exact pre-admission Git tree."""

    if re.fullmatch(r"[0-9a-f]{40}", commit) is None:
        raise ValueError("historical novelty commit must be a full SHA-1")
    completed = subprocess.run(
        ["git", "archive", "--format=tar", commit],
        cwd=root,
        check=True,
        capture_output=True,
    )
    corpus: list[tuple[Path, str]] = []
    with tarfile.open(fileobj=io.BytesIO(completed.stdout), mode="r:") as archive:
        for member in archive.getmembers():
            if not member.isfile() or member.name in excluded_paths:
                continue
            stream = archive.extractfile(member)
            if stream is None:
                continue
            corpus.append(
                (
                    root / member.name,
                    stream.read().decode("utf-8", errors="ignore"),
                )
            )
    return _find_overlaps_in_corpus(instance, corpus)


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
    parser.add_argument(
        "--bound-blueprint",
        type=Path,
        help=(
            "Exclude exactly one blueprint only after its scenario_id and "
            "instance_spec_sha256 are verified against --instance-spec."
        ),
    )
    args = parser.parse_args()
    root = args.repository_root.resolve()
    try:
        instance = ForgejoPublicationInstanceSpec.from_path(args.instance_spec)
        all_tracked_paths = tracked_paths(root)
        scan_paths = novelty_scan_paths(
            all_tracked_paths,
            instance_spec_path=args.instance_spec,
            instance=instance,
            bound_blueprint_path=args.bound_blueprint,
        )
    except (OSError, TypeError, ValueError) as exc:
        print(
            json.dumps(
                {
                    "passed": False,
                    "error": str(exc),
                },
                ensure_ascii=False,
            )
        )
        return 2
    overlaps = find_overlaps(instance.as_dict(), scan_paths)
    report = {
        "passed": not overlaps,
        "checked_field_count": len(IDENTITY_FIELDS),
        "tracked_file_count": len(all_tracked_paths),
        "scanned_file_count": len(scan_paths),
        "excluded_tracked_file_count": (len(all_tracked_paths) - len(scan_paths)),
        "overlaps": overlaps,
    }
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
