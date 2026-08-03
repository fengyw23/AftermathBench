from __future__ import annotations

import copy
import unittest

from aftermath_bench.erpnext_manufacturing_state_evidence import (
    manufacturing_boundary_projection,
)
from aftermath_bench.erpnext_sales_return_state_evidence import (
    canonical_state_fingerprint,
)
from aftermath_bench.native_boundary_equivalence import (
    native_boundaries_equivalent,
)


class NativeBoundaryEquivalenceTests(unittest.TestCase):
    def test_unregistered_family_requires_exact_capture(self) -> None:
        boundary = {"state": {"record": "draft"}, "binding": "same"}
        self.assertTrue(
            native_boundaries_equivalent("other-family", boundary, boundary)
        )
        replay = copy.deepcopy(boundary)
        replay["state"]["record"] = "submitted"
        self.assertFalse(
            native_boundaries_equivalent("other-family", boundary, replay)
        )

    def test_manufacturing_accepts_only_terminal_queue_audit_drift(self) -> None:
        boundary = self._capture(
            {"work_order": {"status": "Completed"}, "rq_jobs": []}
        )
        replay = self._capture(
            {
                "work_order": {"status": "Completed"},
                "rq_jobs": [{"name": "job-1", "status": "finished"}],
            }
        )
        self.assertTrue(
            native_boundaries_equivalent(
                "erpnext-manufacturing-rework",
                boundary,
                replay,
            )
        )

        pending = self._capture(
            {
                "work_order": {"status": "Completed"},
                "rq_jobs": [{"name": "job-1", "status": "queued"}],
            }
        )
        self.assertFalse(
            native_boundaries_equivalent(
                "erpnext-manufacturing-rework",
                boundary,
                pending,
            )
        )

    def test_projection_cannot_hide_source_or_exact_fingerprint_drift(self) -> None:
        boundary = self._capture({"rq_jobs": []})
        replay = self._capture(
            {"rq_jobs": [{"name": "job-1", "status": "finished"}]}
        )
        replay["failure_report_file_sha256"] = "b" * 64
        self.assertFalse(
            native_boundaries_equivalent(
                "erpnext-manufacturing-rework",
                boundary,
                replay,
            )
        )
        replay = self._capture(
            {"rq_jobs": [{"name": "job-1", "status": "finished"}]}
        )
        replay["state_fingerprint"] = "b" * 64
        self.assertFalse(
            native_boundaries_equivalent(
                "erpnext-manufacturing-rework",
                boundary,
                replay,
            )
        )

    @staticmethod
    def _capture(state: dict) -> dict:
        return {
            "schema_version": "1.0",
            "artifact_type": "erpnext_manufacturing_state_evidence",
            "scenario_id": "manufacturing-1",
            "instance_id": "dev-001",
            "variant_id": "committed",
            "phase": "boundary",
            "failure_report_file_sha256": "a" * 64,
            "state_fingerprint": canonical_state_fingerprint(state),
            "failure_state_semantic_fingerprint": (
                canonical_state_fingerprint(
                    manufacturing_boundary_projection(state)
                )
            ),
            "state": state,
        }


if __name__ == "__main__":
    unittest.main()
