from __future__ import annotations

import argparse
import json
from pathlib import Path

from aftermath_bench.native_admission import (
    native_admission_report_payload,
    validate_native_scenario,
)
from aftermath_bench.native_scenario import load_native_scenario


def refresh_native_admission_report(
    scenario_path: Path,
    *,
    allow_failed: bool = False,
) -> dict[str, object]:
    scenario = load_native_scenario(scenario_path)
    report = validate_native_scenario(scenario)
    if not report.passed and not allow_failed:
        raise RuntimeError(
            "refusing to persist a failed admission report: "
            + ", ".join(report.failures)
        )
    payload = native_admission_report_payload(report)
    output = scenario.resolve_artifact("admission")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Recompute and persist a native scenario's derived admission "
            "report without treating the report as its own input."
        )
    )
    parser.add_argument("--scenario", type=Path, required=True)
    parser.add_argument("--allow-failed", action="store_true")
    args = parser.parse_args()
    payload = refresh_native_admission_report(
        args.scenario.resolve(),
        allow_failed=args.allow_failed,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
