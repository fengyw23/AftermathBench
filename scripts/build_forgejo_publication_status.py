from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_summary(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def build_publication_status(
    *,
    summary_path: Path,
    formal_declarations_path: Path,
    provider_scan_sentinel_path: Path,
    scenario_path: Path,
    output_path: Path,
    expected_cases: int,
    minimum_pass_rate: float,
) -> dict[str, Any]:
    if expected_cases < 1:
        raise ValueError("expected_cases must be positive")
    if not 0.0 <= minimum_pass_rate <= 1.0:
        raise ValueError("minimum_pass_rate must be between zero and one")
    if not provider_scan_sentinel_path.is_file():
        raise ValueError("provider secret-scan sentinel is missing")
    if not scenario_path.is_file():
        raise ValueError("scenario evidence is missing")

    summary = _load_summary(summary_path)
    reports = summary.get("reports") if summary is not None else None
    valid_reports = (
        reports
        if isinstance(reports, list)
        and all(isinstance(item, dict) for item in reports)
        else []
    )
    variants = [
        item.get("variant")
        for item in valid_reports
        if isinstance(item.get("variant"), str)
    ]
    completed_runs = len(valid_reports)
    passed_runs = sum(
        item.get("passed") is True for item in valid_reports
    )
    task_pass_rate = (
        passed_runs / expected_cases if expected_cases else 0.0
    )
    declared_rate = summary.get("task_pass_rate") if summary else None
    declared_completed = (
        summary.get("completed_runs") if summary else None
    )
    run_errors = summary.get("run_errors") if summary else None
    summary_valid = (
        summary is not None
        and completed_runs == expected_cases
        and len(variants) == expected_cases
        and len(set(variants)) == expected_cases
        and declared_completed == expected_cases
        and run_errors == []
        and isinstance(declared_rate, (int, float))
        and abs(float(declared_rate) - task_pass_rate) <= 1e-12
    )
    control_gate_pass = (
        summary_valid and task_pass_rate >= minimum_pass_rate
    )
    formal_complete = (
        formal_declarations_path.is_file()
        and formal_declarations_path.stat().st_size > 0
    )
    status = {
        "schema_version": "1.0",
        "artifact_type": (
            "forgejo_public_development_publication_status"
        ),
        "formal_complete": formal_complete,
        "control_gate_pass": control_gate_pass,
        "release_promotion_eligible": (
            formal_complete and control_gate_pass
        ),
        "control": {
            "summary_present": summary is not None,
            "summary_valid": summary_valid,
            "summary_sha256": (
                _sha256_file(summary_path)
                if summary_path.is_file()
                else None
            ),
            "expected_cases": expected_cases,
            "completed_runs": completed_runs,
            "passed_runs": passed_runs,
            "task_pass_rate": task_pass_rate,
            "minimum_pass_rate": minimum_pass_rate,
        },
        "formal": {
            "declarations_present": formal_complete,
            "declarations_sha256": (
                _sha256_file(formal_declarations_path)
                if formal_complete
                else None
            ),
        },
        "safety": {
            "provider_secret_scan_passed": True,
            "scenario_present": True,
            "scenario_sha256": _sha256_file(scenario_path),
        },
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(
            status,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return status


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Record whether a public Forgejo evidence run is diagnostic "
            "only or eligible for formal release promotion."
        )
    )
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument(
        "--formal-declarations",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--provider-scan-sentinel",
        type=Path,
        required=True,
    )
    parser.add_argument("--scenario", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-cases", type=int, required=True)
    parser.add_argument(
        "--minimum-pass-rate",
        type=float,
        required=True,
    )
    args = parser.parse_args()
    try:
        status = build_publication_status(
            summary_path=args.summary,
            formal_declarations_path=args.formal_declarations,
            provider_scan_sentinel_path=args.provider_scan_sentinel,
            scenario_path=args.scenario,
            output_path=args.output,
            expected_cases=args.expected_cases,
            minimum_pass_rate=args.minimum_pass_rate,
        )
    except (OSError, ValueError) as error:
        print(json.dumps({"passed": False, "error": str(error)}))
        return 2
    print(json.dumps(status, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
