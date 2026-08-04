from __future__ import annotations

import copy
import unittest

from aftermath_bench.inventory_cost_boundary_audit import (
    REQUIRED_DIMENSIONS,
    audit_inventory_cost_boundaries,
)


def _reports() -> dict[str, dict[str, object]]:
    projections = {
        "request_not_reached": ("draft", "old", "old", "absent", "absent"),
        "voucher_committed_revaluation_completed_response_lost": (
            "submitted",
            "settled",
            "settled",
            "completed",
            "delivered",
        ),
        "voucher_committed_reposting_job_missing": (
            "submitted",
            "pending",
            "pending",
            "absent",
            "absent",
        ),
        "voucher_committed_reposting_job_pending": (
            "submitted",
            "pending",
            "pending",
            "queued",
            "queued",
        ),
    }
    return {
        variant: {
            "dimension_projection": dict(zip(REQUIRED_DIMENSIONS, values, strict=True)),
            "replay_bound": True,
            "native_state_sha256": f"sha-{variant}",
            "reference_passed": True,
        }
        for variant, values in projections.items()
    }


class InventoryCostBoundaryAuditTest(unittest.TestCase):
    def test_accepts_four_replayed_multidimensional_boundaries(self) -> None:
        report = audit_inventory_cost_boundaries(_reports())
        self.assertTrue(report.passed)
        self.assertEqual(report.observed["distinct_signature_count"], 4)

    def test_rejects_job_only_variation(self) -> None:
        reports = _reports()
        for report in reports.values():
            projection = report["dimension_projection"]
            for dimension in (
                "landed_cost_voucher",
                "stock_ledger",
                "gl_entries",
                "external_attestation",
            ):
                projection[dimension] = "unchanged"
        result = audit_inventory_cost_boundaries(reports)
        self.assertFalse(result.passed)
        self.assertFalse(result.checks["every_dimension_actually_varies"])

    def test_rejects_unbound_or_failed_reference_evidence(self) -> None:
        reports = copy.deepcopy(_reports())
        reports["request_not_reached"]["replay_bound"] = False
        reports["voucher_committed_reposting_job_pending"][
            "reference_passed"
        ] = False
        result = audit_inventory_cost_boundaries(reports)
        self.assertFalse(result.checks["all_reports_replay_bound"])
        self.assertFalse(result.checks["all_reference_recoveries_pass"])


if __name__ == "__main__":
    unittest.main()
