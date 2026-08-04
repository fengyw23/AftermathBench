from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .scope_decision_audit import analyze_scope_decision_matrix


def build_independent_gap_design(
    *,
    scenario_id: str,
    obligations: Mapping[str, Sequence[str]],
) -> dict[str, Any]:
    """Build a pre-runtime star design for independently repairable effects.

    The all-valid boundary and every one-gap boundary form a matched group in
    which every public query surface is necessary.  This is a design-time
    lower-bound check only; native replay must later replace each declared
    observation with evidence captured from the real systems.
    """

    if len(obligations) < 3:
        raise ValueError("independent-gap design requires at least three obligations")
    normalized: dict[str, tuple[str, ...]] = {}
    for obligation, surfaces in obligations.items():
        name = str(obligation).strip()
        values = tuple(sorted({str(item).strip() for item in surfaces if str(item).strip()}))
        if not name or not values:
            raise ValueError("each obligation requires one or more public surfaces")
        normalized[name] = values

    rows: list[dict[str, Any]] = []
    states = (("all_effects_valid", None),) + tuple(
        (f"{obligation}_gap", obligation) for obligation in normalized
    )
    for variant, gap in states:
        rows.append(
            {
                "variant": variant,
                "recovery_signature": (
                    "verify_and_preserve" if gap is None else f"repair_{gap}"
                ),
                "observations": {
                    obligation: obligation != gap for obligation in normalized
                },
            }
        )

    matrix = {
        "schema_version": "1.0-design",
        "scenario_id": scenario_id,
        "source": "pre-runtime independent-gap design; not replay evidence",
        "surface_requirements": {
            obligation: list(surfaces)
            for obligation, surfaces in normalized.items()
        },
        "rows": rows,
    }
    audit = analyze_scope_decision_matrix(matrix)
    query_surfaces = sorted(
        {surface for surfaces in normalized.values() for surface in surfaces}
    )
    return {
        "schema_version": "1.0-design",
        "scenario_id": scenario_id,
        "status": "design_only_native_replay_required",
        "obligations": {
            obligation: list(surfaces)
            for obligation, surfaces in normalized.items()
        },
        "matrix": matrix,
        "observed": {
            "variant_count": audit.variant_count,
            "recovery_signature_count": audit.recovery_signature_count,
            "public_query_surface_count": len(query_surfaces),
            "minimum_static_certificate_size": audit.minimum_static_certificate_size,
            "optimal_adaptive_worst_case_depth": (
                audit.optimal_adaptive_worst_case_depth
            ),
            "single_surface_solvers": list(audit.single_surface_solvers),
        },
        "passed_design_gate": (
            audit.identifiable
            and not audit.single_surface_solvers
            and audit.minimum_static_certificate_size == len(query_surfaces)
            and audit.optimal_adaptive_worst_case_depth is not None
            and audit.optimal_adaptive_worst_case_depth >= len(normalized)
        ),
    }


__all__ = ["build_independent_gap_design"]
