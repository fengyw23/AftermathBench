from __future__ import annotations

from typing import Any

from .benchmark_matrix import (
    benchmark_family_index,
    benchmark_slots,
    load_benchmark_matrix,
    validate_benchmark_matrix,
)
from .native_admission import validate_native_scenario
from .native_scenario import (
    load_native_scenario,
    native_scenario_paths,
    validate_native_scenario_document,
)
from .release_manifest import (
    default_release_manifest_path,
    load_release_manifest,
    validate_release_manifest,
)
from .runtime_gate import (
    load_runtime_manifest,
    runtime_manifest_paths,
    validate_runtime_manifest,
)
from .schema import repository_root

FORMAL_RELEASE_SPLITS = frozenset({"public_dev", "hidden_test"})


def build_benchmark_status() -> dict[str, Any]:
    """Derive release state from canonical slots and bound evidence."""

    root = repository_root()
    matrix_raw = load_benchmark_matrix(root / "data" / "benchmark_matrix.json")
    matrix = validate_benchmark_matrix(matrix_raw)
    matrix_families = benchmark_family_index(matrix_raw)
    matrix_slots = {
        str(slot["slot_id"]): slot for slot in benchmark_slots(matrix_raw)
    }
    runtimes = [
        validate_runtime_manifest(load_runtime_manifest(path))
        for path in runtime_manifest_paths()
    ]
    runtime_admission = {
        report.runtime_id: report.execution_admitted for report in runtimes
    }

    scenario_rows: list[dict[str, Any]] = []
    for path in native_scenario_paths():
        scenario = load_native_scenario(path)
        document_failures = validate_native_scenario_document(scenario)
        try:
            admission = validate_native_scenario(scenario)
            admitted_tier = admission.admitted_tier
            admission_passed = admission.passed
        except (KeyError, OSError, ValueError):
            admitted_tier = "invalid"
            admission_passed = False
        runtime_id = str(scenario.raw["runtime_id"])
        family_key = (scenario.domain_id, scenario.family_id)
        slot_id = (
            f"{scenario.domain_id}/{scenario.family_id}/"
            f"{scenario.instance_id}"
        )
        scenario_rows.append(
            {
                "scenario_id": scenario.scenario_id,
                "domain_id": scenario.domain_id,
                "family_id": scenario.family_id,
                "instance_id": scenario.instance_id,
                "runtime_id": runtime_id,
                "split": scenario.split,
                "requested_tier": scenario.tier,
                "admitted_tier": admitted_tier,
                "scenario_document_valid": not document_failures,
                "scenario_document_failures": list(document_failures),
                "admission_passed": admission_passed,
                "runtime_execution_admitted": runtime_admission.get(
                    runtime_id, False
                ),
                "family_in_target_matrix": family_key in matrix_families,
                "formal_slot_id": (
                    slot_id if slot_id in matrix_slots else None
                ),
                "formal_slot_split_matches": bool(
                    slot_id in matrix_slots
                    and matrix_slots[slot_id]["split"] == scenario.split
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
    family_mapped_rows = [
        row for row in scenario_rows if row["family_in_target_matrix"]
    ]

    release = validate_release_manifest(
        load_release_manifest(default_release_manifest_path()),
        root=root,
    )
    return {
        "status_schema_version": "1.0",
        "release_state": release.release_state,
        "benchmark_release_id": release.benchmark_release_id,
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
            "matrix_family_mapped_scenario_count": len(family_mapped_rows),
            "hard_admitted_scenario_count": len(hard_rows),
            "hard_admitted_matched_case_count": sum(
                int(row["matched_state_count"]) for row in hard_rows
            ),
            "runtime_admitted_hard_scenario_count": len(
                runtime_admitted_hard_rows
            ),
            "formal_release_scenario_count": release.observed[
                "formal_verified_slot_count"
            ],
            "formal_release_matched_case_count": sum(
                int(row["variant_count"])
                for row in release.bindings
                if row["formal_slot_id"] is not None and row["passed"]
            ),
            "hard_development_candidate_count": release.observed[
                "hard_development_candidate_count"
            ],
            "hard_development_candidate_case_count": release.observed[
                "hard_development_candidate_case_count"
            ],
        },
        "release_manifest": {
            "passed": release.passed,
            "release_state": release.release_state,
            "checks": release.checks,
            "failures": list(release.failures),
            "observed": release.observed,
            "bindings": list(release.bindings),
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
