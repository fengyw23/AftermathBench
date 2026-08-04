from __future__ import annotations

import copy
import unittest

from aftermath_bench.forgejo_promotion_boundary_audit import (
    MUTABLE_DIMENSIONS,
    PROTECTED_DIMENSIONS,
    REQUIRED_VARIANTS,
    audit_forgejo_promotion_boundaries,
)


def _reports() -> dict[str, dict[str, object]]:
    mutable = {
        "dispatch_request_not_reached": ("absent", "absent", "old", "absent", "absent"),
        "workflow_queued_runner_unavailable": ("queued", "absent", "old", "absent", "absent"),
        "signed_bundle_completed_deployment_missing": ("completed", "valid", "old", "absent", "absent"),
        "deployment_completed_attestation_missing": ("completed", "valid", "target", "absent", "absent"),
        "attestation_accepted_release_metadata_missing": ("completed", "valid", "target", "accepted", "absent"),
        "promotion_completed_response_lost": ("completed", "valid", "target", "accepted", "complete"),
    }
    protected = ("approved", "v6.1.4", "preserved", "open")
    return {
        variant: {
            "dimension_projection": {
                **dict(zip(MUTABLE_DIMENSIONS, values, strict=True)),
                **dict(zip(PROTECTED_DIMENSIONS, protected, strict=True)),
            },
            "replay_bound": True,
            "native_state_sha256": f"sha-{variant}",
            "reference_passed": True,
        }
        for variant, values in mutable.items()
    }


class ForgejoPromotionBoundaryAuditTest(unittest.TestCase):
    def test_accepts_six_cross_system_boundaries_with_stable_protected_state(self) -> None:
        result = audit_forgejo_promotion_boundaries(_reports())
        self.assertTrue(result.passed)
        self.assertEqual(set(_reports()), REQUIRED_VARIANTS)

    def test_rejects_release_only_variation(self) -> None:
        reports = _reports()
        for report in reports.values():
            projection = report["dimension_projection"]
            for dimension in MUTABLE_DIMENSIONS[:-1]:
                projection[dimension] = "unchanged"
        result = audit_forgejo_promotion_boundaries(reports)
        self.assertFalse(result.checks["every_recovery_system_actually_varies"])

    def test_rejects_hidden_damage_to_prior_release(self) -> None:
        reports = copy.deepcopy(_reports())
        reports["promotion_completed_response_lost"]["dimension_projection"][
            "prior_release"
        ] = "deleted"
        result = audit_forgejo_promotion_boundaries(reports)
        self.assertFalse(
            result.checks["protected_state_is_identical_across_boundaries"]
        )


if __name__ == "__main__":
    unittest.main()
