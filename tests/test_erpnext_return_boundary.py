from __future__ import annotations

import unittest

from scripts.run_erpnext_return_failure import _validate_boundary


class ReturnBoundaryAuditTest(unittest.TestCase):
    def test_ignores_normal_downstream_submit_after_ambiguous_submit(
        self,
    ) -> None:
        prefix = {
            "purchase_return": "PREC-RETURN",
            "replacement_purchase_receipt": "PREC-REPLACEMENT",
        }
        evidence = {
            "purchase_return": {"docstatus": 1},
            "debit_note": {"docstatus": 0},
            "replacement_purchase_receipt": {"docstatus": 1},
            "replacement_invoices": [{"docstatus": 0}],
            "stock_ledger_entries": [
                {
                    "voucher_no": "PREC-RETURN",
                    "is_cancelled": 0,
                }
            ],
            "rq_jobs": [],
            "pickup_delivery": {"attempt_count": 1},
        }
        gateway_events = [
            {
                "method": "POST",
                "path": "/api/method/frappe.client.submit",
                "mode": "drop_response",
                "outcome": "upstream_completed_response_dropped",
                "upstream_status": 200,
            },
            {
                "method": "POST",
                "path": "/api/method/frappe.client.submit",
                "mode": "normal",
                "outcome": "response_forwarded",
                "upstream_status": 200,
            },
        ]

        result = _validate_boundary(
            "database_committed_response_lost",
            evidence,
            prefix,
            gateway_events,
        )

        self.assertTrue(result["passed"])
        self.assertTrue(result["checks"]["one_submit_attempt_audited"])
        self.assertTrue(result["checks"]["upstream_completed"])


if __name__ == "__main__":
    unittest.main()
