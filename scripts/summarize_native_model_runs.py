from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


DEFAULT_VARIANTS = {
    "request_not_reached",
    "database_committed_response_lost",
    "after_commit_enqueue_failed",
    "async_job_pending",
}


def _load_reports(
    root: Path,
    *,
    expected_variants: set[str],
) -> tuple[list[dict[str, Any]], list[str]]:
    reports = []
    errors = []
    repetition_directories = sorted(
        path
        for path in root.rglob("repetition-*")
        if path.is_dir()
    )
    for run_directory in repetition_directories:
        for variant in sorted(expected_variants):
            path = run_directory / f"{variant}.json"
            if not path.is_file() or path.stat().st_size == 0:
                errors.append(
                    f"{path}: missing trajectory after provider retry"
                )
    for path in sorted(root.rglob("*.json")):
        if path.name.endswith("-failure.json") or path.name in {
            "summary.json",
            "manifest.json",
            "prefix.json",
        }:
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            errors.append(f"{path}: {error}")
            continue
        if "evaluation" not in payload or "variant" not in payload:
            continue
        payload["_path"] = str(path)
        reports.append(payload)
    return reports, errors


def summarize(
    root: Path,
    *,
    expected_execution_control: bool | None = None,
    expected_variants: set[str] | None = None,
) -> dict[str, Any]:
    expected_variants = expected_variants or DEFAULT_VARIANTS
    reports, errors = _load_reports(
        root,
        expected_variants=expected_variants,
    )
    by_group: dict[tuple[str, str], dict[str, bool]] = defaultdict(dict)
    component_totals: Counter[str] = Counter()
    failure_types: Counter[str] = Counter()
    execution_control_counts: Counter[str] = Counter()
    passed = 0
    for report in reports:
        observed_control = bool(report.get("execution_control", False))
        execution_control_counts[str(observed_control).lower()] += 1
        if (
            expected_execution_control is not None
            and observed_control is not expected_execution_control
        ):
            errors.append(
                f"{report['_path']}: execution_control="
                f"{str(observed_control).lower()} does not match expected "
                f"{str(expected_execution_control).lower()}"
            )
        evaluation = report["evaluation"]
        success = bool(evaluation.get("passed", False))
        passed += int(success)
        for component, value in evaluation.get("components", {}).items():
            component_totals[component] += int(bool(value))
        error_type = report.get("trajectory_diagnostics", {}).get(
            "primary_error"
        )
        if error_type:
            failure_types[str(error_type)] += 1
        path = Path(report["_path"])
        repetition = next(
            (
                part
                for part in path.parts
                if part.startswith("repetition-")
            ),
            "repetition-unknown",
        )
        by_group[(str(report["scenario_id"]), repetition)][
            str(report["variant"])
        ] = success
    matched_groups = [
        variants
        for variants in by_group.values()
        if set(variants) == expected_variants
    ]
    matched_successes = sum(
        int(all(group.values())) for group in matched_groups
    )
    total = len(reports)
    return {
        "schema_version": "0.5",
        "completed_runs": total,
        "run_errors": errors,
        "task_pass_rate": passed / total if total else 0,
        "matched_group_count": len(matched_groups),
        "matched_group_success_rate": (
            matched_successes / len(matched_groups)
            if matched_groups
            else 0
        ),
        "component_pass_rates": {
            component: count / total if total else 0
            for component, count in sorted(component_totals.items())
        },
        "failure_type_counts": dict(sorted(failure_types.items())),
        "execution_control_counts": dict(
            sorted(execution_control_counts.items())
        ),
        "reports": [
            {
                "scenario_id": report["scenario_id"],
                "variant": report["variant"],
                "passed": report["evaluation"]["passed"],
                "primary_error": report.get(
                    "trajectory_diagnostics",
                    {},
                ).get("primary_error"),
                "path": report["_path"],
            }
            for report in reports
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-directory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--expected-execution-control",
        choices=("true", "false"),
    )
    parser.add_argument(
        "--scenario",
        type=Path,
        help="derive the expected matched variants from a scenario manifest",
    )
    args = parser.parse_args()
    expected_execution_control = (
        args.expected_execution_control == "true"
        if args.expected_execution_control is not None
        else None
    )
    expected_variants = None
    if args.scenario is not None:
        scenario = json.loads(args.scenario.read_text(encoding="utf-8"))
        expected_variants = {
            str(item["id"]) for item in scenario["matched_variants"]
        }
    summary = summarize(
        args.run_directory,
        expected_execution_control=expected_execution_control,
        expected_variants=expected_variants,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if not summary["run_errors"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
