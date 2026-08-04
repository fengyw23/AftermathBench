from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .scope_decision_audit import analyze_scope_decision_matrix

PUBLIC_SURFACE_GROUPS: dict[str, dict[str, tuple[str, ...]]] = {
    "erpnext-inventory-cost-settlement": {
        "voucher_document": ("landed_cost_voucher",),
        "inventory_and_accounting_ledgers": ("stock_ledger", "gl_entries"),
        "reposting_owner": ("reposting_owner",),
        "external_attestation": ("external_attestation",),
    },
    "forgejo-approved-artifact-promotion": {
        "actions_owner": ("actions_owner",),
        "deployment_controller": ("signed_bundle", "production_deployment"),
        "external_attestation": ("external_attestation",),
        "release_metadata": ("release_metadata",),
    },
}


def audit_replayed_scope_decisions(
    *, boundary_audit: Mapping[str, Any], scenario: Mapping[str, Any]
) -> dict[str, Any]:
    """Measure recovery-scope identifiability from replayed public surfaces.

    Related fields returned by one ordinary tool are deliberately grouped into
    one observation. This produces a conservative lower bound on query depth
    and prevents database row identities from masquerading as reasoning depth.
    """

    family = str(scenario.get("family", ""))
    groups = PUBLIC_SURFACE_GROUPS.get(family)
    if groups is None:
        raise ValueError(f"no public-surface grouping for {family!r}")
    reports = boundary_audit.get("reports")
    variants = scenario.get("matched_variants")
    if not isinstance(reports, Mapping) or not isinstance(variants, list):
        raise TypeError("scope audit requires replay reports and matched variants")
    signatures = {
        str(row["id"]): str(row["recovery_signature_class"])
        for row in variants
        if isinstance(row, Mapping)
    }
    if set(reports) != set(signatures):
        raise ValueError("boundary audit and scenario variants differ")

    rows: list[dict[str, Any]] = []
    for variant in sorted(signatures):
        report = reports[variant]
        if not isinstance(report, Mapping):
            raise TypeError(f"boundary report {variant} is not an object")
        projection = report.get("dimension_projection")
        if not isinstance(projection, Mapping):
            raise TypeError(f"boundary report {variant} lacks a projection")
        observations = {
            surface: {dimension: projection.get(dimension) for dimension in dimensions}
            for surface, dimensions in groups.items()
        }
        if any(
            value is None
            for observation in observations.values()
            for value in observation.values()
        ):
            raise ValueError(f"boundary report {variant} has missing public evidence")
        rows.append(
            {
                "variant": variant,
                "recovery_signature": signatures[variant],
                "observations": observations,
            }
        )

    matrix = {
        "schema_version": "1.0",
        "scenario_id": scenario.get("scenario_id"),
        "source": "replayed native boundary dimension projections",
        "surface_grouping": groups,
        "rows": rows,
    }
    audit = analyze_scope_decision_matrix(matrix)
    profile = scenario.get("planned_admission_profile", {}).get(
        "scope_decision", {}
    )
    required_static = int(profile.get("minimum_static_certificate_size", 2))
    required_adaptive = int(profile.get("minimum_adaptive_worst_case_depth", 2))
    observed_static = audit.minimum_static_certificate_size or 0
    observed_adaptive = audit.optimal_adaptive_worst_case_depth or 0
    checks = {
        "all_scopes_identifiable": audit.identifiable,
        "no_single_surface_solver": not audit.single_surface_solvers,
        "static_certificate_meets_profile": observed_static >= required_static,
        "adaptive_depth_meets_profile": observed_adaptive >= required_adaptive,
    }
    return {
        "schema_version": "1.0",
        "scenario_id": scenario.get("scenario_id"),
        "family": family,
        "matrix": matrix,
        "observed": {
            "variant_count": audit.variant_count,
            "recovery_signature_count": audit.recovery_signature_count,
            "public_surface_count": audit.observable_surface_count,
            "minimum_static_certificate_size": audit.minimum_static_certificate_size,
            "optimal_adaptive_worst_case_depth": (
                audit.optimal_adaptive_worst_case_depth
            ),
            "single_surface_solvers": list(audit.single_surface_solvers),
            "indistinguishable_variant_pairs": [
                list(pair) for pair in audit.indistinguishable_variant_pairs
            ],
        },
        "required": {
            "minimum_static_certificate_size": required_static,
            "minimum_adaptive_worst_case_depth": required_adaptive,
        },
        "checks": checks,
        "passed": all(checks.values()),
    }


__all__ = ["PUBLIC_SURFACE_GROUPS", "audit_replayed_scope_decisions"]
