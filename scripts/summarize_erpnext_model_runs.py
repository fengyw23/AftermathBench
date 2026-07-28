from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


VARIANTS = (
    "request_not_reached",
    "database_committed_response_lost",
    "after_commit_enqueue_failed",
    "async_job_pending",
)


def summarize(root: Path) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    repetition_directories = sorted(root.glob("repetition-*"))
    for run_directory in repetition_directories:
        repetition = int(run_directory.name.split("-", 1)[1])
        for variant in VARIANTS:
            path = run_directory / f"{variant}.json"
            if not path.is_file() or path.stat().st_size == 0:
                records.append(
                    {
                        "trajectory": str(path),
                        "status": "run_error",
                        "variant": variant,
                        "repetition": repetition,
                        "error": "missing trajectory after provider retry",
                    }
                )
                continue
            try:
                report = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as error:
                records.append(
                    {
                        "trajectory": str(path),
                        "status": "run_error",
                        "variant": variant,
                        "repetition": repetition,
                        "error": str(error),
                    }
                )
                continue
            if "evaluation" not in report:
                records.append(
                    {
                        "trajectory": str(path),
                        "status": "run_error",
                        "variant": variant,
                        "repetition": repetition,
                        "error": report.get(
                            "error",
                            "missing evaluation",
                        ),
                    }
                )
                continue
            diagnostics = report.get("trajectory_diagnostics", {})
            records.append(
                {
                    "trajectory": str(path),
                    "status": "completed",
                    "variant": report["variant"],
                    "repetition": repetition,
                    "passed": bool(report["evaluation"]["passed"]),
                    "checks": report["evaluation"]["checks"],
                    "turns": len(report.get("turns", ())),
                    "stop_reason": report.get("stop_reason"),
                    "selected_mutations": diagnostics.get(
                        "selected_mutations",
                        (),
                    ),
                    "inspected_payment_state": diagnostics.get(
                        "inspected_payment_state",
                        False,
                    ),
                    "inspected_remittance_state": diagnostics.get(
                        "inspected_remittance_state",
                        False,
                    ),
                    "unsafe_submit_retry": diagnostics.get(
                        "unsafe_submit_retry",
                        False,
                    ),
                    "unnecessary_remittance_requeue": diagnostics.get(
                        "unnecessary_remittance_requeue",
                        False,
                    ),
                    "tool_error_count": diagnostics.get(
                        "tool_error_count",
                        0,
                    ),
                }
            )

    completed = [record for record in records if record["status"] == "completed"]
    repetitions = sorted(
        {record["repetition"] for record in completed}
    )
    matched_successes = 0
    for repetition in repetitions:
        group = [
            record
            for record in completed
            if record["repetition"] == repetition
        ]
        if (
            {record["variant"] for record in group} == set(VARIANTS)
            and all(record["passed"] for record in group)
        ):
            matched_successes += 1
    check_names = sorted(
        {
            name
            for record in completed
            for name in record["checks"]
        }
    )
    return {
        "schema_version": "0.4",
        "expected_variants": list(VARIANTS),
        "completed_runs": len(completed),
        "run_errors": len(records) - len(completed),
        "task_pass_rate": (
            sum(record["passed"] for record in completed) / len(completed)
            if completed
            else None
        ),
        "matched_group_success_rate": (
            matched_successes / len(repetitions)
            if repetitions
            else None
        ),
        "check_pass_rates": {
            name: (
                sum(bool(record["checks"].get(name)) for record in completed)
                / len(completed)
                if completed
                else None
            )
            for name in check_names
        },
        "behavior_rates": {
            name: (
                sum(bool(record[name]) for record in completed) / len(completed)
                if completed
                else None
            )
            for name in (
                "inspected_payment_state",
                "inspected_remittance_state",
                "unsafe_submit_retry",
                "unnecessary_remittance_requeue",
            )
        },
        "runs": records,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-directory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = summarize(args.run_directory)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["run_errors"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
