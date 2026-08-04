from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from aftermath_bench.integrations.erpnext_inventory_cost_baselines import (
    INVENTORY_COST_BASELINE_NAMES,
)
from aftermath_bench.native_scenario import load_native_scenario


def summarize(directory: Path, scenario_path: Path) -> dict[str, Any]:
    scenario = load_native_scenario(scenario_path)
    matrix: dict[str, dict[str, bool]] = {}
    missing: list[str] = []
    for baseline in INVENTORY_COST_BASELINE_NAMES:
        matrix[baseline] = {}
        for variant in scenario.variants:
            path = directory / f"{baseline}-{variant}.json"
            if not path.is_file():
                missing.append(path.name)
                continue
            report = json.loads(path.read_text(encoding="utf-8"))
            matrix[baseline][variant] = bool(
                report.get("evaluation", {}).get("passed", False)
            )
    counts = {name: sum(row.values()) for name, row in matrix.items()}
    universal = [
        name for name, count in counts.items() if count == len(scenario.variants)
    ]
    maximum = max(counts.values(), default=0) / len(scenario.variants)
    return {
        "schema_version": "0.1",
        "artifact_type": "erpnext_inventory_cost_fixed_baseline_summary",
        "scenario_id": scenario.scenario_id,
        "variant_count": len(scenario.variants),
        "baseline_count": len(INVENTORY_COST_BASELINE_NAMES),
        "matrix": matrix,
        "pass_counts": counts,
        "maximum_pass_rate": maximum,
        "maximum_pass_rate_below_half": maximum < 0.5,
        "universal_baselines": universal,
        "missing_reports": missing,
        "passed": not missing and not universal and maximum < 0.5,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Summarize fixed inventory-cost recovery baselines."
    )
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--scenario", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = summarize(args.directory, args.scenario)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
