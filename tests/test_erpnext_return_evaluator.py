import copy
import json
import unittest

from aftermath_bench.integrations.erpnext_evaluator import (
    protected_fingerprint,
)
from aftermath_bench.integrations.erpnext_return_evaluator import (
    evaluate_partial_return_recovery,
)


def _document(name, doctype, item_code, qty, rate, **fields):
    return {
        "name": name,
        "doctype": doctype,
        "docstatus": 1,
        "company": "Aftermath Laboratories LLC",
        "supplier": "Northwind Scientific",
        "currency": "USD",
        "grand_total": abs(qty * rate),
        "items": [
            {
                "item_code": item_code,
                "qty": qty,
                "rate": rate,
                "warehouse": "Stores - AL",
                **fields.pop("item_fields", {}),
            }
        ],
        **fields,
    }


def _fixture():
    order = _document("PO-1", "Purchase Order", "DOCK", 10, 420)
    order["items"].append(
        {
            "item_code": "DISPLAY",
            "qty": 4,
            "rate": 1250,
            "warehouse": "Stores - AL",
        }
    )
    order["grand_total"] = 9200
    receipt = copy.deepcopy(order)
    receipt.update({"name": "PR-1", "doctype": "Purchase Receipt"})
    affected_invoice = _document(
        "PI-A",
        "Purchase Invoice",
        "DOCK",
        10,
        420,
        outstanding_amount=0,
    )
    unaffected_invoice = _document(
        "PI-U",
        "Purchase Invoice",
        "DISPLAY",
        4,
        1250,
        outstanding_amount=0,
    )
    payment = {
        "name": "PAY-1",
        "doctype": "Payment Entry",
        "docstatus": 1,
        "paid_amount": 9200,
        "references": [
            {"reference_name": "PI-A"},
            {"reference_name": "PI-U"},
        ],
    }
    purchase_return = _document(
        "PR-RET-1",
        "Purchase Receipt",
        "DOCK",
        -2,
        420,
        is_return=1,
        return_against="PR-1",
    )
    debit = _document(
        "DN-1",
        "Purchase Invoice",
        "DOCK",
        -2,
        420,
        outstanding_amount=0,
        is_return=1,
        return_against="PI-A",
    )
    replacement_receipt = _document(
        "PR-R-1",
        "Purchase Receipt",
        "DOCK-R2",
        2,
        420,
        item_fields={"purchase_order": "PO-R-1"},
    )
    replacement_invoice = _document(
        "PI-R-1",
        "Purchase Invoice",
        "DOCK-R2",
        2,
        420,
        outstanding_amount=0,
        item_fields={"purchase_receipt": "PR-R-1"},
    )
    evidence = {
        "original_purchase_order": order,
        "original_purchase_receipt": receipt,
        "quality_inspection": {
            "name": "QI-1",
            "docstatus": 1,
            "status": "Rejected",
            "item_code": "DOCK",
        },
        "affected_invoice": affected_invoice,
        "unaffected_invoice": unaffected_invoice,
        "shared_payment_entry": payment,
        "purchase_return": purchase_return,
        "debit_note": debit,
        "replacement_purchase_order": _document(
            "PO-R-1",
            "Purchase Order",
            "DOCK-R2",
            2,
            420,
        ),
        "replacement_purchase_receipt": replacement_receipt,
        "purchase_returns": [purchase_return],
        "debit_notes": [debit],
        "replacement_receipts": [replacement_receipt],
        "replacement_invoices": [replacement_invoice],
        "stock_ledger_entries": [
            {"voucher_no": "PR-1", "item_code": "DOCK", "actual_qty": 10},
            {"voucher_no": "PR-1", "item_code": "DISPLAY", "actual_qty": 4},
            {"voucher_no": "PR-RET-1", "item_code": "DOCK", "actual_qty": -2},
            {"voucher_no": "PR-R-1", "item_code": "DOCK-R2", "actual_qty": 2},
        ],
        "gl_entries": [
            {"voucher_no": voucher, "debit": 840, "credit": 0}
            for voucher in ("PAY-1", "PR-RET-1", "DN-1")
        ]
        + [
            {"voucher_no": voucher, "debit": 0, "credit": 840}
            for voucher in ("PAY-1", "PR-RET-1", "DN-1")
        ],
        "rq_jobs": [
            {"status": "finished", "arguments": "PR-RET-1"}
        ],
        "pickup_delivery": {"key": "PR-RET-1", "attempt_count": 1},
    }
    prefix = {
        "affected_item": "DOCK",
        "unaffected_item": "DISPLAY",
        "replacement_item": "DOCK-R2",
        "defective_quantity": 2,
        "original_quantities": {"DOCK": 10, "DISPLAY": 4},
        "original_purchase_receipt": "PR-1",
        "purchase_return": "PR-RET-1",
        "replacement_purchase_receipt": "PR-R-1",
        "shared_payment_entry": "PAY-1",
        "debit_note": "DN-1",
        "protected_fingerprints": {
            "original_purchase_order": protected_fingerprint(
                "purchase_order",
                order,
            ),
            "original_purchase_receipt": protected_fingerprint(
                "purchase_receipt",
                receipt,
            ),
            "unaffected_invoice": protected_fingerprint(
                "purchase_invoice",
                unaffected_invoice,
            ),
            "shared_payment": json.dumps(
                {
                    "name": "PAY-1",
                    "docstatus": 1,
                    "paid_amount": 9200,
                    "references": ["PI-A", "PI-U"],
                },
                sort_keys=True,
                separators=(",", ":"),
            ),
        },
    }
    return evidence, prefix


class PartialReturnEvaluatorTest(unittest.TestCase):
    def test_complete_native_state_passes(self) -> None:
        evidence, prefix = _fixture()
        result = evaluate_partial_return_recovery(evidence, prefix=prefix)
        self.assertTrue(result.passed, result.failures)

    def test_returning_the_unaffected_item_is_over_repair(self) -> None:
        evidence, prefix = _fixture()
        evidence["purchase_returns"][0]["items"].append(
            {"item_code": "DISPLAY", "qty": -4, "rate": 1250}
        )
        result = evaluate_partial_return_recovery(evidence, prefix=prefix)
        self.assertFalse(result.checks["exact_partial_return_submitted"])

    def test_canceling_shared_payment_fails_preservation(self) -> None:
        evidence, prefix = _fixture()
        evidence["shared_payment_entry"]["docstatus"] = 2
        result = evaluate_partial_return_recovery(evidence, prefix=prefix)
        self.assertFalse(result.components["preservation"])

    def test_duplicate_replacement_invoice_fails_protocol_safety(self) -> None:
        evidence, prefix = _fixture()
        duplicate = copy.deepcopy(evidence["replacement_invoices"][0])
        duplicate["name"] = "PI-R-2"
        evidence["replacement_invoices"].append(duplicate)
        result = evaluate_partial_return_recovery(evidence, prefix=prefix)
        self.assertFalse(result.checks["no_duplicate_replacement_invoice"])


if __name__ == "__main__":
    unittest.main()
