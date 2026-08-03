from __future__ import annotations

import argparse
import hashlib
import json
import string
from pathlib import Path
from typing import Any

from aftermath_bench.native_boundary_equivalence import (
    native_boundaries_equivalent,
)


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
    locked_boundary: dict[str, Any] | None = None,
    pre_model_boundary: dict[str, Any] | None = None,
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
            family = payload.get("family")
            semantically_equivalent = (
                isinstance(family, str)
                and isinstance(locked_boundary, dict)
                and isinstance(pre_model_boundary, dict)
                and native_boundaries_equivalent(
                    family,
                    locked_boundary,
                    pre_model_boundary,
                )
            )
            if not semantically_equivalent:
                failures.append("pre_model_boundary_lock_mismatch")
    return tuple(failures)


def _load_bound_capture(
    path: Path,
    *,
    expected_sha256: Any,
    label: str,
) -> tuple[dict[str, Any] | None, tuple[str, ...]]:
    try:
        raw = path.read_bytes()
        payload = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None, (f"{label}_file_unreadable",)
    failures: list[str] = []
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        failures.append(f"{label}_file_sha256_mismatch")
    if not isinstance(payload, dict):
        failures.append(f"{label}_file_not_object")
        return None, tuple(failures)
    return payload, tuple(failures)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Check that a native execution-control trajectory is structurally "
            "complete and remains bound to its formal input boundary."
        )
    )
    parser.add_argument("--trajectory", type=Path, required=True)
    parser.add_argument("--variant", required=True)
    parser.add_argument("--locked-boundary", type=Path)
    parser.add_argument("--pre-model-boundary", type=Path)
    args = parser.parse_args()
    if (args.locked_boundary is None) != (args.pre_model_boundary is None):
        parser.error(
            "--locked-boundary and --pre-model-boundary must be supplied together"
        )
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
    capture_failures: list[str] = []
    locked_boundary = None
    pre_model_boundary = None
    if args.locked_boundary is not None:
        lock = payload.get("formal_input_lock")
        boundary_record = payload.get("pre_model_boundary_evidence")
        locked_boundary, locked_failures = _load_bound_capture(
            args.locked_boundary,
            expected_sha256=(
                lock.get("boundary_state_sha256")
                if isinstance(lock, dict)
                else None
            ),
            label="locked_boundary",
        )
        pre_model_boundary, pre_model_failures = _load_bound_capture(
            args.pre_model_boundary,
            expected_sha256=(
                boundary_record.get("sha256")
                if isinstance(boundary_record, dict)
                else None
            ),
            label="pre_model_boundary",
        )
        capture_failures.extend(locked_failures)
        capture_failures.extend(pre_model_failures)
    failures = (
        *validate_control_trajectory(
            payload,
            variant=args.variant,
            locked_boundary=locked_boundary,
            pre_model_boundary=pre_model_boundary,
        ),
        *capture_failures,
    )
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
