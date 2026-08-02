from __future__ import annotations

import copy
import unittest

from scripts.run_erpnext_manufacturing_failure import (
    validate_manufacturing_boundary,
)


class ERPNextManufacturingBoundaryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.prefix = {
            "corrective_job_card": "JC-C",
            "accepted_manufacture_stock_entry": "SE-A",
            "expected_corrective_operation_cost": 120,
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


if __name__ == "__main__":
    unittest.main()
