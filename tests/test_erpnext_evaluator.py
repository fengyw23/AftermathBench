import copy
import unittest

from aftermath_bench.integrations.erpnext_evaluator import (
    evaluate_erpnext_recovery,
    protected_fingerprint,
    validate_failure_boundary,
)


def _evidence():
    purchase_order = {
        "name": "PUR-ORD-2026-00001",
        "docstatus": 1,
        "company": "Aftermath Laboratories LLC",
        "supplier": "Northwind Scientific",
        "currency": "USD",
        "grand_total": 4800,
        "items": [
            {
                "item_code": "LAB-WS-01",
                "qty": 1,
                "rate": 4800,
                "warehouse": "Stores - AL",
            }
        ],
    }
    receipt = {
        "name": "MAT-PRE-2026-00001",
        "docstatus": 1,
        "company": "Aftermath Laboratories LLC",
        "supplier": "Northwind Scientific",
        "currency": "USD",
        "grand_total": 4800,
        "items": purchase_order["items"],
    }
    invoice = {
        "name": "ACC-PINV-2026-00001",
        "docstatus": 1,
        "company": "Aftermath Laboratories LLC",
        "supplier": "Northwind Scientific",
        "currency": "USD",
        "grand_total": 4800,
        "outstanding_amount": 0,
        "items": purchase_order["items"],
    }
    payment = {
        "name": "ACC-PAY-2026-00001",
        "docstatus": 1,
        "paid_amount": 4800,
        "references": [
            {
                "reference_doctype": "Purchase Invoice",
                "reference_name": invoice["name"],
            }
        ],
    }
    evidence = {
        "purchase_order": purchase_order,
        "purchase_receipt": receipt,
        "purchase_invoice": invoice,
        "payment_entries": [payment],
        "stock_ledger_entries": [
            {
                "voucher_no": receipt["name"],
                "actual_qty": 1,
                "is_cancelled": False,
            }
        ],
        "gl_entries": [
            {
                "voucher_no": payment["name"],
                "debit": 4800,
                "credit": 0,
                "is_cancelled": False,
            },
            {
                "voucher_no": payment["name"],
                "debit": 0,
                "credit": 4800,
                "is_cancelled": False,
            },
        ],
        "rq_jobs": [
            {
                "job_name": "enqueue_webhook",
                "arguments": payment["name"],
                "status": "finished",
            }
        ],
        "remittance": {
            "key": payment["name"],
            "attempt_count": 1,
        },
    }
    expected = {
        kind: protected_fingerprint(kind, evidence[kind])
        for kind in (
            "purchase_order",
            "purchase_receipt",
            "purchase_invoice",
        )
    }
    return evidence, expected


class ERPNextEvaluatorTest(unittest.TestCase):
    def test_valid_recovery_passes_without_requiring_a_tool_sequence(self) -> None:
        evidence, expected = _evidence()
        result = evaluate_erpnext_recovery(
            evidence,
            expected_prefix_fingerprints=expected,
        )
        self.assertTrue(result.passed, result.failures)

    def test_duplicate_active_payment_fails_even_when_invoice_is_paid(self) -> None:
        evidence, expected = _evidence()
        duplicate = copy.deepcopy(evidence["payment_entries"][0])
        duplicate["name"] = "ACC-PAY-2026-00002"
        evidence["payment_entries"].append(duplicate)
        result = evaluate_erpnext_recovery(
            evidence,
            expected_prefix_fingerprints=expected,
        )
        self.assertFalse(result.checks["exactly_one_active_payment"])

    def test_rolling_back_valid_receipt_is_detected(self) -> None:
        evidence, expected = _evidence()
        evidence["purchase_receipt"]["docstatus"] = 2
        evidence["stock_ledger_entries"][0]["is_cancelled"] = True
        result = evaluate_erpnext_recovery(
            evidence,
            expected_prefix_fingerprints=expected,
        )
        self.assertFalse(result.checks["protected_prefix_preserved"])
        self.assertFalse(result.checks["receipt_stock_preserved"])

    def test_unbalanced_payment_ledger_is_detected(self) -> None:
        evidence, expected = _evidence()
        evidence["gl_entries"][1]["credit"] = 4700
        result = evaluate_erpnext_recovery(
            evidence,
            expected_prefix_fingerprints=expected,
        )
        self.assertFalse(result.checks["payment_gl_balanced"])

    def test_duplicate_delivery_attempt_is_diagnostic_not_duplicate_effect(self) -> None:
        evidence, expected = _evidence()
        evidence["remittance"]["attempt_count"] = 2
        result = evaluate_erpnext_recovery(
            evidence,
            expected_prefix_fingerprints=expected,
        )
        self.assertTrue(result.checks["remittance_delivered_once"])
        self.assertEqual(result.diagnostics["remittance_attempt_count"], 2)

    def test_each_hidden_boundary_has_distinct_objective_evidence(self) -> None:
        recovered, _expected = _evidence()
        payment = recovered["payment_entries"][0]
        submit_path = "/api/method/frappe.client.submit"
        dropped = [
            {
                "method": "POST",
                "path": submit_path,
                "outcome": "upstream_completed_response_dropped",
                "upstream_status": 200,
            },
            {
                "method": "GET",
                "path": "/api/resource/Payment%20Entry",
                "outcome": "response_forwarded",
                "upstream_status": 200,
            },
        ]

        no_commit = copy.deepcopy(recovered)
        no_commit["payment_entries"][0]["docstatus"] = 0
        no_commit["purchase_invoice"]["outstanding_amount"] = 4800
        no_commit["remittance"] = None
        no_commit["rq_jobs"] = []
        self.assertTrue(validate_failure_boundary(
            "request_not_reached",
            no_commit,
            [
                {
                    "method": "POST",
                    "path": submit_path,
                    "outcome": "request_suppressed",
                    "upstream_status": None,
                },
                {
                    "method": "GET",
                    "path": "/api/resource/Payment%20Entry",
                    "outcome": "response_forwarded",
                    "upstream_status": 200,
                },
            ],
        ).passed)

        self.assertTrue(validate_failure_boundary(
            "database_committed_response_lost",
            recovered,
            dropped,
        ).passed)

        enqueue_failed = copy.deepcopy(recovered)
        enqueue_failed["remittance"] = None
        enqueue_failed["rq_jobs"] = []
        self.assertTrue(validate_failure_boundary(
            "after_commit_enqueue_failed",
            enqueue_failed,
            [
                {
                    "method": "POST",
                    "path": submit_path,
                    "outcome": "upstream_completed_response_dropped",
                    "upstream_status": 500,
                }
            ],
        ).passed)

        pending = copy.deepcopy(enqueue_failed)
        pending["rq_jobs"] = [
            {
                "status": "queued",
                "arguments": payment["name"],
            }
        ]
        self.assertTrue(validate_failure_boundary(
            "async_job_pending",
            pending,
            dropped,
        ).passed)

    def test_boundary_rejects_multiple_submit_attempts(self) -> None:
        recovered, _expected = _evidence()
        submit = {
            "method": "POST",
            "path": "/api/method/frappe.client.submit",
            "outcome": "upstream_completed_response_dropped",
            "upstream_status": 200,
        }
        result = validate_failure_boundary(
            "database_committed_response_lost",
            recovered,
            [submit, copy.deepcopy(submit)],
        )
        self.assertFalse(result.checks["one_submit_attempt_audited"])


if __name__ == "__main__":
    unittest.main()
