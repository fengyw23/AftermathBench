from __future__ import annotations

import unittest

from scripts.run_erpnext_sales_return_failure import (
    validate_sales_return_boundary,
)


def _committed_evidence() -> dict:
    return {
        "sales_return": {"docstatus": 1},
        "credit_note": {"docstatus": 0},
        "replacement_delivery_note": {"docstatus": 1},
        "replacement_invoices": [{"docstatus": 0}],
        "stock_ledger_entries": [
            {
                "voucher_no": "DN-RETURN",
                "actual_qty": 2,
                "is_cancelled": 0,
            }
        ],
        "rq_jobs": [],
        "pickup_delivery": {"key": "DN-RETURN"},
    }


def _gateway_event(outcome: str) -> list[dict]:
    return [
        {
            "method": "POST",
            "path": "/api/method/frappe.client.submit",
            "outcome": outcome,
            "upstream_status": (
                None if outcome == "request_suppressed" else 200
            ),
        }
    ]


class ERPNextSalesReturnBoundaryTest(unittest.TestCase):
    def test_committed_response_lost_boundary_passes(self) -> None:
        report = validate_sales_return_boundary(
            "database_committed_response_lost",
            _committed_evidence(),
            {"sales_return": "DN-RETURN"},
            _gateway_event("upstream_completed_response_dropped"),
        )
        self.assertTrue(report["passed"], report["failures"])

    def test_request_not_reached_boundary_passes(self) -> None:
        evidence = _committed_evidence()
        evidence.update(
            {
                "sales_return": {"docstatus": 0},
                "replacement_delivery_note": {"docstatus": 0},
                "replacement_invoices": [],
                "stock_ledger_entries": [],
                "pickup_delivery": None,
            }
        )
        report = validate_sales_return_boundary(
            "request_not_reached",
            evidence,
            {"sales_return": "DN-RETURN"},
            _gateway_event("request_suppressed"),
        )
        self.assertTrue(report["passed"], report["failures"])


if __name__ == "__main__":
    unittest.main()
