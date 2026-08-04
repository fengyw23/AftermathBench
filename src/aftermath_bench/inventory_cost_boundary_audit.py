from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


REQUIRED_VARIANTS = frozenset(
    {
        "request_not_reached",
        "voucher_committed_repost_queued_attested_response_lost",
        "voucher_committed_repost_queued_attestation_pending",
        "voucher_committed_repost_completed_attestation_pending",
    }
)
REQUIRED_DIMENSIONS = (
    "landed_cost_voucher",
    "stock_ledger",
    "gl_entries",
    "reposting_owner",
    "external_attestation",
)


@dataclass(frozen=True)
class InventoryCostBoundaryAudit:
    passed: bool
    checks: dict[str, bool]
    observed: dict[str, Any]


def audit_inventory_cost_boundaries(
    reports: Mapping[str, Mapping[str, Any]],
) -> InventoryCostBoundaryAudit:
    variants = set(reports)
    projections: dict[str, tuple[str, ...]] = {}
    replay_bound = True
    references_pass = True
    dimensions_complete = True
    for variant, report in reports.items():
        projection = report.get("dimension_projection")
        if not isinstance(projection, Mapping):
            dimensions_complete = False
            continue
        values: list[str] = []
        for dimension in REQUIRED_DIMENSIONS:
            value = projection.get(dimension)
            if not isinstance(value, str) or not value:
                dimensions_complete = False
                break
            values.append(value)
        else:
            projections[variant] = tuple(values)
        replay_bound = replay_bound and bool(report.get("replay_bound")) and bool(
            report.get("native_state_sha256")
        )
        references_pass = references_pass and bool(report.get("reference_passed"))

    distinct_by_dimension = {
        dimension: len(
            {
                projection[index]
                for projection in projections.values()
                if len(projection) == len(REQUIRED_DIMENSIONS)
            }
        )
        for index, dimension in enumerate(REQUIRED_DIMENSIONS)
    }
    distinct_signatures = len(set(projections.values()))
    checks = {
        "complete_variant_coverage": variants == REQUIRED_VARIANTS,
        "complete_native_dimension_projection": (
            dimensions_complete and len(projections) == len(REQUIRED_VARIANTS)
        ),
        "every_dimension_actually_varies": all(
            count >= 2 for count in distinct_by_dimension.values()
        ),
        "four_distinct_native_boundary_signatures": distinct_signatures == 4,
        "all_reports_replay_bound": replay_bound,
        "all_reference_recoveries_pass": references_pass,
    }
    return InventoryCostBoundaryAudit(
        passed=all(checks.values()),
        checks=checks,
        observed={
            "variant_count": len(variants),
            "distinct_signature_count": distinct_signatures,
            "distinct_values_by_dimension": distinct_by_dimension,
        },
    )


__all__ = [
    "InventoryCostBoundaryAudit",
    "REQUIRED_DIMENSIONS",
    "REQUIRED_VARIANTS",
    "audit_inventory_cost_boundaries",
]
