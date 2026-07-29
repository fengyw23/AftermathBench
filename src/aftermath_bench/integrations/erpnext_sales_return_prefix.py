from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from .erpnext_evaluator import protected_fingerprint
from .erpnext_return_prefix import _payload
from .frappe import FrappeHTTPAdapter


def _money(value: Any) -> float:
    return float(Decimal(str(value)))


@dataclass(frozen=True)
class SalesReturnPrefix:
    scenario_id: str
    company: str
    customer: str
    affected_item: str
    unaffected_item: str
    replacement_item: str
    stock_seed: str
    original_sales_order: str
    original_delivery_note: str
    quality_inspection: str
    affected_invoice: str
    unaffected_invoice: str
    shared_payment_entry: str
    sales_return: str
    credit_note: str
    replacement_sales_order: str
    replacement_delivery_note: str
    defective_quantity: float
    original_quantities: dict[str, float]
    protected_fingerprints: dict[str, str]
    trace: tuple[dict[str, Any], ...]

    def as_dict(self) -> dict[str, Any]:
        return {field: getattr(self, field) for field in self.__dataclass_fields__}


class ERPNextSalesReturnPrefixBuilder:
    WAREHOUSE = "Stores - AL"
    PICKUP_WEBHOOK = "Aftermath Customer Return Pickup"

    def __init__(
        self,
        adapter: FrappeHTTPAdapter,
        *,
        scenario_id: str,
        fixture: dict[str, Any],
    ) -> None:
        self.adapter = adapter
        self.scenario_id = scenario_id
        self.fixture = fixture

    def _exists(self, doctype: str, name: str) -> bool:
        return bool(
            self.adapter.list_resources(
                doctype,
                fields=["name"],
                filters={"name": name},
                limit=1,
            ).get("data", [])
        )

    @staticmethod
    def _trace(
        trace: list[dict[str, Any]],
        tool: str,
        document: dict[str, Any],
    ) -> None:
        trace.append(
            {
                "kind": "write",
                "status": "success",
                "tool": tool,
                "doctype": document.get("doctype"),
                "name": document["name"],
            }
        )

    @staticmethod
    def _select_item(
        document: dict[str, Any],
        item_code: str,
    ) -> dict[str, Any]:
        matches = [
            dict(item)
            for item in document.get("items", [])
            if item.get("item_code") == item_code
        ]
        if len(matches) != 1:
            raise RuntimeError(
                f"expected exactly one {item_code} row, found {len(matches)}"
            )
        return matches[0]

    @staticmethod
    def _set_return_quantity(
        item: dict[str, Any],
        quantity: float,
    ) -> None:
        negative = -abs(float(quantity))
        for field in ("qty", "stock_qty", "delivered_qty"):
            if field in item:
                item[field] = negative
        rate = _money(item.get("rate", 0))
        for field in ("amount", "base_amount", "net_amount", "base_net_amount"):
            if field in item:
                item[field] = negative * rate

    def prepare_public_fixture(self) -> None:
        customer = str(self.fixture["customer"])
        if not self._exists("Customer", customer):
            self.adapter.create_resource(
                "Customer",
                {
                    "customer_name": customer,
                    "customer_type": "Company",
                    "customer_group": "Commercial",
                    "territory": "All Territories",
                },
            )
        for key in ("affected_item", "unaffected_item", "replacement_item"):
            item = self.fixture[key]
            code = str(item["item_code"])
            if self._exists("Item", code):
                continue
            description = str(item["item_name"])
            if item.get("replaces"):
                description += f"; approved exchange replacement for {item['replaces']}"
            self.adapter.create_resource(
                "Item",
                {
                    "item_code": code,
                    "item_name": str(item["item_name"]),
                    "description": description,
                    "item_group": "Products",
                    "stock_uom": "Nos",
                    "is_stock_item": 1,
                    "valuation_rate": _money(item["unit_price"]),
                    "standard_rate": _money(item["unit_price"]),
                },
            )
        parameter = "Aftermath Customer Return Test"
        if not self._exists("Quality Inspection Parameter", parameter):
            self.adapter.create_resource(
                "Quality Inspection Parameter",
                {
                    "parameter": parameter,
                    "description": "Reproduced customer-reported failure",
                },
            )
        self.adapter.update_resource(
            "Stock Settings",
            "Stock Settings",
            {"allow_to_make_quality_inspection_after_purchase_or_delivery": 1},
        )
        if not self._exists("Webhook", self.PICKUP_WEBHOOK):
            self.adapter.create_resource(
                "Webhook",
                {
                    "name": self.PICKUP_WEBHOOK,
                    "webhook_doctype": "Delivery Note",
                    "webhook_docevent": "on_submit",
                    "enabled": 1,
                    "condition": "doc.is_return == 1",
                    "request_url": "http://remittance:8080/webhooks/events",
                    "request_method": "POST",
                    "request_structure": "JSON",
                    "background_jobs_queue": "short",
                    "webhook_json": (
                        '{"name":"{{ doc.name }}",'
                        '"return_against":"{{ doc.return_against }}",'
                        '"event":"customer_return_pickup"}'
                    ),
                    "webhook_headers": [
                        {"key": "Content-Type", "value": "application/json"}
                    ],
                },
            )

    def _make_invoice(
        self,
        delivery: dict[str, Any],
        item_code: str,
        trace: list[dict[str, Any]],
    ) -> dict[str, Any]:
        row = self._select_item(delivery, item_code)
        template = _payload(
            self.adapter.call_method(
                "erpnext.stock.doctype.delivery_note.delivery_note.make_sales_invoice",
                {
                    "source_name": delivery["name"],
                    "args": {"filtered_children": [row["name"]]},
                },
            )
        )
        invoice = _payload(self.adapter.create_resource("Sales Invoice", template))
        self._trace(trace, "create Sales Invoice", invoice)
        invoice = _payload(
            self.adapter.submit_document("Sales Invoice", invoice["name"])
        )
        self._trace(trace, "submit Sales Invoice", invoice)
        return invoice

    def _shared_payment(
        self,
        affected_invoice: dict[str, Any],
        unaffected_invoice: dict[str, Any],
        transaction_date: date,
    ) -> dict[str, Any]:
        template = _payload(
            self.adapter.call_method(
                "erpnext.accounts.doctype.payment_entry.payment_entry.get_payment_entry",
                {
                    "dt": "Sales Invoice",
                    "dn": affected_invoice["name"],
                    "bank_account": (f"Cash - {self.fixture['company_abbr']}"),
                    "reference_date": transaction_date.isoformat(),
                },
            )
        )
        total = _money(affected_invoice["grand_total"]) + _money(
            unaffected_invoice["grand_total"]
        )
        template["paid_amount"] = total
        template["received_amount"] = total
        template["base_paid_amount"] = total
        template["base_received_amount"] = total
        template["total_allocated_amount"] = total
        template["unallocated_amount"] = 0
        template.setdefault("references", []).append(
            {
                "reference_doctype": "Sales Invoice",
                "reference_name": unaffected_invoice["name"],
                "total_amount": _money(unaffected_invoice["grand_total"]),
                "outstanding_amount": _money(unaffected_invoice["outstanding_amount"]),
                "allocated_amount": _money(unaffected_invoice["outstanding_amount"]),
                "exchange_rate": 1,
            }
        )
        return _payload(self.adapter.create_resource("Payment Entry", template))

    def build(self) -> SalesReturnPrefix:
        self.prepare_public_fixture()
        posting_date = datetime.now(UTC).date()
        delivery_date = posting_date + timedelta(days=3)
        trace: list[dict[str, Any]] = []
        affected = self.fixture["affected_item"]
        unaffected = self.fixture["unaffected_item"]
        replacement = self.fixture["replacement_item"]
        company = str(self.fixture["company"])
        customer = str(self.fixture["customer"])

        stock_seed = _payload(
            self.adapter.create_resource(
                "Stock Entry",
                {
                    "stock_entry_type": "Material Receipt",
                    "company": company,
                    "posting_date": posting_date.isoformat(),
                    "items": [
                        {
                            "item_code": item["item_code"],
                            "qty": item["quantity"],
                            "basic_rate": item["unit_price"],
                            "t_warehouse": self.WAREHOUSE,
                        }
                        for item in (affected, unaffected, replacement)
                    ],
                },
            )
        )
        self._trace(trace, "create inventory seed Stock Entry", stock_seed)
        stock_seed = _payload(
            self.adapter.submit_document("Stock Entry", stock_seed["name"])
        )
        self._trace(trace, "submit inventory seed Stock Entry", stock_seed)

        order = _payload(
            self.adapter.create_resource(
                "Sales Order",
                {
                    "company": company,
                    "customer": customer,
                    "transaction_date": posting_date.isoformat(),
                    "delivery_date": delivery_date.isoformat(),
                    "currency": "USD",
                    "items": [
                        {
                            "item_code": affected["item_code"],
                            "qty": affected["quantity"],
                            "rate": affected["unit_price"],
                            "warehouse": self.WAREHOUSE,
                            "delivery_date": delivery_date.isoformat(),
                        },
                        {
                            "item_code": unaffected["item_code"],
                            "qty": unaffected["quantity"],
                            "rate": unaffected["unit_price"],
                            "warehouse": self.WAREHOUSE,
                            "delivery_date": delivery_date.isoformat(),
                        },
                    ],
                },
            )
        )
        self._trace(trace, "create Sales Order", order)
        order = _payload(self.adapter.submit_document("Sales Order", order["name"]))
        self._trace(trace, "submit Sales Order", order)

        delivery_template = _payload(
            self.adapter.call_method(
                "erpnext.selling.doctype.sales_order.sales_order.make_delivery_note",
                {"source_name": order["name"]},
            )
        )
        delivery = _payload(
            self.adapter.create_resource("Delivery Note", delivery_template)
        )
        self._trace(trace, "create Delivery Note", delivery)
        delivery = _payload(
            self.adapter.submit_document("Delivery Note", delivery["name"])
        )
        self._trace(trace, "submit Delivery Note", delivery)

        inspection = _payload(
            self.adapter.create_resource(
                "Quality Inspection",
                {
                    "inspection_type": "Outgoing",
                    "reference_type": "Delivery Note",
                    "reference_name": delivery["name"],
                    "item_code": affected["item_code"],
                    "sample_size": affected["defective_quantity"],
                    "inspected_by": "Administrator",
                    "readings": [
                        {
                            "specification": "Aftermath Customer Return Test",
                            "min_value": 1,
                            "max_value": 1,
                            "reading_1": "0",
                        }
                    ],
                },
            )
        )
        self._trace(trace, "create return Quality Inspection", inspection)
        inspection = _payload(
            self.adapter.submit_document(
                "Quality Inspection",
                inspection["name"],
            )
        )
        self._trace(trace, "submit return Quality Inspection", inspection)

        affected_invoice = self._make_invoice(
            delivery,
            str(affected["item_code"]),
            trace,
        )
        unaffected_invoice = self._make_invoice(
            delivery,
            str(unaffected["item_code"]),
            trace,
        )
        payment = self._shared_payment(
            affected_invoice,
            unaffected_invoice,
            posting_date,
        )
        self._trace(trace, "create shared customer Payment Entry", payment)
        payment = _payload(
            self.adapter.submit_document("Payment Entry", payment["name"])
        )
        self._trace(trace, "submit shared customer Payment Entry", payment)

        return_template = _payload(
            self.adapter.call_method(
                "erpnext.stock.doctype.delivery_note.delivery_note.make_sales_return",
                {"source_name": delivery["name"]},
            )
        )
        return_item = self._select_item(
            return_template,
            str(affected["item_code"]),
        )
        self._set_return_quantity(
            return_item,
            float(affected["defective_quantity"]),
        )
        return_template["items"] = [return_item]
        sales_return = _payload(
            self.adapter.create_resource("Delivery Note", return_template)
        )
        self._trace(trace, "create partial Sales Return", sales_return)

        credit_template = _payload(
            self.adapter.call_method(
                "erpnext.accounts.doctype.sales_invoice.sales_invoice.make_sales_return",
                {"source_name": affected_invoice["name"]},
            )
        )
        credit_item = self._select_item(
            credit_template,
            str(affected["item_code"]),
        )
        self._set_return_quantity(
            credit_item,
            float(affected["defective_quantity"]),
        )
        credit_template["items"] = [credit_item]
        credit_note = _payload(
            self.adapter.create_resource("Sales Invoice", credit_template)
        )
        self._trace(trace, "create partial customer Credit Note", credit_note)

        replacement_order = _payload(
            self.adapter.create_resource(
                "Sales Order",
                {
                    "company": company,
                    "customer": customer,
                    "transaction_date": posting_date.isoformat(),
                    "delivery_date": delivery_date.isoformat(),
                    "currency": "USD",
                    "items": [
                        {
                            "item_code": replacement["item_code"],
                            "qty": replacement["quantity"],
                            "rate": replacement["unit_price"],
                            "warehouse": self.WAREHOUSE,
                            "delivery_date": delivery_date.isoformat(),
                        }
                    ],
                },
            )
        )
        self._trace(
            trace,
            "create replacement Sales Order",
            replacement_order,
        )
        replacement_order = _payload(
            self.adapter.submit_document(
                "Sales Order",
                replacement_order["name"],
            )
        )
        self._trace(
            trace,
            "submit replacement Sales Order",
            replacement_order,
        )
        replacement_delivery_template = _payload(
            self.adapter.call_method(
                "erpnext.selling.doctype.sales_order.sales_order.make_delivery_note",
                {"source_name": replacement_order["name"]},
            )
        )
        replacement_delivery = _payload(
            self.adapter.create_resource(
                "Delivery Note",
                replacement_delivery_template,
            )
        )
        self._trace(
            trace,
            "create replacement Delivery Note",
            replacement_delivery,
        )

        protected = {
            "original_sales_order": protected_fingerprint(
                "sales_order",
                order,
            ),
            "original_delivery_note": protected_fingerprint(
                "delivery_note",
                delivery,
            ),
            "unaffected_invoice": protected_fingerprint(
                "sales_invoice",
                unaffected_invoice,
            ),
            "shared_payment": json.dumps(
                {
                    "name": payment["name"],
                    "docstatus": payment["docstatus"],
                    "received_amount": payment["received_amount"],
                    "references": sorted(
                        reference["reference_name"]
                        for reference in payment.get("references", [])
                    ),
                },
                sort_keys=True,
                separators=(",", ":"),
            ),
        }
        return SalesReturnPrefix(
            scenario_id=self.scenario_id,
            company=company,
            customer=customer,
            affected_item=str(affected["item_code"]),
            unaffected_item=str(unaffected["item_code"]),
            replacement_item=str(replacement["item_code"]),
            stock_seed=str(stock_seed["name"]),
            original_sales_order=str(order["name"]),
            original_delivery_note=str(delivery["name"]),
            quality_inspection=str(inspection["name"]),
            affected_invoice=str(affected_invoice["name"]),
            unaffected_invoice=str(unaffected_invoice["name"]),
            shared_payment_entry=str(payment["name"]),
            sales_return=str(sales_return["name"]),
            credit_note=str(credit_note["name"]),
            replacement_sales_order=str(replacement_order["name"]),
            replacement_delivery_note=str(replacement_delivery["name"]),
            defective_quantity=float(affected["defective_quantity"]),
            original_quantities={
                str(affected["item_code"]): float(affected["quantity"]),
                str(unaffected["item_code"]): float(unaffected["quantity"]),
            },
            protected_fingerprints=protected,
            trace=tuple(trace),
        )


