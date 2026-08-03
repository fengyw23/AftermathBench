from __future__ import annotations

import copy
import unittest
from unittest.mock import Mock

from scripts.run_erpnext_manufacturing_failure import (
    collect_manufacturing_boundary_evidence,
    validate_manufacturing_boundary,
)


class ERPNextManufacturingBoundaryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.prefix = {
            "corrective_job_card": "JC-C",
            "accepted_manufacture_stock_entry": "SE-A",
            "expected_corrective_operation_cost": 120,
            "accepted_quantity": 8,
        }
        self.evidence = {
            "corrective_job_card": {"name": "JC-C", "docstatus": 1},
            "accepted_manufacture_stock_entry": {"name": "SE-A", "docstatus": 1},
            "work_order": {"produced_qty": 8, "corrective_operation_cost": 120},
            "manufacture_stock_entries": [
                {"name": "SE-A", "docstatus": 1, "purpose": "Manufacture"}
            ],
            "rq_jobs": [],
            "quality_release_delivery": {"key": "JC-C", "attempt_count": 1},
        }
        self.gateway = [
            {
                "method": "POST",
                "path": "/api/method/frappe.client.submit",
                "outcome": "upstream_completed_response_dropped",
                "upstream_status": 200,
            }
        ]

    def test_committed_response_lost_boundary(self) -> None:
        result = validate_manufacturing_boundary(
            "database_committed_response_lost",
            self.evidence,
            self.prefix,
            self.gateway,
        )
        self.assertTrue(result["passed"], result["failures"])

    def test_request_not_reached_requires_draft_and_no_effects(self) -> None:
        evidence = copy.deepcopy(self.evidence)
        evidence["corrective_job_card"]["docstatus"] = 0
        evidence["work_order"]["corrective_operation_cost"] = 0
        evidence["quality_release_delivery"] = None
        gateway = copy.deepcopy(self.gateway)
        gateway[0]["outcome"] = "request_suppressed"
        gateway[0]["upstream_status"] = None
        result = validate_manufacturing_boundary(
            "request_not_reached", evidence, self.prefix, gateway
        )
        self.assertTrue(result["passed"], result["failures"])

    def test_pending_variant_requires_a_visible_job(self) -> None:
        evidence = copy.deepcopy(self.evidence)
        evidence["quality_release_delivery"] = None
        evidence["rq_jobs"] = [{"status": "queued", "arguments": '{"doc":"JC-C"}'}]
        result = validate_manufacturing_boundary(
            "async_job_pending", evidence, self.prefix, self.gateway
        )
        self.assertTrue(result["passed"], result["failures"])

    def test_pending_capture_waits_until_native_job_is_visible(self) -> None:
        absent = copy.deepcopy(self.evidence)
        absent["quality_release_delivery"] = None
        queued = copy.deepcopy(absent)
        queued["rq_jobs"] = [
            {"status": "queued", "arguments": '{"doc":"JC-C"}'}
        ]
        collector = Mock()
        collector.collect.side_effect = [absent, queued]
        evidence = collect_manufacturing_boundary_evidence(
            "async_job_pending",
            collector,
            self.prefix,
            monotonic=lambda: 0,
            sleep=lambda _seconds: None,
        )
        self.assertEqual(evidence, queued)
        self.assertEqual(collector.collect.call_count, 2)

    def test_response_lost_capture_waits_for_delivery_settlement(self) -> None:
        pending = copy.deepcopy(self.evidence)
        pending["quality_release_delivery"] = None
        pending["rq_jobs"] = [
            {"status": "started", "arguments": '{"doc":"JC-C"}'}
        ]
        collector = Mock()
        collector.collect.side_effect = [pending, self.evidence]
        evidence = collect_manufacturing_boundary_evidence(
            "database_committed_response_lost",
            collector,
            self.prefix,
            monotonic=lambda: 0,
            sleep=lambda _seconds: None,
        )
        self.assertEqual(evidence, self.evidence)
        self.assertEqual(collector.collect.call_count, 2)

    def test_boundary_uses_instance_quantity_instead_of_public_fixture(self) -> None:
        prefix = {**self.prefix, "accepted_quantity": 11}
        evidence = copy.deepcopy(self.evidence)
        evidence["work_order"]["produced_qty"] = 11
        result = validate_manufacturing_boundary(
            "database_committed_response_lost",
            evidence,
            prefix,
            self.gateway,
        )
        self.assertTrue(result["passed"], result["failures"])


if __name__ == "__main__":
    unittest.main()
