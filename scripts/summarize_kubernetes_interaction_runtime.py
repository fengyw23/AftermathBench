from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from aftermath_bench.evidence_projection import projection_admission_report
from aftermath_bench.integrations.kubernetes_interaction_scope import (
    INTERACTION_FACT_GROUPS,
    KUBERNETES_INTERACTION_VARIANTS,
)


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-directory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--projection-output", type=Path, required=True)
    args = parser.parse_args()
    boundaries = {
        variant: _read(args.run_directory / f"{variant}-boundary.json")
        for variant in KUBERNETES_INTERACTION_VARIANTS
    }
    references = {
        variant: _read(args.run_directory / f"{variant}-reference.json")
        for variant in KUBERNETES_INTERACTION_VARIANTS
    }
    projection = projection_admission_report(
        variant_facts={
            variant: report["counterfactual_facts"]
            for variant, report in boundaries.items()
        },
        variant_scopes={
            variant: report["semantic_recovery_direction"]
            for variant, report in references.items()
        },
        evidence_fact_groups=INTERACTION_FACT_GROUPS,
    )
    projection.update(
        {
            "scenario_id": "k8s-constraint-interactions-dev-005",
            "source": "replayed native Kubernetes failure boundaries",
        }
    )
    checks = {
        "all_boundaries_valid": all(report.get("passed") for report in boundaries.values()),
        "all_references_pass": all(
            report.get("evaluation", {}).get("passed")
            and report.get("control_error") is None
            for report in references.values()
        ),
        "prefix_fingerprint_stable": len(
            {str(report.get("prefix_fingerprint")) for report in boundaries.values()}
        )
        == 1,
        "surface_error_identical": len(
            {str(report.get("surface_result")) for report in boundaries.values()}
        )
        == 1,
        "all_projection_groups_have_native_witnesses": bool(
            projection.get("all_declared_groups_have_witnesses")
        ),
        "projection_witnesses>=10": int(
            projection.get("projection_witness_count", 0)
        )
        >= 10,
        "semantic_scopes>=8": len(
            {
                str(report.get("semantic_recovery_direction"))
                for report in references.values()
            }
        )
        >= 8,
    }
    summary = {
        "schema_version": "1.0",
        "scenario_id": "k8s-constraint-interactions-dev-005",
        "variant_count": len(boundaries),
        "reference_pass_count": sum(
            bool(report.get("evaluation", {}).get("passed"))
            for report in references.values()
        ),
        "semantic_scope_count": len(
            {
                str(report.get("semantic_recovery_direction"))
                for report in references.values()
            }
        ),
        "projection_witness_count": projection.get("projection_witness_count", 0),
        "checks": checks,
        "passed": all(checks.values()),
    }
    _write(args.projection_output, projection)
    _write(args.output, summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
