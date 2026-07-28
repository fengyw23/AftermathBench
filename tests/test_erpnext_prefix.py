import unittest

from aftermath_bench.integrations.erpnext_prefix import (
    ERPNextProcurementPrefixBuilder,
)


class _FakeAdapter:
    def __init__(self):
        self.created = []
        self.submitted = []
        self.counter = {
            "Purchase Order": 0,
            "Purchase Receipt": 0,
            "Purchase Invoice": 0,
            "Payment Entry": 0,
        }

    def list_resources(self, *_args, **_kwargs):
        return {"data": []}

    def create_resource(self, doctype, document):
        self.created.append((doctype, document))
        if doctype in self.counter:
            self.counter[doctype] += 1
            prefixes = {
                "Purchase Order": "PO",
                "Purchase Receipt": "PR",
                "Purchase Invoice": "PI",
                "Payment Entry": "PAY",
            }
            result = dict(document)
            result.update(
                {
                    "name": f"{prefixes[doctype]}-{self.counter[doctype]}",
                    "doctype": doctype,
                    "docstatus": 0,
                    "grand_total": 4800,
                    "currency": "USD",
                    "supplier": "Northwind Scientific",
                    "company": "Aftermath Laboratories LLC",
                }
            )
            return {"data": result}
        return {"data": {"name": document.get("name", doctype)}}

    def submit_document(self, doctype, name):
        self.submitted.append((doctype, name))
        created = next(
            document
            for kind, document in reversed(self.created)
            if kind == doctype
        )
        result = dict(created)
        result.update(
            {
                "name": name,
                "doctype": doctype,
                "docstatus": 1,
                "grand_total": 4800,
                "currency": "USD",
                "supplier": "Northwind Scientific",
                "company": "Aftermath Laboratories LLC",
            }
        )
        return {"message": result}

    def call_method(self, method, arguments):
        if method.endswith("make_purchase_receipt"):
            return {
                "message": {
                    "doctype": "Purchase Receipt",
                    "items": [
                        {
                            "item_code": "LAB-WS-01",
                            "qty": 1,
                            "rate": 4800,
                            "warehouse": "Stores - AL",
                        }
                    ],
                }
            }
        if method.endswith("make_purchase_invoice"):
            return {
                "message": {
                    "doctype": "Purchase Invoice",
                    "items": [
                        {
                            "item_code": "LAB-WS-01",
                            "qty": 1,
                            "rate": 4800,
                            "warehouse": "Stores - AL",
                        }
                    ],
                }
            }
        if method.endswith("get_payment_entry"):
            return {
                "message": {
                    "doctype": "Payment Entry",
                    "paid_amount": 4800,
                    "references": [
                        {
                            "reference_doctype": "Purchase Invoice",
                            "reference_name": arguments["dn"],
                        }
                    ],
                }
            }
        raise AssertionError(method)


class ERPNextPrefixBuilderTest(unittest.TestCase):
    def test_prefix_has_seven_real_writes_and_linked_documents(self) -> None:
        adapter = _FakeAdapter()
        builder = ERPNextProcurementPrefixBuilder(adapter)
        builder.prepare_public_fixture()
        prefix = builder.build()
        self.assertEqual(len(prefix.trace), 7)
        self.assertEqual(
            [step["tool"] for step in prefix.trace],
            [
                "create Purchase Order",
                "submit Purchase Order",
                "create Purchase Receipt",
                "submit Purchase Receipt",
                "create Purchase Invoice",
                "submit Purchase Invoice",
                "create Payment Entry",
            ],
        )
        self.assertEqual(prefix.purchase_order, "PO-1")
        self.assertEqual(prefix.purchase_receipt, "PR-1")
        self.assertEqual(prefix.purchase_invoice, "PI-1")
        self.assertEqual(prefix.payment_entry, "PAY-1")

    def test_fixture_webhook_uses_native_on_submit_queue(self) -> None:
        adapter = _FakeAdapter()
        builder = ERPNextProcurementPrefixBuilder(adapter)
        builder.prepare_public_fixture()
        webhook = next(
            document
            for doctype, document in adapter.created
            if doctype == "Webhook"
        )
        self.assertEqual(webhook["webhook_doctype"], "Payment Entry")
        self.assertEqual(webhook["webhook_docevent"], "on_submit")
        self.assertEqual(webhook["background_jobs_queue"], "short")
        self.assertIn("{{ doc.name }}", webhook["webhook_json"])


if __name__ == "__main__":
    unittest.main()
