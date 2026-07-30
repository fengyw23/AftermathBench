from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def validate_control_summary(
    summary: dict[str, Any],
    *,
    expected_cases: int,
    minimum_pass_rate: float,
) -> list[str]:
    failures = []
    if int(summary.get("completed_runs", -1)) != expected_cases:
        failures.append("completed_runs")
    if summary.get("run_errors"):
        failures.append("run_errors")
    if float(summary.get("task_pass_rate", 0.0)) < minimum_pass_rate:
        failures.append("task_pass_rate")
    control_counts = summary.get("execution_control_counts", {})
    if int(control_counts.get("true", 0)) != expected_cases:
        failures.append("execution_control_counts")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Enforce the preregistered native execution-control gate."
    )
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--expected-cases", type=int, required=True)
    parser.add_argument("--minimum-pass-rate", type=float, default=0.8)
    args = parser.parse_args()
    summary = json.loads(args.summary.read_text(encoding="utf-8"))
    failures = validate_control_summary(
        summary,
        expected_cases=args.expected_cases,
        minimum_pass_rate=args.minimum_pass_rate,
    )
    print(
        json.dumps(
            {
                "passed": not failures,
                "expected_cases": args.expected_cases,
                "minimum_pass_rate": args.minimum_pass_rate,
                "failures": failures,
            }
        )
    )
    return 0 if not failures else 2


if __name__ == "__main__":
    raise SystemExit(main())
