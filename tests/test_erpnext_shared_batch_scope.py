from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from aftermath_bench.integrations.erpnext_shared_batch_scope import (
    SHARED_BATCH_RECOVERY_SIGNATURES,
    build_shared_batch_scope_decision_matrix,
)
from aftermath_bench.scope_decision_audit import analyze_scope_decision_matrix


class SharedBatchScopeDecisionTests(unittest.TestCase):
    def _reports(self, root: Path):
        states = {
            "request_not_reached": (0, False, []),
            "job_card_committed_certificate_delivered_response_lost": (
                1,
                True,
                [],
            ),
            "job_card_committed_certificate_enqueue_failed": (1, False, []),
            "job_card_committed_certificate_job_pending": (
                1,
                False,
                [{"status": "queued"}],
            ),
        }
        reports = {}
        for variant, (docstatus, delivered, jobs) in states.items():
            payload = {
                "scenario_id": "shared-test",
                "variant": variant,
                "boundary_validation": {"passed": True},
                "boundary_evidence": {
                    "corrective_job_card": {
                        "docstatus": docstatus,
                        "total_completed_qty": 3 if docstatus else 0,
                    },
                    "certificate_delivery": (
                        {
                            "key": "calibration:test",
                            "attempt_count": 1,
                        }
                        if delivered
                        else None
                    ),
                    "rq_jobs": jobs,
                },
            }
            path = root / f"{variant}.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            reports[variant] = (path, payload)
        return reports

    def test_three_public_surfaces_are_jointly_necessary(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            matrix = build_shared_batch_scope_decision_matrix(
                self._reports(Path(directory)), scenario_id="shared-test"
            )
        audit = analyze_scope_decision_matrix(matrix)
        self.assertTrue(audit.identifiable)
        self.assertEqual(audit.variant_count, 4)
        self.assertEqual(audit.recovery_signature_count, 4)
        self.assertEqual(audit.minimum_static_certificate_size, 3)
        self.assertEqual(audit.optimal_adaptive_worst_case_depth, 3)
        self.assertEqual(audit.single_surface_solvers, ())

    def test_rejects_an_incomplete_matched_group(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            reports = self._reports(Path(directory))
            reports.pop(next(iter(SHARED_BATCH_RECOVERY_SIGNATURES)))
            with self.assertRaises(ValueError):
                build_shared_batch_scope_decision_matrix(
                    reports, scenario_id="shared-test"
                )


if __name__ == "__main__":
    unittest.main()
