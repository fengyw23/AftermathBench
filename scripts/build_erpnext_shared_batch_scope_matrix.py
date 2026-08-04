from __future__ import annotations

import argparse
import json
from pathlib import Path

from aftermath_bench.integrations.erpnext_shared_batch_scope import (
    SHARED_BATCH_RECOVERY_SIGNATURES,
    build_shared_batch_scope_decision_matrix,
)
from aftermath_bench.scope_decision_audit import analyze_scope_decision_matrix


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build the replay-derived shared-batch scope decision matrix."
    )
    parser.add_argument("--boundary-directory", type=Path, required=True)
    parser.add_argument("--scenario-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    reports = {}
    for variant in SHARED_BATCH_RECOVERY_SIGNATURES:
        path = args.boundary_directory / f"{variant}.json"
        reports[variant] = (
            path,
            json.loads(path.read_text(encoding="utf-8")),
        )
    result = build_shared_batch_scope_decision_matrix(
        reports, scenario_id=args.scenario_id
    )
    audit = analyze_scope_decision_matrix(result)
    if (
        not audit.identifiable
        or audit.minimum_static_certificate_size != 3
        or audit.optimal_adaptive_worst_case_depth != 3
        or audit.single_surface_solvers
    ):
        raise RuntimeError(f"shared-batch scope admission failed: {audit}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "scenario_id": args.scenario_id,
                "variant_count": audit.variant_count,
                "minimum_static_certificate_size": (
                    audit.minimum_static_certificate_size
                ),
                "optimal_adaptive_worst_case_depth": (
                    audit.optimal_adaptive_worst_case_depth
                ),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
