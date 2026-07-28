import unittest
from unittest.mock import patch

from aftermath_bench.integrations.erpnext_evidence import (
    ERPNextEvidenceCollector,
    ProcurementPaymentIDs,
)


class _FakeAdapter:
    def __init__(self):
        self.list_calls = []
        self.documents = {
            ("Purchase Order", "PO-1"): {"name": "PO-1", "docstatus": 1},
            ("Purchase Receipt", "PR-1"): {"name": "PR-1", "docstatus": 1},
            ("Purchase Invoice", "PI-1"): {
                "name": "PI-1",
                "docstatus": 1,
                "outstanding_amount": 0,
            },
            ("Payment Entry", "PAY-1"): {
                "name": "PAY-1",
                "docstatus": 1,
                "references": [
                    {
                        "reference_doctype": "Purchase Invoice",
                        "reference_name": "PI-1",
                    }
                ],
            },
            ("Payment Entry", "PAY-OTHER"): {
                "name": "PAY-OTHER",
                "docstatus": 1,
                "references": [],
            },
        }

    def get_resource(self, doctype, name):
        return {"data": self.documents[(doctype, name)]}

    def list_resources(self, doctype, **kwargs):
        self.list_calls.append((doctype, kwargs))
        if doctype == "Payment Entry":
            return {"data": [{"name": "PAY-1"}, {"name": "PAY-OTHER"}]}
        if doctype == "Stock Ledger Entry":
            return {
                "data": [
                    {
                        "voucher_no": "PR-1",
                        "actual_qty": 1,
                        "is_cancelled": False,
                    }
                ]
            }
        if doctype == "GL Entry":
            return {
                "data": [
                    {"voucher_no": "PAY-1", "debit": 100, "credit": 0},
                    {"voucher_no": "PAY-1", "debit": 0, "credit": 100},
                    {"voucher_no": "UNRELATED", "debit": 1, "credit": 1},
                ]
            }
        if doctype == "RQ Job":
            return {"data": [{"name": "job-1", "status": "finished"}]}
        raise AssertionError(doctype)


class ERPNextEvidenceCollectorTest(unittest.TestCase):
    @patch.object(
        ERPNextEvidenceCollector,
        "_remittance",
        return_value={"key": "PAY-1", "attempt_count": 1},
    )
    def test_collects_only_invoice_relevant_payment_and_ledger(self, _remittance):
        collector = ERPNextEvidenceCollector(_FakeAdapter())
        evidence = collector.collect(
            ProcurementPaymentIDs(
                purchase_order="PO-1",
                purchase_receipt="PR-1",
                purchase_invoice="PI-1",
            )
        )
        self.assertEqual(
            [payment["name"] for payment in evidence["payment_entries"]],
            ["PAY-1"],
        )
        self.assertEqual(len(evidence["gl_entries"]), 2)
        self.assertEqual(evidence["remittance"]["key"], "PAY-1")
        rq_call = next(
            kwargs
            for doctype, kwargs in collector.adapter.list_calls
            if doctype == "RQ Job"
        )
        self.assertEqual(rq_call["order_by"], "creation desc")


if __name__ == "__main__":
    unittest.main()
