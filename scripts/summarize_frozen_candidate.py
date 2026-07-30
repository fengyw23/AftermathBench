from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def execution_control_status(
    *,
    control: dict[str, Any] | None,
    usage_events: list[str],
    expected_cases: int,
    minimum_pass_rate: float = 0.8,
) -> tuple[str, bool]:
    if control is None:
        if any(
            event in {"evaluation_locked", "consumed"}
            for event in usage_events
        ):
            return "attempted_incomplete", False
        if usage_events and usage_events[-1] == "frozen":
            return "frozen_not_consumed", False
        return "not_requested", False
    gate_pass = (
        int(control.get("completed_runs", -1)) == expected_cases
        and not control.get("run_errors")
        and float(control.get("task_pass_rate", 0.0))
        >= minimum_pass_rate
        and int(
            control.get("execution_control_counts", {}).get("true", 0)
        )
        == expected_cases
    )
    return (
        "completed_gate_pass" if gate_pass else "completed_gate_fail",
        gate_pass,
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create a non-sensitive summary of a frozen candidate."
    )
    parser.add_argument("--commitment", type=Path, required=True)
    parser.add_argument("--admission", type=Path, required=True)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--baselines", type=Path, required=True)
    parser.add_argument("--control-summary", type=Path)
    parser.add_argument("--usage-ledger", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    commitment = _read(args.commitment)
    admission = _read(args.admission)
    reference = _read(args.reference)
    baselines = _read(args.baselines)
    ledger = _read(args.usage_ledger)
    control = (
        _read(args.control_summary)
        if args.control_summary is not None
        and args.control_summary.exists()
        else None
    )
    locked_event = next(
        (
            item
            for item in reversed(ledger["events"])
            if item["event"] == "evaluation_locked"
        ),
        None,
    )
    control_model = (
        locked_event.get("details", {}).get("model")
        if locked_event is not None
        else None
    )
    event_names = [str(item["event"]) for item in ledger["events"]]
    expected_cases = len(reference["reports"])
    control_status, control_gate_pass = execution_control_status(
        control=control,
        usage_events=event_names,
        expected_cases=expected_cases,
    )
    payload = {
        **commitment,
        "admission": {
            "passed": bool(admission["passed"]),
            "admitted_tier": admission["admitted_tier"],
            "failure_count": len(admission.get("failures", ())),
        },
        "reference": {
            "case_count": len(reference["reports"]),
            "pass_count": sum(
                bool(report["passed"]) for report in reference["reports"]
            ),
        },
        "fixed_policies": {
            "maximum_pass_rate": baselines[
                "maximum_heuristic_pass_rate"
            ],
            "matched_group_solver_count": len(
                baselines["matched_group_solvers"]
            ),
        },
        "execution_control": (
            {
                "status": control_status,
                "gate_pass": control_gate_pass,
                "model": control_model,
                "completed_runs": control["completed_runs"],
                "run_error_count": len(control["run_errors"]),
                "task_pass_rate": control["task_pass_rate"],
                "matched_group_success_rate": control[
                    "matched_group_success_rate"
                ],
            }
            if control is not None
            else {
                "status": control_status,
                "gate_pass": False,
            }
        ),
        "usage_events": [
            {
                "event": item["event"],
                "recorded_at": item["recorded_at"],
            }
            for item in ledger["events"]
        ],
        "usage_state": event_names[-1] if event_names else "missing",
        "raw_hidden_bundle_published": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "scenario_id": payload["scenario_id"],
                "admitted_tier": payload["admission"]["admitted_tier"],
                "reference_passes": (
                    f"{payload['reference']['pass_count']}/"
                    f"{payload['reference']['case_count']}"
                ),
                "control_pass_rate": payload["execution_control"].get(
                    "task_pass_rate"
                ),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
