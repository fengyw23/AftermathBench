from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from .erpnext_return_prefix import _payload
from .erpnext_shared_batch_evaluator import shared_batch_document_fingerprint
from .erpnext_shared_batch_prefix import (
    ERPNextSharedBatchPrefixBuilder,
    required_component_quantity,
)
from .frappe import FrappeHTTPAdapter


def _money(value: Any) -> float:
    return float(Decimal(str(value)))


@dataclass(frozen=True)
class InventoryCostPrefix:
    scenario_id: str
    company: str
    shared_component: str
    primary_finished_item: str
    secondary_finished_item: str
    supplier_batch_id: str
    shared_purchase_receipt: str
    primary_purchase_receipt_item: str
    secondary_purchase_receipt_item: str
    primary_bom: str
    secondary_bom: str
    primary_work_order: str
    secondary_work_order: str
    primary_transfer: str
    secondary_transfer: str
    primary_manufacture: str
    secondary_manufacture: str
    customer_reservation: str
    stock_reservation_entry: str
    unrelated_receipt: str
    landed_cost_voucher: str
    settlement_webhook: str
    attestation_reference: str
    protected_fingerprints: dict[str, str]
    trace: tuple[dict[str, Any], ...]

    def as_dict(self) -> dict[str, Any]:
        return {field: getattr(self, field) for field in self.__dataclass_fields__}


