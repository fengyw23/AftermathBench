from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from aftermath_bench.integrations.forgejo_reconciliation_baselines import (
    FORGEJO_RECONCILIATION_BASELINES,
)
from aftermath_bench.integrations.forgejo_reconciliation_faults import (
    FORGEJO_RECONCILIATION_VARIANTS,
)


def _read(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError(f"expected object in {path}")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-directory", type=Path, required=True)
    parser.add_argument("--scenario-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    matrix: dict[str, dict[str, bool]] = {}
    missing: list[str] = []
    for baseline in FORGEJO_RECONCILIATION_BASELINES:
        row: dict[str, bool] = {}
        for variant in FORGEJO_RECONCILIATION_VARIANTS:
            path = args.run_directory / f"{baseline}-{variant}.json"
            if not path.exists():
                missing.append(path.name)
                continue
            report = _read(path)
            row[variant] = bool(report.get("evaluation", {}).get("passed"))
        matrix[baseline] = row
    counts = {name: sum(row.values()) for name, row in matrix.items()}
    variant_count = len(FORGEJO_RECONCILIATION_VARIANTS)
    maximum = max(counts.values(), default=variant_count)
    universal = [name for name, count in counts.items() if count == variant_count]
    payload = {
        "schema_version": "1.0",
        "artifact_type": "forgejo_reconciliation_fixed_baseline_summary",
        "scenario_id": args.scenario_id,
        "variant_count": variant_count,
        "baseline_count": len(FORGEJO_RECONCILIATION_BASELINES),
        "matrix": matrix,
        "pass_counts": counts,
        "maximum_pass_rate": maximum / variant_count,
        "maximum_pass_rate_below_half": maximum / variant_count < 0.5,
        "universal_baselines": universal,
        "missing_reports": missing,
    }
    payload["passed"] = (
        not missing
        and not universal
        and bool(payload["maximum_pass_rate_below_half"])
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
