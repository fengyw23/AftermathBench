from __future__ import annotations

import argparse
import json
import string
from pathlib import Path
from typing import Any


def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in string.hexdigits for character in value)
    )


def validate_control_trajectory(
    payload: Any,
    *,
    variant: str,
) -> tuple[str, ...]:
    failures: list[str] = []
    if not isinstance(payload, dict):
        return ("trajectory_not_object",)
    if payload.get("variant") != variant:
        failures.append("variant_mismatch")
    if payload.get("execution_control") is not True:
        failures.append("not_execution_control")
    if not isinstance(payload.get("run_id"), str) or not payload["run_id"]:
        failures.append("missing_run_id")
    if not isinstance(payload.get("scenario_id"), str) or not payload[
        "scenario_id"
    ]:
        failures.append("missing_scenario_id")
    if not _is_sha256(payload.get("instance_spec_sha256")):
        failures.append("invalid_instance_spec_sha256")
    if not isinstance(payload.get("surface_failure"), dict):
        failures.append("missing_surface_failure")
    if not isinstance(payload.get("turns"), list) or not payload["turns"]:
        failures.append("missing_turns")
    if not isinstance(payload.get("final_evidence"), dict):
        failures.append("missing_final_evidence")
    evaluation = payload.get("evaluation")
    if not isinstance(evaluation, dict) or not isinstance(
        evaluation.get("passed"),
        bool,
    ):
        failures.append("invalid_evaluation")

    lock = payload.get("formal_input_lock")
    if not isinstance(lock, dict):
        failures.append("missing_formal_input_lock")
    else:
        if lock.get("variant_id") != variant:
            failures.append("formal_input_lock_variant_mismatch")
        for field in (
            "lock_sha256",
            "boundary_state_sha256",
            "failure_report_sha256",
            "prefix_sha256",
        ):
            if not _is_sha256(lock.get(field)):
                failures.append(f"invalid_formal_input_lock_{field}")

    boundary = payload.get("pre_model_boundary_evidence")
    if not isinstance(boundary, dict):
        failures.append("missing_pre_model_boundary_evidence")
    else:
        if boundary.get("variant_id") != variant:
            failures.append("pre_model_boundary_variant_mismatch")
        if not _is_sha256(boundary.get("sha256")):
            failures.append("invalid_pre_model_boundary_sha256")
        if (
            isinstance(lock, dict)
            and boundary.get("sha256") != lock.get("boundary_state_sha256")
        ):
            failures.append("pre_model_boundary_lock_mismatch")
    return tuple(failures)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Check that a native execution-control trajectory is structurally "
            "complete and remains bound to its formal input boundary."
        )
    )
    parser.add_argument("--trajectory", type=Path, required=True)
    parser.add_argument("--variant", required=True)
    args = parser.parse_args()
    try:
        payload = json.loads(args.trajectory.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        print(
            json.dumps(
                {
                    "passed": False,
                    "variant": args.variant,
                    "failures": ["trajectory_unreadable"],
                    "error_type": type(error).__name__,
                }
            )
        )
        return 2
    failures = validate_control_trajectory(payload, variant=args.variant)
    print(
        json.dumps(
            {
                "passed": not failures,
                "variant": args.variant,
                "failures": list(failures),
            },
            indent=2,
        )
    )
    return 0 if not failures else 2


if __name__ == "__main__":
    raise SystemExit(main())
