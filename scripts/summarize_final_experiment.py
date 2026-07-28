from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def compare(
    easy: dict[str, Any],
    holdout: dict[str, Any],
) -> dict[str, Any]:
    easy_pass = float(easy["task_pass_rate"])
    holdout_pass = float(holdout["task_pass_rate"])
    drop = easy_pass - holdout_pass
    holdout_matched = float(holdout["matched_group_success_rate"])
    checks = {
        "easy_has_20_completed_runs": easy["completed_runs"] == 20,
        "holdout_has_20_completed_runs": (
            holdout["completed_runs"] == 20
        ),
        "provider_and_runtime_errors_are_zero": (
            not easy.get("run_errors")
            and not holdout.get("run_errors")
        ),
        "holdout_pass_at_most_50_percent": holdout_pass <= 0.5,
        "drop_at_least_40_percentage_points": drop >= 0.4,
        "holdout_matched_group_at_most_20_percent": (
            holdout_matched <= 0.2
        ),
    }
    return {
        "schema_version": "0.1",
        "easy": {
            "completed_runs": easy["completed_runs"],
            "task_pass_rate": easy_pass,
            "matched_group_success_rate": easy[
                "matched_group_success_rate"
            ],
            "run_errors": easy.get("run_errors", []),
        },
        "frozen_holdout": {
            "completed_runs": holdout["completed_runs"],
            "task_pass_rate": holdout_pass,
            "matched_group_success_rate": holdout_matched,
            "component_pass_rates": holdout.get(
                "component_pass_rates",
                {},
            ),
            "failure_type_counts": holdout.get(
                "failure_type_counts",
                {},
            ),
            "run_errors": holdout.get("run_errors", []),
        },
        "absolute_pass_rate_drop": drop,
        "checks": checks,
        "primary_experiment_acceptance": all(checks.values()),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--easy-summary", type=Path, required=True)
    parser.add_argument("--holdout-summary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = compare(
        _read(args.easy_summary),
        _read(args.holdout_summary),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["primary_experiment_acceptance"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
