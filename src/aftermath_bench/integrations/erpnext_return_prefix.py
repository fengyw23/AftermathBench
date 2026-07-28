from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from .erpnext_evaluator import protected_fingerprint
from .frappe import FrappeHTTPAdapter


def _payload(response: dict[str, Any]) -> dict[str, Any]:
    value = response.get("data", response.get("message", response))
    if not isinstance(value, dict):
        raise RuntimeError(f"expected a document payload, got: {value!r}")
    return value


def _money(value: Any) -> float:
    return float(Decimal(str(value)))


@dataclass(frozen=True)
class PartialReturnPrefix:
    scenario_id: str
    company: str
    supplier: str
    affected_item: str
    unaffected_item: str
    replacement_item: str
    original_purchase_order: str
    original_purchase_receipt: str
    quality_inspection: str
    affected_invoice: str
    unaffected_invoice: str
    shared_payment_entry: str
    purchase_return: str
    debit_note: str
    replacement_purchase_order: str
    replacement_purchase_receipt: str
    defective_quantity: float
    original_quantities: dict[str, float]
    protected_fingerprints: dict[str, str]
    trace: tuple[dict[str, Any], ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            field: getattr(self, field)
            for field in self.__dataclass_fields__
        }


class ERPNextPartialReturnPrefixBuilder:
    WAREHOUSE = "Stores - AL"
    PICKUP_WEBHOOK = "Aftermath Supplier Return Pickup"

    def __init__(
        self,
        adapter: FrappeHTTPAdapter,
        *,
        scenario_id: str,
        fixture: dict[str, Any],
    ):
        self.adapter = adapter
        self.scenario_id = scenario_id
        self.fixture = fixture

    def _exists(self, doctype: str, name: str) -> bool:
        response = self.adapter.list_resources(
            doctype,
            fields=["name"],
            filters={"name": name},
            limit=1,
        )
        return bool(response.get("data", []))

    def _trace(
        self,
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

    def prepare_public_fixture(self) -> None:
        supplier = str(self.fixture["supplier"])
        if not self._exists("Supplier", supplier):
            self.adapter.create_resource(
                "Supplier",
                {
                    "supplier_name": supplier,
                    "supplier_group": "All Supplier Groups",
                    "supplier_type": "Company",
                    "country": "United States",
                },
            )
        for key in ("affected_item", "unaffected_item", "replacement_item"):
            item = self.fixture[key]
            code = str(item["item_code"])
            if self._exists("Item", code):
                continue
            description = str(item["item_name"])
            if item.get("replaces"):
                description += (
                    f"; approved compatible replacement for "
                    f"{item['replaces']}"
                )
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
        parameter = "Aftermath Functional Test"
        if not self._exists("Quality Inspection Parameter", parameter):
            self.adapter.create_resource(
                "Quality Inspection Parameter",
                {
                    "parameter": parameter,
                    "description": "Functional acceptance test",
                },
            )
        self.adapter.update_resource(
            "Stock Settings",
            "Stock Settings",
            {
                "allow_to_make_quality_inspection_after_purchase_or_delivery": 1
            },
        )
        if not self._exists("Webhook", self.PICKUP_WEBHOOK):
            self.adapter.create_resource(
                "Webhook",
                {
                    "name": self.PICKUP_WEBHOOK,
                    "webhook_doctype": "Purchase Receipt",
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
                        '"event":"supplier_return_pickup"}'
                    ),
                    "webhook_headers": [
                        {"key": "Content-Type", "value": "application/json"}
                    ],
                },
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
        for field in ("qty", "stock_qty", "received_qty"):
            if field in item:
                item[field] = negative
        if "rejected_qty" in item:
            item["rejected_qty"] = 0
        rate = _money(item.get("rate", 0))
        for field in ("amount", "base_amount", "net_amount", "base_net_amount"):
            if field in item:
                item[field] = negative * rate

    def _make_invoice(
        self,
        receipt: dict[str, Any],
        item_code: str,
        trace: list[dict[str, Any]],
    ) -> dict[str, Any]:
        row = self._select_item(receipt, item_code)
        template = _payload(self.adapter.call_method(
            "erpnext.stock.doctype.purchase_receipt.purchase_receipt.make_purchase_invoice",
            {
                "source_name": receipt["name"],
                "args": {"filtered_children": [row["name"]]},
            },
        ))
        invoice = _payload(
            self.adapter.create_resource("Purchase Invoice", template)
        )
        self._trace(trace, "create Purchase Invoice", invoice)
        invoice = _payload(
            self.adapter.submit_document("Purchase Invoice", invoice["name"])
        )
        self._trace(trace, "submit Purchase Invoice", invoice)
        return invoice

    def _shared_payment(
        self,
        affected_invoice: dict[str, Any],
        unaffected_invoice: dict[str, Any],
        transaction_date: date,
    ) -> dict[str, Any]:
        template = _payload(self.adapter.call_method(
            "erpnext.accounts.doctype.payment_entry.payment_entry.get_payment_entry",
            {
                "dt": "Purchase Invoice",
                "dn": affected_invoice["name"],
                "bank_account": (
                    f"Cash - {self.fixture['company_abbr']}"
                ),
                "reference_date": transaction_date.isoformat(),
            },
        ))
        total = (
            _money(affected_invoice["grand_total"])
            + _money(unaffected_invoice["grand_total"])
        )
        template["paid_amount"] = total
        template["received_amount"] = total
        template["base_paid_amount"] = total
        template["base_received_amount"] = total
        template["total_allocated_amount"] = total
        template["unallocated_amount"] = 0
        template.setdefault("references", []).append(
            {
                "reference_doctype": "Purchase Invoice",
                "reference_name": unaffected_invoice["name"],
                "total_amount": _money(unaffected_invoice["grand_total"]),
                "outstanding_amount": _money(
                    unaffected_invoice["outstanding_amount"]
                ),
                "allocated_amount": _money(
                    unaffected_invoice["outstanding_amount"]
                ),
                "exchange_rate": 1,
            }
        )
        return _payload(
            self.adapter.create_resource("Payment Entry", template)
        )

    def build(self) -> PartialReturnPrefix:
        self.prepare_public_fixture()
        transaction_date = date.today()
        schedule_date = transaction_date + timedelta(days=14)
        trace: list[dict[str, Any]] = []
        affected = self.fixture["affected_item"]
        unaffected = self.fixture["unaffected_item"]
        replacement = self.fixture["replacement_item"]
        company = str(self.fixture["company"])
        supplier = str(self.fixture["supplier"])

        order = _payload(self.adapter.create_resource(
            "Purchase Order",
            {
                "company": company,
                "supplier": supplier,
                "transaction_date": transaction_date.isoformat(),
                "schedule_date": schedule_date.isoformat(),
                "currency": "USD",
                "items": [
                    {
                        "item_code": affected["item_code"],
                        "qty": affected["quantity"],
                        "rate": affected["unit_price"],
                        "warehouse": self.WAREHOUSE,
                        "schedule_date": schedule_date.isoformat(),
                    },
                    {
                        "item_code": unaffected["item_code"],
                        "qty": unaffected["quantity"],
                        "rate": unaffected["unit_price"],
                        "warehouse": self.WAREHOUSE,
                        "schedule_date": schedule_date.isoformat(),
                    },
                ],
            },
        ))
        self._trace(trace, "create Purchase Order", order)
        order = _payload(
            self.adapter.submit_document("Purchase Order", order["name"])
        )
        self._trace(trace, "submit Purchase Order", order)

        receipt_template = _payload(self.adapter.call_method(
            "erpnext.buying.doctype.purchase_order.purchase_order.make_purchase_receipt",
            {"source_name": order["name"]},
        ))
        receipt = _payload(
            self.adapter.create_resource("Purchase Receipt", receipt_template)
        )
        self._trace(trace, "create Purchase Receipt", receipt)
        receipt = _payload(
            self.adapter.submit_document("Purchase Receipt", receipt["name"])
        )
        self._trace(trace, "submit Purchase Receipt", receipt)

        inspection = _payload(self.adapter.create_resource(
            "Quality Inspection",
            {
                "inspection_type": "Incoming",
                "reference_type": "Purchase Receipt",
                "reference_name": receipt["name"],
                "item_code": affected["item_code"],
                "sample_size": affected["defective_quantity"],
                "inspected_by": "Administrator",
                "readings": [
                    {
                        "specification": "Aftermath Functional Test",
                        "min_value": 1,
                        "max_value": 1,
                        "reading_1": "0",
                    }
                ],
            },
        ))
        self._trace(trace, "create Quality Inspection", inspection)
        inspection = _payload(
            self.adapter.submit_document(
                "Quality Inspection",
                inspection["name"],
            )
        )
        self._trace(trace, "submit Quality Inspection", inspection)

        affected_invoice = self._make_invoice(
            receipt,
            str(affected["item_code"]),
            trace,
        )
        unaffected_invoice = self._make_invoice(
            receipt,
            str(unaffected["item_code"]),
            trace,
        )

        payment = self._shared_payment(
            affected_invoice,
            unaffected_invoice,
            transaction_date,
        )
        self._trace(trace, "create shared Payment Entry", payment)
        payment = _payload(
            self.adapter.submit_document("Payment Entry", payment["name"])
        )
        self._trace(trace, "submit shared Payment Entry", payment)

        return_template = _payload(self.adapter.call_method(
            "erpnext.stock.doctype.purchase_receipt.purchase_receipt.make_purchase_return",
            {"source_name": receipt["name"]},
        ))
        return_item = self._select_item(
            return_template,
            str(affected["item_code"]),
        )
        self._set_return_quantity(
            return_item,
            float(affected["defective_quantity"]),
        )
        return_template["items"] = [return_item]
        purchase_return = _payload(
            self.adapter.create_resource("Purchase Receipt", return_template)
        )
        self._trace(trace, "create partial Purchase Return", purchase_return)

        debit_template = _payload(self.adapter.call_method(
            "erpnext.accounts.doctype.purchase_invoice.purchase_invoice.make_debit_note",
            {"source_name": affected_invoice["name"]},
        ))
        debit_item = self._select_item(
            debit_template,
            str(affected["item_code"]),
        )
        self._set_return_quantity(
            debit_item,
            float(affected["defective_quantity"]),
        )
        debit_template["items"] = [debit_item]
        debit_note = _payload(
            self.adapter.create_resource("Purchase Invoice", debit_template)
        )
        self._trace(trace, "create partial Debit Note", debit_note)

        replacement_order = _payload(self.adapter.create_resource(
            "Purchase Order",
            {
                "company": company,
                "supplier": supplier,
                "transaction_date": transaction_date.isoformat(),
                "schedule_date": schedule_date.isoformat(),
                "currency": "USD",
                "items": [
                    {
                        "item_code": replacement["item_code"],
                        "qty": replacement["quantity"],
                        "rate": replacement["unit_price"],
                        "warehouse": self.WAREHOUSE,
                        "schedule_date": schedule_date.isoformat(),
                    }
                ],
            },
        ))
        self._trace(trace, "create replacement Purchase Order", replacement_order)
        replacement_order = _payload(
            self.adapter.submit_document(
                "Purchase Order",
                replacement_order["name"],
            )
        )
        self._trace(trace, "submit replacement Purchase Order", replacement_order)
        replacement_receipt_template = _payload(self.adapter.call_method(
            "erpnext.buying.doctype.purchase_order.purchase_order.make_purchase_receipt",
            {"source_name": replacement_order["name"]},
        ))
        replacement_receipt = _payload(
            self.adapter.create_resource(
                "Purchase Receipt",
                replacement_receipt_template,
            )
        )
        self._trace(
            trace,
            "create replacement Purchase Receipt",
            replacement_receipt,
        )

        protected = {
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
                    "name": payment["name"],
                    "docstatus": payment["docstatus"],
                    "paid_amount": payment["paid_amount"],
                    "references": sorted(
                        reference["reference_name"]
                        for reference in payment.get("references", [])
                    ),
                },
                sort_keys=True,
                separators=(",", ":"),
            ),
        }
        return PartialReturnPrefix(
            scenario_id=self.scenario_id,
            company=company,
            supplier=supplier,
            affected_item=str(affected["item_code"]),
            unaffected_item=str(unaffected["item_code"]),
            replacement_item=str(replacement["item_code"]),
            original_purchase_order=str(order["name"]),
            original_purchase_receipt=str(receipt["name"]),
            quality_inspection=str(inspection["name"]),
            affected_invoice=str(affected_invoice["name"]),
            unaffected_invoice=str(unaffected_invoice["name"]),
            shared_payment_entry=str(payment["name"]),
            purchase_return=str(purchase_return["name"]),
            debit_note=str(debit_note["name"]),
            replacement_purchase_order=str(replacement_order["name"]),
            replacement_purchase_receipt=str(replacement_receipt["name"]),
            defective_quantity=float(affected["defective_quantity"]),
            original_quantities={
                str(affected["item_code"]): float(affected["quantity"]),
                str(unaffected["item_code"]): float(unaffected["quantity"]),
            },
            protected_fingerprints=protected,
            trace=tuple(trace),
        )
