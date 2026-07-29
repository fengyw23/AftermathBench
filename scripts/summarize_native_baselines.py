from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def summarize_baselines(
    *,
    run_directory: Path,
    scenario: dict[str, Any],
) -> dict[str, Any]:
    expected = {
        str(item["id"]) for item in scenario.get("matched_variants", [])
    }
    grouped: dict[str, list[tuple[Path, dict[str, Any]]]] = defaultdict(list)
    parse_errors: list[dict[str, str]] = []
    for path in sorted(run_directory.glob("*.json")):
        if path.name.endswith("-boundary.json"):
            continue
        try:
            report = _read(path)
        except (OSError, json.JSONDecodeError) as error:
            parse_errors.append({"path": str(path), "error": str(error)})
            continue
        if report.get("baseline"):
            grouped[str(report["baseline"])].append((path, report))

    heuristics = []
    coverage_errors = []
    for name, items in sorted(grouped.items()):
        variants = {str(report.get("variant")) for _, report in items}
        missing = sorted(expected - variants)
        extra = sorted(variants - expected)
        duplicates = len(items) != len(variants)
        if missing or extra or duplicates:
            coverage_errors.append(
                {
                    "baseline": name,
                    "missing": missing,
                    "extra": extra,
                    "duplicate_variant": duplicates,
                }
            )
        rows = []
        for path, report in sorted(
            items, key=lambda item: str(item[1].get("variant"))
        ):
            passed = bool(report.get("evaluation", {}).get("passed"))
            rows.append(
                {
                    "variant": str(report.get("variant")),
                    "passed": passed,
                    "path": str(path),
                }
            )
        passed_count = sum(row["passed"] for row in rows)
        complete = variants == expected and len(items) == len(expected)
        heuristics.append(
            {
                "name": name,
                "pass_rate": passed_count / len(expected) if expected else 0.0,
                "matched_group_success": (
                    complete and all(row["passed"] for row in rows)
                ),
                "reports": rows,
            }
        )
    maximum_pass_rate = max(
        (item["pass_rate"] for item in heuristics), default=1.0
    )
    matched_solvers = [
        item["name"] for item in heuristics if item["matched_group_success"]
    ]
    return {
        "schema_version": "0.1",
        "scenario_id": scenario["scenario_id"],
        "source": "executed native terminal-state evaluations",
        "expected_variants": sorted(expected),
        "heuristics": heuristics,
        "maximum_heuristic_pass_rate": maximum_pass_rate,
        "matched_group_solvers": matched_solvers,
        "hard_fixed_policy_gate_passed": (
            not parse_errors
            and not coverage_errors
            and bool(heuristics)
            and maximum_pass_rate < 0.5
            and not matched_solvers
        ),
        "coverage_errors": coverage_errors,
        "parse_errors": parse_errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Summarize replayed fixed policies for a native family."
    )
    parser.add_argument("--run-directory", type=Path, required=True)
    parser.add_argument("--scenario", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    summary = summarize_baselines(
        run_directory=args.run_directory,
        scenario=_read(args.scenario),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if not summary["coverage_errors"] and not summary["parse_errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
