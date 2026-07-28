from __future__ import annotations

import unittest

from aftermath_bench.integrations.erpnext_return_prefix import (
    ensure_return_replacement_automation,
)


class FakeAdapter:
    def __init__(self, *, receipt_docstatus: int, invoice=None):
        self.receipt_docstatus = receipt_docstatus
        self.invoice = invoice
        self.calls = []

    def get_resource(self, doctype, name):
        self.calls.append(("get_resource", doctype, name))
        if doctype == "Purchase Receipt":
            return {
                "data": {
                    "name": name,
                    "docstatus": self.receipt_docstatus,
                }
            }
        return {"data": self.invoice}

    def submit_document(self, doctype, name):
        self.calls.append(("submit_document", doctype, name))
        self.receipt_docstatus = 1
        return {"data": {"name": name, "docstatus": 1}}

    def list_resources(self, doctype, **kwargs):
        self.calls.append(("list_resources", doctype))
        if self.invoice is None:
            return {"data": []}
        return {"data": [{"name": self.invoice["name"]}]}

    def call_method(self, method, arguments):
        self.calls.append(("call_method", method, arguments))
        return {
            "message": {
                "doctype": "Purchase Invoice",
                "items": [
                    {
                        "purchase_receipt": arguments["source_name"],
                    }
                ],
            }
        }

    def create_resource(self, doctype, document):
        self.calls.append(("create_resource", doctype))
        self.invoice = {
            **document,
            "name": "PINV-REPLACEMENT",
            "docstatus": 0,
        }
        return {"data": self.invoice}


PREFIX = {
    "replacement_purchase_receipt": "PREC-REPLACEMENT",
}


class ReturnReplacementAutomationTest(unittest.TestCase):
    def test_submits_receipt_and_creates_draft_invoice(self) -> None:
        adapter = FakeAdapter(receipt_docstatus=0)
        result = ensure_return_replacement_automation(
            adapter,  # type: ignore[arg-type]
            PREFIX,
        )
        self.assertEqual(result["replacement_invoice_docstatus"], 0)
        self.assertEqual(
            result["actions"],
            [
                "submit replacement Purchase Receipt",
                "create draft replacement Purchase Invoice",
            ],
        )

    def test_reuses_existing_active_invoice(self) -> None:
        adapter = FakeAdapter(
            receipt_docstatus=1,
            invoice={
                "name": "PINV-EXISTING",
                "docstatus": 0,
                "items": [
                    {"purchase_receipt": "PREC-REPLACEMENT"}
                ],
            },
        )
        result = ensure_return_replacement_automation(
            adapter,  # type: ignore[arg-type]
            PREFIX,
        )
        self.assertEqual(result["replacement_invoice"], "PINV-EXISTING")
        self.assertEqual(result["actions"], [])
        self.assertFalse(
            any(call[0] == "create_resource" for call in adapter.calls)
        )


if __name__ == "__main__":
    unittest.main()
