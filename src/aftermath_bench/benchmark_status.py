from __future__ import annotations

from typing import Any

from .benchmark_matrix import (
    benchmark_family_index,
    benchmark_slots,
    load_benchmark_matrix,
    validate_benchmark_matrix,
)
from .frozen_hidden_registry import (
    FrozenHiddenRecord,
    load_frozen_hidden_registry,
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


def _slot_coverage(
    *,
    matrix_slots: dict[str, dict[str, Any]],
    scenario_rows: list[dict[str, Any]],
    formal_bindings: tuple[dict[str, Any], ...],
    frozen_hidden_records: tuple[FrozenHiddenRecord, ...] = (),
) -> dict[str, Any]:
    """Describe each planned release slot without double-counting replicas.

    The repository can contain historical development scenarios, consumed hidden
    instances, and several views of the same business instance.  A benchmark
    progress number is useful only when it says which *planned* slot those
    artifacts satisfy.  This projection deliberately requires exact
    ``domain/family/instance/split`` agreement before a scenario can advance a
    slot.
    """

    scenarios_by_slot: dict[str, list[dict[str, Any]]] = {}
    for row in scenario_rows:
        slot_id = (
            f"{row['domain_id']}/{row['family_id']}/{row['instance_id']}"
        )
        scenarios_by_slot.setdefault(slot_id, []).append(row)
    bindings_by_slot = {
        str(binding["formal_slot_id"]): binding
        for binding in formal_bindings
        if binding.get("formal_slot_id") is not None and binding.get("passed")
    }
    frozen_by_slot = {
        record.formal_slot_id: record for record in frozen_hidden_records
    }

    slots: list[dict[str, Any]] = []
    for slot_id, slot in sorted(matrix_slots.items()):
        expected_split = str(slot["split"])
        candidates = [
            row
            for row in scenarios_by_slot.get(slot_id, [])
            if str(row["split"]) == expected_split
        ]
        hard_candidates = [
            row
            for row in candidates
            if row["admission_passed"]
            and row["admitted_tier"] == "hard"
            and row["runtime_execution_admitted"]
        ]
        binding = bindings_by_slot.get(slot_id)
        frozen = frozen_by_slot.get(slot_id)
        if binding is not None:
            state = "formal_bound"
        elif frozen is not None:
            state = "frozen_hidden"
        elif hard_candidates:
            state = "hard_candidate"
        else:
            state = "missing"
        slots.append(
            {
                "slot_id": slot_id,
                "domain_id": str(slot["domain_id"]),
                "family_id": str(slot["family_id"]),
                "instance_id": str(slot["instance_id"]),
                "split": expected_split,
                "variant_count": int(
                    dict(slot["variant_profile"]).get(
                        "required_variant_count", 0
                    )
                ),
                "state": state,
                "formal_binding_scenario_id": (
                    str(binding["scenario_id"]) if binding is not None else None
                ),
                "frozen_hidden_scenario_id": (
                    frozen.scenario_id if frozen is not None else None
                ),
                "frozen_hidden_freeze_run_id": (
                    frozen.freeze_run_id if frozen is not None else None
                ),
                "hard_candidate_scenario_ids": sorted(
                    str(row["scenario_id"]) for row in hard_candidates
                ),
                "matching_scenario_ids": sorted(
                    str(row["scenario_id"]) for row in candidates
                ),
            }
        )

    state_counts = {
        state: sum(1 for row in slots if row["state"] == state)
        for state in (
            "formal_bound",
            "frozen_hidden",
            "hard_candidate",
            "missing",
        )
    }
    case_counts = {
        state: sum(
            int(row["variant_count"])
            for row in slots
            if row["state"] == state
        )
        for state in (
            "formal_bound",
            "frozen_hidden",
            "hard_candidate",
            "missing",
        )
    }
    return {
        "required_slot_count": len(slots),
        "slot_state_counts": state_counts,
        "matched_case_state_counts": case_counts,
        "slots": slots,
    }


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
    mapped_family_keys = {
        (str(row["domain_id"]), str(row["family_id"]))
        for row in family_mapped_rows
    }
    hard_family_keys = {
        (str(row["domain_id"]), str(row["family_id"]))
        for row in runtime_admitted_hard_rows
        if row["family_in_target_matrix"]
    }
    missing_family_keys = sorted(set(matrix_families) - mapped_family_keys)

    release = validate_release_manifest(
        load_release_manifest(default_release_manifest_path()),
        root=root,
    )
    frozen_hidden_records = load_frozen_hidden_registry(
        root / "data" / "frozen_hidden_candidates.json",
        root=root,
    )
    slot_coverage = _slot_coverage(
        matrix_slots=matrix_slots,
        scenario_rows=scenario_rows,
        formal_bindings=release.bindings,
        frozen_hidden_records=frozen_hidden_records,
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
            "unique_target_family_coverage_count": len(mapped_family_keys),
            "hard_admitted_target_family_count": len(hard_family_keys),
            "missing_target_family_count": len(missing_family_keys),
            "missing_target_families": [
                {"domain_id": domain_id, "family_id": family_id}
                for domain_id, family_id in missing_family_keys
            ],
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
            # These are slot-level progress figures.  Unlike the legacy
            # release-manifest development counter, they include an admitted
            # public-development scenario even before its seven-role formal
            # package is sealed.
            "target_slot_state_counts": dict(
                slot_coverage["slot_state_counts"]
            ),
            "target_matched_case_state_counts": dict(
                slot_coverage["matched_case_state_counts"]
            ),
            "hard_development_candidate_count": release.observed[
                "hard_development_candidate_count"
            ],
            "hard_development_candidate_case_count": release.observed[
                "hard_development_candidate_case_count"
            ],
            "frozen_hidden_slot_count": len(frozen_hidden_records),
            "frozen_hidden_matched_case_count": sum(
                record.variant_count for record in frozen_hidden_records
            ),
        },
        "release_manifest": {
            "passed": release.passed,
            "release_state": release.release_state,
            "checks": release.checks,
            "failures": list(release.failures),
            "observed": release.observed,
            "bindings": list(release.bindings),
        },
        "slot_coverage": slot_coverage,
        "frozen_hidden_candidates": [
            {
                "formal_slot_id": record.formal_slot_id,
                "scenario_id": record.scenario_id,
                "variant_count": record.variant_count,
                "freeze_run_id": record.freeze_run_id,
                "public_commitment_sha256": (
                    record.public_commitment_sha256
                ),
                "artifact_url": record.artifact_url,
                "evidence_path": record.evidence_path,
            }
            for record in frozen_hidden_records
        ],
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
