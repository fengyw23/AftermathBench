from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from .erpnext_evaluator import protected_fingerprint
from .frappe import FrappeHTTPAdapter


def _payload(response: dict[str, Any]) -> dict[str, Any]:
    value = response.get("data", response.get("message", response))
    if not isinstance(value, dict):
        raise RuntimeError(f"expected a document payload, got: {value!r}")
    return value


@dataclass(frozen=True)
class ProcurementPrefix:
    purchase_order: str
    purchase_receipt: str
    purchase_invoice: str
    payment_entry: str
    protected_fingerprints: dict[str, str]
    trace: tuple[dict[str, Any], ...]


class ERPNextProcurementPrefixBuilder:
    COMPANY = "Aftermath Laboratories LLC"
    COMPANY_ABBR = "AL"
    SUPPLIER = "Northwind Scientific"
    ITEM_CODE = "LAB-WS-01"
    WAREHOUSE = "Stores - AL"
    UNIT_PRICE_USD = 4800

    def __init__(self, adapter: FrappeHTTPAdapter):
        self.adapter = adapter

    def _exists(self, doctype: str, name: str) -> bool:
        response = self.adapter.list_resources(
            doctype,
            fields=["name"],
            filters={"name": name},
            limit=1,
        )
        return bool(response.get("data", []))

    def prepare_public_fixture(self) -> None:
        """Create task master data through the same public REST boundary."""
        if not self._exists("Supplier", self.SUPPLIER):
            self.adapter.create_resource(
                "Supplier",
                {
                    "supplier_name": self.SUPPLIER,
                    "supplier_group": "All Supplier Groups",
                    "supplier_type": "Company",
                    "country": "United States",
                },
            )
        if not self._exists("Item", self.ITEM_CODE):
            self.adapter.create_resource(
                "Item",
                {
                    "item_code": self.ITEM_CODE,
                    "item_name": "Laboratory Imaging Workstation",
                    "item_group": "Products",
                    "stock_uom": "Nos",
                    "is_stock_item": 1,
                    "valuation_rate": self.UNIT_PRICE_USD,
                    "standard_rate": self.UNIT_PRICE_USD,
                },
            )
        webhook_name = "Aftermath Payment Remittance"
        if not self._exists("Webhook", webhook_name):
            self.adapter.create_resource(
                "Webhook",
                {
                    "name": webhook_name,
                    "webhook_doctype": "Payment Entry",
                    "webhook_docevent": "on_submit",
                    "enabled": 1,
                    "request_url": (
                        "http://remittance:8080/webhooks/remittance"
                    ),
                    "request_method": "POST",
                    "request_structure": "JSON",
                    "background_jobs_queue": "short",
                    "webhook_json": (
                        '{"payment_entry":"{{ doc.name }}",'
                        '"purchase_invoice":'
                        '"{{ doc.references[0].reference_name }}"}'
                    ),
                    "webhook_headers": [
                        {
                            "key": "Content-Type",
                            "value": "application/json",
                        }
                    ],
                },
            )

    def build(self) -> ProcurementPrefix:
        transaction_date = date.today()
        schedule_date = transaction_date + timedelta(days=14)
        trace: list[dict[str, Any]] = []

        order = _payload(self.adapter.create_resource(
            "Purchase Order",
            {
                "company": self.COMPANY,
                "supplier": self.SUPPLIER,
                "transaction_date": transaction_date.isoformat(),
                "schedule_date": schedule_date.isoformat(),
                "currency": "USD",
                "items": [
                    {
                        "item_code": self.ITEM_CODE,
                        "qty": 1,
                        "rate": self.UNIT_PRICE_USD,
                        "warehouse": self.WAREHOUSE,
                        "schedule_date": schedule_date.isoformat(),
                    }
                ],
            },
        ))
        trace.append({"kind": "write", "tool": "create Purchase Order", "name": order["name"]})
        order = _payload(
            self.adapter.submit_document("Purchase Order", order["name"])
        )
        trace.append({"kind": "write", "tool": "submit Purchase Order", "name": order["name"]})

        receipt_template = _payload(self.adapter.call_method(
            "erpnext.buying.doctype.purchase_order.purchase_order.make_purchase_receipt",
            {"source_name": order["name"]},
        ))
        receipt = _payload(
            self.adapter.create_resource("Purchase Receipt", receipt_template)
        )
        trace.append({"kind": "write", "tool": "create Purchase Receipt", "name": receipt["name"]})
        receipt = _payload(
            self.adapter.submit_document("Purchase Receipt", receipt["name"])
        )
        trace.append({"kind": "write", "tool": "submit Purchase Receipt", "name": receipt["name"]})

        invoice_template = _payload(self.adapter.call_method(
            "erpnext.stock.doctype.purchase_receipt.purchase_receipt.make_purchase_invoice",
            {"source_name": receipt["name"]},
        ))
        invoice = _payload(
            self.adapter.create_resource("Purchase Invoice", invoice_template)
        )
        trace.append({"kind": "write", "tool": "create Purchase Invoice", "name": invoice["name"]})
        invoice = _payload(
            self.adapter.submit_document("Purchase Invoice", invoice["name"])
        )
        trace.append({"kind": "write", "tool": "submit Purchase Invoice", "name": invoice["name"]})

        payment_template = _payload(self.adapter.call_method(
            "erpnext.accounts.doctype.payment_entry.payment_entry.get_payment_entry",
            {
                "dt": "Purchase Invoice",
                "dn": invoice["name"],
                "bank_account": f"Cash - {self.COMPANY_ABBR}",
                "reference_date": transaction_date.isoformat(),
            },
        ))
        payment = _payload(
            self.adapter.create_resource("Payment Entry", payment_template)
        )
        trace.append({"kind": "write", "tool": "create Payment Entry", "name": payment["name"]})

        protected = {
            "purchase_order": protected_fingerprint("purchase_order", order),
            "purchase_receipt": protected_fingerprint(
                "purchase_receipt",
                receipt,
            ),
            "purchase_invoice": protected_fingerprint(
                "purchase_invoice",
                invoice,
            ),
        }
        return ProcurementPrefix(
            purchase_order=str(order["name"]),
            purchase_receipt=str(receipt["name"]),
            purchase_invoice=str(invoice["name"]),
            payment_entry=str(payment["name"]),
            protected_fingerprints=protected,
            trace=tuple(trace),
        )