def ensure_sales_exchange_automation(
    adapter: FrappeHTTPAdapter,
    prefix: dict[str, Any],
) -> dict[str, Any]:
    """Release the approved exchange and reuse any existing active invoice."""
    delivery_name = str(prefix["replacement_delivery_note"])
    delivery = _payload(adapter.get_resource("Delivery Note", delivery_name))
    actions: list[str] = []
    if int(delivery.get("docstatus", 0)) == 0:
        delivery = _payload(adapter.submit_document("Delivery Note", delivery_name))
        actions.append("submit replacement Delivery Note")
    invoices: list[dict[str, Any]] = []
    for summary in adapter.list_resources(
        "Sales Invoice",
        fields=["name"],
        limit=500,
    ).get("data", []):
        invoice = _payload(adapter.get_resource("Sales Invoice", summary["name"]))
        if int(invoice.get("docstatus", 0)) == 2:
            continue
        if any(
            item.get("delivery_note") == delivery_name
            for item in invoice.get("items", [])
        ):
            invoices.append(invoice)
    if not invoices:
        template = _payload(
            adapter.call_method(
                "erpnext.stock.doctype.delivery_note.delivery_note.make_sales_invoice",
                {"source_name": delivery_name},
            )
        )
        invoice = _payload(adapter.create_resource("Sales Invoice", template))
        actions.append("create draft replacement Sales Invoice")
    elif len(invoices) == 1:
        invoice = invoices[0]
    else:
        raise RuntimeError("post-return workflow found duplicate replacement invoices")
    return {
        "ok": True,
        "actions": actions,
        "replacement_delivery_note": delivery["name"],
        "replacement_invoice": invoice["name"],
        "replacement_invoice_docstatus": int(invoice.get("docstatus", 0)),
    }
