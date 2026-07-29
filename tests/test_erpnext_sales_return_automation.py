from __future__ import annotations

import unittest

from aftermath_bench.integrations.erpnext_sales_return_prefix import (
    ensure_sales_exchange_automation,
)


class FakeAdapter:
    def __init__(self, *, delivery_docstatus: int, invoice=None):
        self.delivery_docstatus = delivery_docstatus
        self.invoice = invoice
        self.calls = []

    def get_resource(self, doctype, name):
        self.calls.append(("get_resource", doctype, name))
        if doctype == "Delivery Note":
            return {
                "data": {
                    "name": name,
                    "docstatus": self.delivery_docstatus,
                }
            }
        return {"data": self.invoice}

    def submit_document(self, doctype, name):
        self.calls.append(("submit_document", doctype, name))
        self.delivery_docstatus = 1
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
                "doctype": "Sales Invoice",
                "items": [{"sales_order": arguments["source_name"]}],
            }
        }

    def create_resource(self, doctype, document):
        self.calls.append(("create_resource", doctype))
        self.invoice = {
            **document,
            "name": "SINV-EXCHANGE",
            "docstatus": 0,
        }
        return {"data": self.invoice}


PREFIX = {
    "replacement_sales_order": "SO-EXCHANGE",
    "replacement_delivery_note": "DN-EXCHANGE",
}


class SalesExchangeAutomationTest(unittest.TestCase):
    def test_submits_delivery_and_creates_draft_invoice(self) -> None:
        adapter = FakeAdapter(delivery_docstatus=0)
        result = ensure_sales_exchange_automation(
            adapter,  # type: ignore[arg-type]
            PREFIX,
        )
        self.assertEqual(
            result["actions"],
            ["create draft replacement Sales Invoice"],
        )
        self.assertFalse(
            any(call[0] == "submit_document" for call in adapter.calls)
        )

    def test_reuses_existing_exchange_invoice(self) -> None:
        adapter = FakeAdapter(
            delivery_docstatus=1,
            invoice={
                "name": "SINV-EXISTING",
                "docstatus": 0,
                "items": [{"sales_order": "SO-EXCHANGE"}],
            },
        )
        result = ensure_sales_exchange_automation(
            adapter,  # type: ignore[arg-type]
            PREFIX,
        )
        self.assertEqual(result["replacement_invoice"], "SINV-EXISTING")
        self.assertEqual(result["actions"], [])
        self.assertFalse(
            any(call[0] == "create_resource" for call in adapter.calls)
        )


if __name__ == "__main__":
    unittest.main()
