from __future__ import annotations

import json
import unittest

from aftermath_bench.integrations.erpnext_evaluator import (
    protected_fingerprint,
)
from aftermath_bench.integrations.erpnext_sales_return_evaluator import (
    evaluate_sales_return_recovery,
)


def _doc(
    name: str,
    *,
    item: str,
    qty: float,
    doctype: str,
    outstanding: float = 0,
) -> dict:
    return {
        "name": name,
        "doctype": doctype,
        "docstatus": 1,
        "company": "Aftermath Laboratories LLC",
        "customer": "Acme Field Services",
        "currency": "USD",
        "grand_total": abs(qty) * 100,
        "outstanding_amount": outstanding,
        "status": "Completed",
        "items": [
            {
                "item_code": item,
                "qty": qty,
                "rate": 100,
                "warehouse": "Stores - AL",
            }
        ],
    }


class ERPNextSalesReturnEvaluatorTest(unittest.TestCase):
    def setUp(self) -> None:
        affected = "FIELD-TABLET-A"
        unaffected = "FIELD-ROUTER-X"
        replacement = "FIELD-TABLET-B"
        original_order = _doc(
            "SO-1",
            item=affected,
            qty=10,
            doctype="Sales Order",
        )
        original_order["items"].append(
            {
                "item_code": unaffected,
                "qty": 2,
                "rate": 100,
                "warehouse": "Stores - AL",
            }
        )
        original_delivery = _doc(
            "DN-1",
            item=affected,
            qty=10,
            doctype="Delivery Note",
        )
        original_delivery["items"].append(
            {
                "item_code": unaffected,
                "qty": 2,
                "rate": 100,
                "warehouse": "Stores - AL",
            }
        )
        unaffected_invoice = _doc(
            "SINV-2",
            item=unaffected,
            qty=2,
            doctype="Sales Invoice",
        )
        affected_invoice = _doc(
            "SINV-1",
            item=affected,
            qty=10,
            doctype="Sales Invoice",
        )
        payment = {
            "name": "PAY-1",
            "docstatus": 1,
            "received_amount": 1200,
            "references": [
                {"reference_name": "SINV-1"},
                {"reference_name": "SINV-2"},
            ],
        }
        self.prefix = {
            "affected_item": affected,
            "unaffected_item": unaffected,
            "replacement_item": replacement,
            "defective_quantity": 2,
            "original_quantities": {affected: 10, unaffected: 2},
            "original_delivery_note": "DN-1",
            "sales_return": "DN-RET-1",
            "replacement_delivery_note": "DN-REP-1",
            "credit_note": "SINV-CN-1",
            "shared_payment_entry": "PAY-1",
            "protected_fingerprints": {
                "original_sales_order": protected_fingerprint(
                    "sales_order",
                    original_order,
                ),
                "original_delivery_note": protected_fingerprint(
                    "delivery_note",
                    original_delivery,
                ),
                "unaffected_invoice": protected_fingerprint(
                    "sales_invoice",
                    unaffected_invoice,
                ),
                "shared_payment": json.dumps(
                    {
                        "name": "PAY-1",
                        "docstatus": 1,
                        "received_amount": 1200,
                        "references": ["SINV-1", "SINV-2"],
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            },
        }
        gl = []
        for voucher in ("PAY-1", "SINV-CN-1"):
            gl.extend(
                [
                    {
                        "voucher_no": voucher,
                        "debit": 200,
                        "credit": 0,
                        "is_cancelled": 0,
                    },
                    {
                        "voucher_no": voucher,
                        "debit": 0,
                        "credit": 200,
                        "is_cancelled": 0,
                    },
                ]
            )
        self.evidence = {
            "original_sales_order": original_order,
            "original_delivery_note": original_delivery,
            "quality_inspection": {
                "name": "QI-1",
                "docstatus": 1,
                "status": "Rejected",
                "item_code": affected,
            },
            "affected_invoice": affected_invoice,
            "unaffected_invoice": unaffected_invoice,
            "shared_payment_entry": payment,
            "sales_returns": [
                _doc(
                    "DN-RET-1",
                    item=affected,
                    qty=-2,
                    doctype="Delivery Note",
                )
            ],
            "credit_notes": [
                _doc(
                    "SINV-CN-1",
                    item=affected,
                    qty=-2,
                    doctype="Sales Invoice",
                )
            ],
            "replacement_delivery_notes": [
                _doc(
                    "DN-REP-1",
                    item=replacement,
                    qty=2,
                    doctype="Delivery Note",
                )
            ],
            "replacement_invoices": [
                _doc(
                    "SINV-REP-1",
                    item=replacement,
                    qty=2,
                    doctype="Sales Invoice",
                )
            ],
            "stock_ledger_entries": [
                {
                    "voucher_no": "DN-1",
                    "item_code": affected,
                    "actual_qty": -10,
                    "is_cancelled": 0,
                },
                {
                    "voucher_no": "DN-1",
                    "item_code": unaffected,
                    "actual_qty": -2,
                    "is_cancelled": 0,
                },
                {
                    "voucher_no": "DN-RET-1",
                    "item_code": affected,
                    "actual_qty": 2,
                    "is_cancelled": 0,
                },
                {
                    "voucher_no": "DN-REP-1",
                    "item_code": replacement,
                    "actual_qty": -2,
                    "is_cancelled": 0,
                },
            ],
            "gl_entries": gl,
            "rq_jobs": [],
            "pickup_delivery": {
                "key": "DN-RET-1",
                "attempt_count": 1,
            },
        }

    def test_complete_sales_recovery_passes(self) -> None:
        result = evaluate_sales_return_recovery(
            self.evidence,
            prefix=self.prefix,
        )
        self.assertTrue(result.passed, result.failures)

    def test_duplicate_exchange_invoice_fails_protocol_safety(self) -> None:
        self.evidence["replacement_invoices"].append(
            dict(self.evidence["replacement_invoices"][0])
        )
        result = evaluate_sales_return_recovery(
            self.evidence,
            prefix=self.prefix,
        )
        self.assertFalse(result.passed)
        self.assertFalse(result.checks["no_duplicate_replacement_invoice"])
        self.assertTrue(result.components["preservation"])


if __name__ == "__main__":
    unittest.main()
