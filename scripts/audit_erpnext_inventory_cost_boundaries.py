from __future__ import annotations

import argparse
import json
from pathlib import Path

from aftermath_bench.inventory_cost_boundary_audit import (
    REQUIRED_VARIANTS,
    audit_inventory_cost_boundaries,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit four native ERPNext inventory-cost boundaries."
    )
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    reports = {
        variant: json.loads((args.directory / f"{variant}.json").read_text(encoding="utf-8"))
        for variant in REQUIRED_VARIANTS
    }
    audit = audit_inventory_cost_boundaries(reports)
    payload = {
        "schema_version": "0.1",
        "artifact_type": "erpnext_inventory_cost_boundary_audit",
        "passed": audit.passed,
        "checks": audit.checks,
        "observed": audit.observed,
        "reports": {
            variant: {
                "native_state_sha256": report["native_state_sha256"],
                "dimension_projection": report["dimension_projection"],
                "reference_passed": report["reference_passed"],
            }
            for variant, report in reports.items()
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if audit.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
