from __future__ import annotations

from typing import Any

from .benchmark_matrix import (
    load_benchmark_matrix,
    validate_benchmark_matrix,
)
from .native_admission import validate_native_scenario
from .native_scenario import load_native_scenario, native_scenario_paths
from .runtime_gate import (
    load_runtime_manifest,
    runtime_manifest_paths,
    validate_runtime_manifest,
)
from .schema import repository_root


FORMAL_RELEASE_SPLITS = frozenset({"public_dev", "hidden_test"})


def build_benchmark_status() -> dict[str, Any]:
    """Derive the implemented/planned boundary from repository evidence."""

    matrix = validate_benchmark_matrix(
        load_benchmark_matrix(
            repository_root() / "data" / "benchmark_matrix.json"
        )
    )
    runtimes = [
        validate_runtime_manifest(load_runtime_manifest(path))
        for path in runtime_manifest_paths()
    ]
    runtime_admission = {
        report.runtime_id: report.execution_admitted
        for report in runtimes
    }

    scenario_rows: list[dict[str, Any]] = []
    for path in native_scenario_paths():
        scenario = load_native_scenario(path)
        admission = validate_native_scenario(scenario)
        runtime_id = str(scenario.raw["runtime_id"])
        scenario_rows.append(
            {
                "scenario_id": scenario.scenario_id,
                "family": str(scenario.raw.get("family", "")),
                "runtime_id": runtime_id,
                "split": scenario.split,
                "requested_tier": admission.requested_tier,
                "admitted_tier": admission.admitted_tier,
                "admission_passed": admission.passed,
                "runtime_execution_admitted": runtime_admission.get(
                    runtime_id, False
                ),
                "matched_state_count": len(scenario.variants),
            }
        )

    hard_rows = [
        row
        for row in scenario_rows
        if row["admission_passed"] and row["admitted_tier"] == "hard"
    ]
    runtime_admitted_hard_rows = [
        row for row in hard_rows if row["runtime_execution_admitted"]
    ]
    formal_rows = [
        row for row in scenario_rows if row["split"] in FORMAL_RELEASE_SPLITS
    ]
    formal_hard_rows = [
        row
        for row in formal_rows
        if row["admission_passed"]
        and row["admitted_tier"] == "hard"
        and row["runtime_execution_admitted"]
    ]

    return {
        "status_schema_version": "0.1",
        "release_state": (
            "formal_release_ready"
            if formal_hard_rows
            else "development_only"
        ),
        "planned": {
            **matrix.observed,
            "matrix_valid": matrix.passed,
            "matrix_failures": list(matrix.failures),
        },
        "implemented": {
            "scenario_count": len(scenario_rows),
            "matched_case_count": sum(
                int(row["matched_state_count"]) for row in scenario_rows
            ),
            "hard_admitted_scenario_count": len(hard_rows),
            "hard_admitted_matched_case_count": sum(
                int(row["matched_state_count"]) for row in hard_rows
            ),
            "runtime_admitted_hard_scenario_count": len(
                runtime_admitted_hard_rows
            ),
            "formal_release_scenario_count": len(formal_hard_rows),
            "formal_release_matched_case_count": sum(
                int(row["matched_state_count"]) for row in formal_hard_rows
            ),
        },
        "runtimes": [
            {
                "runtime_id": report.runtime_id,
                "source_audit_passed": report.source_audit_passed,
                "execution_admitted": report.execution_admitted,
                "failures": list(report.failures),
            }
            for report in runtimes
        ],
        "scenarios": scenario_rows,
    }
