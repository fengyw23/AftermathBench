from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .integrations.kubernetes_settlement_v2_faults import (
    KUBERNETES_SETTLEMENT_V2_VARIANTS,
    SURFACE_ERROR,
)
from .integrations.kubernetes_settlement_v2_prefix import SCENARIO_ID


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def audit_settlement_v2_replay(directory: str | Path) -> dict[str, Any]:
    root = Path(directory)
    boundaries = {
        variant: _read(root / f"{variant}.json")
        for variant in KUBERNETES_SETTLEMENT_V2_VARIANTS
    }
    references = {
        variant: _read(root / f"{variant}-reference.json")
        for variant in KUBERNETES_SETTLEMENT_V2_VARIANTS
    }
    prefix_hashes = {
        str(report["prefix_fingerprint"]) for report in boundaries.values()
    }
    mutation_counts = {
        variant: len(report.get("mutation_tools", []))
        for variant, report in references.items()
    }
    signatures = {
        tuple(report.get("mutation_tools", []))
        for report in references.values()
    }
    target_signals = {
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
        "minimum_four_mutations": min(mutation_counts.values(), default=0)
        >= 4,
        "at_least_three_recovery_signatures": len(signatures) >= 3,
        "four_distinct_partial_states": len(set(target_signals.values())) == 4,
        "seven_downstream_obligations": all(
            int(report.get("downstream_repairs", 0)) >= 7
            for report in references.values()
        ),
    }
    return {
        "schema_version": "0.2",
        "scenario_id": SCENARIO_ID,
        "source": "live native partial-boundary and public-tool reference replay",
        "passed": all(checks.values()),
        "checks": checks,
        "observed": {
            "variant_count": len(boundaries),
            "prefix_hash_count": len(prefix_hashes),
            "mutation_counts": mutation_counts,
            "distinct_recovery_signature_count": len(signatures),
            "distinct_partial_state_count": len(set(target_signals.values())),
        },
    }
