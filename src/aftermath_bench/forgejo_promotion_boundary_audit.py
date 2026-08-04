from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


REQUIRED_VARIANTS = frozenset(
    {
        "dispatch_request_not_reached",
        "workflow_queued_runner_unavailable",
        "signed_bundle_completed_deployment_missing",
        "deployment_completed_attestation_missing",
        "attestation_accepted_release_metadata_missing",
        "promotion_completed_response_lost",
    }
)
MUTABLE_DIMENSIONS = (
    "actions_owner",
    "signed_bundle",
    "production_deployment",
    "external_attestation",
    "release_metadata",
)
PROTECTED_DIMENSIONS = (
    "approval_record",
    "prior_release",
    "protected_environment",
    "unrelated_issue",
)


@dataclass(frozen=True)
class ForgejoPromotionBoundaryAudit:
    passed: bool
    checks: dict[str, bool]
    observed: dict[str, Any]


def audit_forgejo_promotion_boundaries(
    reports: Mapping[str, Mapping[str, Any]],
) -> ForgejoPromotionBoundaryAudit:
    variants = set(reports)
    mutable_projections: dict[str, tuple[str, ...]] = {}
    protected_projections: dict[str, tuple[str, ...]] = {}
    complete = True
    replay_bound = True
    references_pass = True
    for variant, report in reports.items():
        projection = report.get("dimension_projection")
        if not isinstance(projection, Mapping):
            complete = False
            continue
        mutable = tuple(str(projection.get(key, "")) for key in MUTABLE_DIMENSIONS)
        protected = tuple(
            str(projection.get(key, "")) for key in PROTECTED_DIMENSIONS
        )
        if any(not value for value in (*mutable, *protected)):
            complete = False
            continue
        mutable_projections[variant] = mutable
        protected_projections[variant] = protected
        replay_bound = replay_bound and bool(report.get("replay_bound")) and bool(
            report.get("native_state_sha256")
        )
        references_pass = references_pass and bool(report.get("reference_passed"))

    mutable_counts = {
        key: len({values[index] for values in mutable_projections.values()})
        for index, key in enumerate(MUTABLE_DIMENSIONS)
    }
    checks = {
        "complete_variant_coverage": variants == REQUIRED_VARIANTS,
        "complete_cross_system_projection": (
            complete and len(mutable_projections) == len(REQUIRED_VARIANTS)
        ),
        "every_recovery_system_actually_varies": all(
            count >= 2 for count in mutable_counts.values()
        ),
        "six_distinct_boundary_signatures": (
            len(set(mutable_projections.values())) == 6
        ),
        "protected_state_is_identical_across_boundaries": (
            len(set(protected_projections.values())) == 1
        ),
        "all_reports_replay_bound": replay_bound,
        "all_reference_recoveries_pass": references_pass,
    }
    return ForgejoPromotionBoundaryAudit(
        passed=all(checks.values()),
        checks=checks,
        observed={
            "variant_count": len(variants),
            "distinct_boundary_signature_count": len(
                set(mutable_projections.values())
            ),
            "distinct_values_by_recovery_dimension": mutable_counts,
            "protected_projection_count": len(set(protected_projections.values())),
        },
    )


__all__ = [
    "ForgejoPromotionBoundaryAudit",
    "MUTABLE_DIMENSIONS",
    "PROTECTED_DIMENSIONS",
    "REQUIRED_VARIANTS",
    "audit_forgejo_promotion_boundaries",
]