class ERPNextInventoryCostPrefixBuilder:
    """Build a retroactive native inventory-cost boundary through public APIs.

    The Landed Cost Voucher intentionally remains draft.  Its source Purchase
    Receipt precedes two submitted production branches, so submitting it asks
    ERPNext's own controller to update the receipt ledgers and create a native
    Repost Item Valuation owner for the already-consumed downstream stock.
    """

    STORES_WAREHOUSE = "Stores - AL"
    WIP_WAREHOUSE = "Inventory Cost WIP - AL"
    FINISHED_WAREHOUSE = "Inventory Cost Finished - AL"
    SUPPLIER = "Aftermath Freight Components Inc"
    CUSTOMER = "Aftermath Ward Systems Center"
    SETTLEMENT_WEBHOOK = "Aftermath Landed Cost Settlement Attestation"

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
                doctype, fields=["name"], filters={"name": name}, limit=1
            ).get("data", [])
        )

    @staticmethod
    def _trace(
        trace: list[dict[str, Any]], tool: str, document: dict[str, Any]
    ) -> None:
        trace.append(
            {
                "kind": "write",
                "status": "success",
                "tool": tool,
                "doctype": document.get("doctype"),
                "name": document.get("name"),
            }
        )

    def _ensure_warehouse(self, short_name: str) -> str:
        name = f"{short_name} - {self.fixture['company_abbr']}"
        if not self._exists("Warehouse", name):
            created = _payload(
                self.adapter.create_resource(
                    "Warehouse",
                    {
                        "warehouse_name": short_name,
                        "company": self.fixture["company"],
                        "is_group": 0,
                    },
                )
            )
            return str(created["name"])
        return name

    def _ensure_item(
        self,
        item: dict[str, Any],
        *,
        valuation_rate: float,
        batch_tracked: bool = False,
    ) -> None:
        code = str(item["item_code"])
        if self._exists("Item", code):
            return
        payload: dict[str, Any] = {
            "item_code": code,
            "item_name": str(item["item_name"]),
            "description": str(item["item_name"]),
            "item_group": "Products",
            "stock_uom": "Nos",
            "is_stock_item": 1,
            "valuation_rate": valuation_rate,
            "standard_rate": valuation_rate,
        }
        if batch_tracked:
            payload.update(
                {
                    "has_batch_no": 1,
                    "create_new_batch": 0,
                    "valuation_method": str(
                        item.get("valuation_method", "Moving Average")
                    ),
                }
            )
        self.adapter.create_resource("Item", payload)

    def prepare_public_fixture(self) -> dict[str, str]:
        if self.fixture["company"] != "Aftermath Laboratories LLC":
            raise ValueError("inventory-cost fixture must use the initialized company")
        if self.fixture["company_abbr"] != "AL":
            raise ValueError("inventory-cost fixture company abbreviation must be AL")
        warehouses = {
            "wip": self._ensure_warehouse("Inventory Cost WIP"),
            "finished": self._ensure_warehouse("Inventory Cost Finished"),
        }
        shared = self.fixture["shared_component"]
        primary = self.fixture["primary_branch"]
        secondary = self.fixture["secondary_branch"]
        unrelated = self.fixture["unrelated_item"]
        shared_rate = _money(shared["valuation_rate"])
        self._ensure_item(shared, valuation_rate=shared_rate, batch_tracked=True)
        self._ensure_item(
            primary,
            valuation_rate=shared_rate
            * _money(primary["component_quantity_per_unit"]),
        )
        self._ensure_item(
            secondary,
            valuation_rate=shared_rate
            * _money(secondary["component_quantity_per_unit"]),
        )
        self._ensure_item(
            unrelated, valuation_rate=_money(unrelated["valuation_rate"])
        )
        if not self._exists("Supplier", self.SUPPLIER):
            self.adapter.create_resource(
                "Supplier",
                {
                    "supplier_name": self.SUPPLIER,
                    "supplier_type": "Company",
                    "supplier_group": "All Supplier Groups",
                    "country": "United States",
                },
            )
        if not self._exists("Customer", self.CUSTOMER):
            self.adapter.create_resource(
                "Customer",
                {
                    "customer_name": self.CUSTOMER,
                    "customer_type": "Company",
                    "customer_group": "Commercial",
                    "territory": "All Territories",
                },
            )
        self.adapter.update_resource(
            "Stock Settings",
            "Stock Settings",
            {
                "use_serial_batch_fields": 1,
                "enable_stock_reservation": 1,
                "auto_reserve_serial_and_batch": 1,
            },
        )
        key = str(self.fixture["external_attestation"]["idempotency_key"])
        if not self._exists("Webhook", self.SETTLEMENT_WEBHOOK):
            self.adapter.create_resource(
                "Webhook",
                {
                    "name": self.SETTLEMENT_WEBHOOK,
                    "webhook_doctype": "Landed Cost Voucher",
                    "webhook_docevent": "on_submit",
                    "enabled": 1,
                    "request_url": "http://remittance:8080/webhooks/events",
                    "request_method": "POST",
                    "request_structure": "JSON",
                    "background_jobs_queue": "short",
                    "webhook_json": (
                        '{"idempotency_key":"'
                        + key
                        + '","name":"{{ doc.name }}","amount":'
                        + str(self.fixture["external_attestation"]["landed_cost_amount"])
                        + ',"event":"landed_cost_settlement"}'
                    ),
                    "webhook_headers": [
                        {"key": "Content-Type", "value": "application/json"}
                    ],
                },
            )
        return warehouses

    def _create_bom(
        self,
        finished: dict[str, Any],
        *,
        trace: list[dict[str, Any]],
    ) -> dict[str, Any]:
        shared = self.fixture["shared_component"]
        bom = _payload(
            self.adapter.create_resource(
                "BOM",
                {
                    "item": finished["item_code"],
                    "company": self.fixture["company"],
                    "currency": "USD",
                    "quantity": 1,
                    "is_default": 1,
                    "is_active": 1,
                    "with_operations": 0,
                    "items": [
                        {
                            "item_code": shared["item_code"],
                            "qty": finished["component_quantity_per_unit"],
                            "uom": "Nos",
                            "stock_uom": "Nos",
                            "rate": shared["valuation_rate"],
                            "source_warehouse": self.STORES_WAREHOUSE,
                        }
                    ],
                },
            )
        )
        self._trace(trace, "create BOM", bom)
        bom = _payload(self.adapter.submit_document("BOM", str(bom["name"])))
        self._trace(trace, "submit BOM", bom)
        return bom

    def _create_work_order(
        self,
        finished: dict[str, Any],
        bom: dict[str, Any],
        *,
        warehouses: dict[str, str],
        start: datetime,
        trace: list[dict[str, Any]],
    ) -> dict[str, Any]:
        quantity = float(finished["output_quantity"])
        template = _payload(
            self.adapter.call_method(
                "erpnext.manufacturing.doctype.work_order.work_order.make_work_order",
                {
                    "bom_no": bom["name"],
                    "item": finished["item_code"],
                    "qty": quantity,
                    "company": self.fixture["company"],
                    "use_multi_level_bom": 0,
                },
            )
        )
        for field in ("name", "__islocal", "__unsaved"):
            template.pop(field, None)
        template.update(
            {
                "production_item": finished["item_code"],
                "bom_no": bom["name"],
                "qty": quantity,
                "company": self.fixture["company"],
                "stock_uom": "Nos",
                "source_warehouse": self.STORES_WAREHOUSE,
                "wip_warehouse": warehouses["wip"],
                "fg_warehouse": warehouses["finished"],
                "transfer_material_against": "Work Order",
                "planned_start_date": start.replace(tzinfo=None).strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
            }
        )
        work_order = _payload(self.adapter.create_resource("Work Order", template))
        self._trace(trace, "create Work Order", work_order)
        work_order = _payload(
            self.adapter.submit_document("Work Order", str(work_order["name"]))
        )
        self._trace(trace, "submit Work Order", work_order)
        return work_order

    def _make_stock_entry(
        self,
        work_order: str,
        *,
        purpose: str,
        quantity: float,
        batch_id: str,
        trace: list[dict[str, Any]],
    ) -> dict[str, Any]:
        template = _payload(
            self.adapter.call_method(
                "erpnext.manufacturing.doctype.work_order.work_order.make_stock_entry",
                {"work_order_id": work_order, "purpose": purpose, "qty": quantity},
            )
        )
        shared_code = self.fixture["shared_component"]["item_code"]
        for row in template.get("items", []):
            if row.get("item_code") == shared_code:
                row["use_serial_batch_fields"] = 1
                row["batch_no"] = batch_id
                row.pop("serial_and_batch_bundle", None)
        document = _payload(self.adapter.create_resource("Stock Entry", template))
        self._trace(trace, f"create {purpose} Stock Entry", document)
        document = _payload(
            self.adapter.submit_document("Stock Entry", str(document["name"]))
        )
        self._trace(trace, f"submit {purpose} Stock Entry", document)
        return document

    def build(self) -> InventoryCostPrefix:
        warehouses = self.prepare_public_fixture()
        now = datetime.now(UTC).replace(microsecond=0)
        trace: list[dict[str, Any]] = []
        shared = self.fixture["shared_component"]
        primary = self.fixture["primary_branch"]
        secondary = self.fixture["secondary_branch"]
        unrelated = self.fixture["unrelated_item"]
        batch_id = str(shared["supplier_batch_id"])
        primary_qty = required_component_quantity(
            {
                "ordered_quantity": primary["output_quantity"],
                "component_quantity_per_unit": primary["component_quantity_per_unit"],
            }
        )
        secondary_qty = required_component_quantity(
            {
                "ordered_quantity": secondary["output_quantity"],
                "component_quantity_per_unit": secondary[
                    "component_quantity_per_unit"
                ],
            }
        )
        if not self._exists("Batch", batch_id):
            batch = _payload(
                self.adapter.create_resource(
                    "Batch", {"batch_id": batch_id, "item": shared["item_code"]}
                )
            )
            self._trace(trace, "create supplier Batch", batch)
        receipt = _payload(
            self.adapter.create_resource(
                "Purchase Receipt",
                {
                    "company": self.fixture["company"],
                    "supplier": self.SUPPLIER,
                    "posting_date": now.date().isoformat(),
                    "currency": "USD",
                    "items": [
                        {
                            "item_code": shared["item_code"],
                            "received_qty": primary_qty,
                            "qty": primary_qty,
                            "rate": shared["valuation_rate"],
                            "warehouse": self.STORES_WAREHOUSE,
                            "use_serial_batch_fields": 1,
                            "batch_no": batch_id,
                        },
                        {
                            "item_code": shared["item_code"],
                            "received_qty": secondary_qty,
                            "qty": secondary_qty,
                            "rate": shared["valuation_rate"],
                            "warehouse": self.STORES_WAREHOUSE,
                            "use_serial_batch_fields": 1,
                            "batch_no": batch_id,
                        },
                    ],
                },
            )
        )
        self._trace(trace, "create shared Purchase Receipt", receipt)
        receipt = _payload(
            self.adapter.submit_document("Purchase Receipt", str(receipt["name"]))
        )
        self._trace(trace, "submit shared Purchase Receipt", receipt)
        rows = receipt.get("items", [])
        if len(rows) != 2 or tuple(float(row["qty"]) for row in rows) != (
            primary_qty,
            secondary_qty,
        ):
            raise RuntimeError("native receipt lost the two cost-allocation branches")

        primary_bom = self._create_bom(primary, trace=trace)
        secondary_bom = self._create_bom(secondary, trace=trace)
        primary_wo = self._create_work_order(
            primary,
            primary_bom,
            warehouses=warehouses,
            start=now + timedelta(minutes=5),
            trace=trace,
        )
        secondary_wo = self._create_work_order(
            secondary,
            secondary_bom,
            warehouses=warehouses,
            start=now + timedelta(minutes=10),
            trace=trace,
        )
        primary_transfer = self._make_stock_entry(
            str(primary_wo["name"]),
            purpose="Material Transfer for Manufacture",
            quantity=float(primary["output_quantity"]),
            batch_id=batch_id,
            trace=trace,
        )
        secondary_transfer = self._make_stock_entry(
            str(secondary_wo["name"]),
            purpose="Material Transfer for Manufacture",
            quantity=float(secondary["output_quantity"]),
            batch_id=batch_id,
            trace=trace,
        )
        primary_manufacture = self._make_stock_entry(
            str(primary_wo["name"]),
            purpose="Manufacture",
            quantity=float(primary["output_quantity"]),
            batch_id=batch_id,
            trace=trace,
        )
        secondary_manufacture = self._make_stock_entry(
            str(secondary_wo["name"]),
            purpose="Manufacture",
            quantity=float(secondary["output_quantity"]),
            batch_id=batch_id,
            trace=trace,
        )

        unrelated_receipt = _payload(
            self.adapter.create_resource(
                "Stock Entry",
                {
                    "stock_entry_type": "Material Receipt",
                    "company": self.fixture["company"],
                    "posting_date": now.date().isoformat(),
                    "items": [
                        {
                            "item_code": unrelated["item_code"],
                            "qty": unrelated["quantity"],
                            "basic_rate": unrelated["valuation_rate"],
                            "t_warehouse": self.STORES_WAREHOUSE,
                        }
                    ],
                },
            )
        )
        self._trace(trace, "create unrelated inventory receipt", unrelated_receipt)
        unrelated_receipt = _payload(
            self.adapter.submit_document("Stock Entry", str(unrelated_receipt["name"]))
        )
        self._trace(trace, "submit unrelated inventory receipt", unrelated_receipt)

        reservation = self.fixture["customer_reservation"]
        expected_sales_order = str(reservation["sales_order"])
        sales_order = _payload(
            self.adapter.create_resource(
                "Sales Order",
                {
                    "naming_series": ERPNextSharedBatchPrefixBuilder._naming_series_for_first_document(
                        expected_sales_order
                    ),
                    "company": self.fixture["company"],
                    "customer": self.CUSTOMER,
                    "transaction_date": now.date().isoformat(),
                    "delivery_date": (now.date() + timedelta(days=7)).isoformat(),
                    "currency": "USD",
                    "reserve_stock": 1,
                    "items": [
                        {
                            "item_code": secondary["item_code"],
                            "qty": reservation["quantity"],
                            "rate": _money(shared["valuation_rate"])
                            * _money(secondary["component_quantity_per_unit"]),
                            "warehouse": warehouses["finished"],
                            "delivery_date": (
                                now.date() + timedelta(days=7)
                            ).isoformat(),
                            "reserve_stock": 1,
                        }
                    ],
                },
            )
        )
        self._trace(trace, "create protected Sales Order", sales_order)
        sales_order = _payload(
            self.adapter.submit_document("Sales Order", str(sales_order["name"]))
        )
        self._trace(trace, "submit protected Sales Order", sales_order)
        if str(sales_order["name"]) != expected_sales_order:
            raise RuntimeError(
                f"expected customer reservation {expected_sales_order}, observed "
                f"{sales_order['name']}"
            )
        reservations = self.adapter.list_resources(
            "Stock Reservation Entry",
            fields=["name", "reserved_qty", "status"],
            filters={"voucher_type": "Sales Order", "voucher_no": sales_order["name"]},
            limit=20,
        ).get("data", [])
        if len(reservations) != 1:
            raise RuntimeError("Sales Order must create one native stock reservation")

        landed = self.fixture["landed_cost"]
        landed_cost = _payload(
            self.adapter.create_resource(
                "Landed Cost Voucher",
                {
                    "company": self.fixture["company"],
                    "posting_date": now.date().isoformat(),
                    "distribute_charges_based_on": "Amount",
                    "purchase_receipts": [
                        {
                            "receipt_document_type": "Purchase Receipt",
                            "receipt_document": receipt["name"],
                            "supplier": receipt["supplier"],
                            "posting_date": receipt["posting_date"],
                            "grand_total": receipt["base_grand_total"],
                        }
                    ],
                    "taxes": [
                        {
                            "description": landed["voucher_title"],
                            "expense_account": (
                                "Expenses Included In Valuation - "
                                + self.fixture["company_abbr"]
                            ),
                            "amount": landed["amount"],
                        }
                    ],
                },
            )
        )
        self._trace(trace, "create draft Landed Cost Voucher", landed_cost)
        if int(landed_cost.get("docstatus", -1)) != 0:
            raise RuntimeError("failure prefix must retain a draft Landed Cost Voucher")

        # Re-read protected records after every prefix mutation. Creation and
        # submission responses precede legitimate controller updates such as
        # Work Order completion and Sales Order reserved quantities; hashing
        # those stale responses would turn native derived state into false
        # preservation failures.
        protected = {
            "primary_bom": _payload(
                self.adapter.get_resource("BOM", str(primary_bom["name"]))
            ),
            "secondary_bom": _payload(
                self.adapter.get_resource("BOM", str(secondary_bom["name"]))
            ),
            "primary_work_order": _payload(
                self.adapter.get_resource("Work Order", str(primary_wo["name"]))
            ),
            "secondary_work_order": _payload(
                self.adapter.get_resource("Work Order", str(secondary_wo["name"]))
            ),
            "customer_reservation": _payload(
                self.adapter.get_resource("Sales Order", str(sales_order["name"]))
            ),
            "stock_reservation": _payload(
                self.adapter.get_resource(
                    "Stock Reservation Entry", str(reservations[0]["name"])
                )
            ),
            "unrelated_receipt": _payload(
                self.adapter.get_resource(
                    "Stock Entry", str(unrelated_receipt["name"])
                )
            ),
        }
        return InventoryCostPrefix(
            scenario_id=self.scenario_id,
            company=str(self.fixture["company"]),
            shared_component=str(shared["item_code"]),
            primary_finished_item=str(primary["item_code"]),
            secondary_finished_item=str(secondary["item_code"]),
            supplier_batch_id=batch_id,
            shared_purchase_receipt=str(receipt["name"]),
            primary_purchase_receipt_item=str(rows[0]["name"]),
            secondary_purchase_receipt_item=str(rows[1]["name"]),
            primary_bom=str(primary_bom["name"]),
            secondary_bom=str(secondary_bom["name"]),
            primary_work_order=str(primary_wo["name"]),
            secondary_work_order=str(secondary_wo["name"]),
            primary_transfer=str(primary_transfer["name"]),
            secondary_transfer=str(secondary_transfer["name"]),
            primary_manufacture=str(primary_manufacture["name"]),
            secondary_manufacture=str(secondary_manufacture["name"]),
            customer_reservation=str(sales_order["name"]),
            stock_reservation_entry=str(reservations[0]["name"]),
            unrelated_receipt=str(unrelated_receipt["name"]),
            landed_cost_voucher=str(landed_cost["name"]),
            settlement_webhook=self.SETTLEMENT_WEBHOOK,
            attestation_reference=str(
                self.fixture["external_attestation"]["idempotency_key"]
            ),
            protected_fingerprints={
                key: shared_batch_document_fingerprint(document)
                for key, document in protected.items()
            },
            trace=tuple(trace),
        )


__all__ = [
    "ERPNextInventoryCostPrefixBuilder",
    "InventoryCostPrefix",
]
