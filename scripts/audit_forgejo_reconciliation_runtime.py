from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from aftermath_bench.integrations.forgejo_reconciliation_faults import (
    FORGEJO_RECONCILIATION_VARIANTS,
    reconciliation_scope_matrix,
)
from aftermath_bench.scope_decision_audit import analyze_scope_decision_matrix


def _read(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError(f"expected object in {path}")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit native independent-gap Forgejo replay."
    )
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    prefix = _read(args.run_root / "prefix.json")
    expected_instance_hash = prefix.get("instance_spec_sha256")
    if not isinstance(expected_instance_hash, str) or not expected_instance_hash:
        raise ValueError("prefix has no instance_spec_sha256")
    first_variant = next(iter(FORGEJO_RECONCILIATION_VARIANTS))
    first_boundary = _read(args.run_root / f"{first_variant}-boundary.json")
    design = reconciliation_scope_matrix(
        scenario_id=str(first_boundary["scenario_id"])
    )
    signatures = {
        variant: specification.recovery_kind
        for variant, specification in FORGEJO_RECONCILIATION_VARIANTS.items()
    }
    reports: dict[str, Any] = {}
    rows: list[dict[str, Any]] = []
    for variant, specification in FORGEJO_RECONCILIATION_VARIANTS.items():
        boundary = _read(args.run_root / f"{variant}-boundary.json")
        reference = _read(args.run_root / f"{variant}-reference.json")
        if boundary.get("scenario_id") != design["scenario_id"]:
            raise ValueError(f"boundary scenario drifted for {variant}")
        if reference.get("scenario_id") != design["scenario_id"]:
            raise ValueError(f"reference scenario drifted for {variant}")
        if boundary.get("instance_spec_sha256") != expected_instance_hash:
            raise ValueError(f"boundary instance drifted for {variant}")
        if reference.get("instance_spec_sha256") != expected_instance_hash:
            raise ValueError(f"reference instance drifted for {variant}")
        projection = boundary["dimension_projection"]
        expected_gap = specification.missing_obligation
        observed_gaps = [name for name, valid in projection.items() if not valid]
        reports[variant] = {
            "boundary_passed": bool(boundary["passed"]),
            "reference_passed": bool(reference["passed"]),
            "instance_spec_sha256": expected_instance_hash,
            "dimension_projection": projection,
            "expected_gap": expected_gap,
            "observed_gaps": observed_gaps,
        }
        rows.append(
            {
                "variant": variant,
                "recovery_signature": signatures[variant],
                "observations": projection,
            }
        )
    matrix = {
        "schema_version": "1.0",
        "scenario_id": design["scenario_id"],
        "source": "replayed native Forgejo boundaries",
        "surface_requirements": design["surface_requirements"],
        "rows": rows,
    }
    scope = analyze_scope_decision_matrix(matrix)
    checks = {
        "all_boundaries_pass": all(row["boundary_passed"] for row in reports.values()),
        "all_references_pass": all(row["reference_passed"] for row in reports.values()),
        "each_boundary_has_only_its_declared_gap": all(
            row["observed_gaps"]
            == ([] if row["expected_gap"] is None else [row["expected_gap"]])
            for row in reports.values()
        ),
        "all_scopes_identifiable": scope.identifiable,
        "no_single_surface_solver": not scope.single_surface_solvers,
        "static_certificate_is_six": scope.minimum_static_certificate_size == 6,
        "adaptive_worst_case_depth_is_six": (
            scope.optimal_adaptive_worst_case_depth == 6
        ),
    }
    payload = {
        "schema_version": "1.0",
        "scenario_id": design["scenario_id"],
        "reports": reports,
        "scope_decision_matrix": matrix,
        "observed": {
            "minimum_static_certificate_size": scope.minimum_static_certificate_size,
            "optimal_adaptive_worst_case_depth": (
                scope.optimal_adaptive_worst_case_depth
            ),
            "single_surface_solvers": list(scope.single_surface_solvers),
        },
        "checks": checks,
        "passed": all(checks.values()),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps({"checks": checks, "observed": payload["observed"]}))
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
