from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .integrations.kubernetes_migration_faults import (
    KUBERNETES_MIGRATION_VARIANTS,
    SURFACE_ERROR,
)
from .integrations.kubernetes_migration_prefix import SCENARIO_ID


EXPECTED_DIRECTIONS = {
    "change_request_not_reached": "rollback_to_stable",
    "preparation_escaped_migration_failed": "compensate_external_effect",
    "schema_committed_cutover_pending": "forward_complete",
    "cutover_and_publication_committed": "repair_downstream_only",
}


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def audit_migration_replay(directory: str | Path) -> dict[str, Any]:
    root = Path(directory)
    boundaries = {
        variant: _read(root / f"{variant}.json")
        for variant in KUBERNETES_MIGRATION_VARIANTS
    }
    references = {
        variant: _read(root / f"{variant}-reference.json")
        for variant in KUBERNETES_MIGRATION_VARIANTS
    }
    prefix_hashes = {
        str(report["prefix_fingerprint"]) for report in boundaries.values()
    }
    directions = {
        variant: str(report.get("semantic_recovery_direction"))
        for variant, report in references.items()
    }
    mutation_counts = {
        variant: len(report.get("mutation_tools", []))
        for variant, report in references.items()
    }
    boundary_signatures = {
        variant: tuple(sorted(report.get("observed", {}).items()))
        for variant, report in boundaries.items()
    }
    checks = {
        "all_boundaries_pass": all(
            bool(report.get("passed")) for report in boundaries.values()
        ),
        "same_surface_error": all(
            report.get("surface_result") == SURFACE_ERROR
            for report in boundaries.values()
        ),
        "semantic_prefix_hash_stable": len(prefix_hashes) == 1,
        "all_references_pass": all(
            bool(report.get("evaluation", {}).get("passed"))
            and report.get("control_error") is None
            for report in references.values()
        ),
        "directions_match_objective_boundaries": directions == EXPECTED_DIRECTIONS,
        "four_distinct_semantic_directions": len(set(directions.values())) == 4,
        "minimum_four_mutations": min(mutation_counts.values(), default=0) >= 4,
        "four_distinct_partial_states": len(set(boundary_signatures.values())) == 4,
    }
    return {
        "schema_version": "0.3",
        "scenario_id": SCENARIO_ID,
        "source": "live native boundary and public-tool reference replay",
        "passed": all(checks.values()),
        "checks": checks,
        "observed": {
            "variant_count": len(boundaries),
            "prefix_hash_count": len(prefix_hashes),
            "semantic_directions": directions,
            "mutation_counts": mutation_counts,
            "distinct_partial_state_count": len(set(boundary_signatures.values())),
        },
    }
