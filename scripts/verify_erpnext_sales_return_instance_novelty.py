from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from aftermath_bench.integrations.erpnext_sales_return_instance import (
    ERPNextSalesReturnInstanceSpec,
)
from aftermath_bench.strict_json import load_json_strict


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


def identity_values(
    instance: ERPNextSalesReturnInstanceSpec,
) -> dict[str, str]:
    return {
        "scenario_id": instance.scenario_id,
        "customer": instance.customer,
        "affected_item_code": str(
            instance.affected_item["item_code"]
        ),
        "affected_item_name": str(
            instance.affected_item["item_name"]
        ),
        "unaffected_item_code": str(
            instance.unaffected_item["item_code"]
        ),
        "unaffected_item_name": str(
            instance.unaffected_item["item_name"]
        ),
        "replacement_item_code": str(
            instance.replacement_item["item_code"]
        ),
        "replacement_item_name": str(
            instance.replacement_item["item_name"]
        ),
    }


def validate_bound_blueprint(
    instance: ERPNextSalesReturnInstanceSpec,
    path: Path,
) -> Path:
    payload = load_json_strict(path)
    if (
        not isinstance(payload, dict)
        or payload.get("scenario_id") != instance.scenario_id
        or payload.get("instance_spec_sha256") != instance.sha256
    ):
        raise ValueError(
            "bound blueprint identity does not match instance spec"
        )
    return path.resolve()


def find_overlaps(
    values: dict[str, str],
    paths: list[Path],
) -> list[dict[str, str]]:
    overlaps: list[dict[str, str]] = []
    for path in paths:
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for field, value in values.items():
            if value in text:
                overlaps.append(
                    {
                        "field": field,
                        "path": path.as_posix(),
                    }
                )
    return overlaps


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Reject a fresh ERPNext instance whose business identities "
            "already occur in tracked benchmark material."
        )
    )
    parser.add_argument("--instance-spec", type=Path, required=True)
    parser.add_argument(
        "--repository-root",
        type=Path,
        default=Path("."),
    )
    parser.add_argument("--bound-blueprint", type=Path)
    args = parser.parse_args()
    root = args.repository_root.resolve()
    try:
        instance = ERPNextSalesReturnInstanceSpec.from_path(
            args.instance_spec
        )
        excluded = {args.instance_spec.resolve()}
        if args.bound_blueprint is not None:
            excluded.add(
                validate_bound_blueprint(
                    instance,
                    args.bound_blueprint,
                )
            )
        tracked = tracked_paths(root)
        scan_paths = [
            path for path in tracked if path.resolve() not in excluded
        ]
        overlaps = find_overlaps(
            identity_values(instance),
            scan_paths,
        )
    except (OSError, TypeError, ValueError) as error:
        print(json.dumps({"passed": False, "error": str(error)}))
        return 2
    report = {
        "passed": not overlaps,
        "checked_field_count": len(identity_values(instance)),
        "tracked_file_count": len(tracked),
        "scanned_file_count": len(scan_paths),
        "excluded_tracked_file_count": len(tracked) - len(scan_paths),
        "overlaps": overlaps,
    }
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
