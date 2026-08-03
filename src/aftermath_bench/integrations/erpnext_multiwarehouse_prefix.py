from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from .erpnext_multiwarehouse_evaluator import multiwarehouse_document_fingerprint
from .erpnext_return_prefix import _payload
from .frappe import FrappeHTTPAdapter


def _money(value: Any) -> float:
    return float(Decimal(str(value)))


@dataclass(frozen=True)
class MultiwarehousePrefix:
    scenario_id: str
    company: str
    transfer_item: str
    transfer_quantity: float
    batch_id: str
    protected_item: str
    protected_stock_balance: float
    source_warehouse: str
    transit_warehouse: str
    destination_warehouse: str
    protected_warehouse: str
    stock_seed: str
    material_request: str
    outgoing_stock_entry: str
    second_leg_stock_entry: str
    clinic_sales_order: str
    clinic_sales_order_item: str
    clinic_reserved_quantity: float
    protected_sales_order: str
    protected_pick_list: str
    protected_reservation: str
    protected_fingerprints: dict[str, str]
    trace: tuple[dict[str, Any], ...]

    def as_dict(self) -> dict[str, Any]:
        return {field: getattr(self, field) for field in self.__dataclass_fields__}


class ERPNextMultiwarehousePrefixBuilder:
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

    def _warehouse(self, short_name: str) -> str:
        full_name = f"{short_name} - {self.fixture['company_abbr']}"
        if not self._exists("Warehouse", full_name):
            document = _payload(
                self.adapter.create_resource(
                    "Warehouse",
                    {
                        "warehouse_name": short_name,
                        "company": self.fixture["company"],
                        "is_group": 0,
                    },
                )
            )
            return str(document["name"])
        return full_name

    def _ensure_item(self, item: dict[str, Any], *, batch_tracked: bool) -> None:
        code = str(item["item_code"])
        if self._exists("Item", code):
            return
        payload = {
            "item_code": code,
            "item_name": item["item_name"],
            "description": item["item_name"],
            "item_group": "Products",
            "stock_uom": "Nos",
            "is_stock_item": 1,
            "is_sales_item": 1,
            "valuation_rate": _money(item["valuation_rate"]),
            "standard_rate": _money(item["valuation_rate"]),
        }
        if batch_tracked:
            payload.update({"has_batch_no": 1, "create_new_batch": 0})
        self.adapter.create_resource("Item", payload)

    def _ensure_customer(self, customer: str) -> None:
        if self._exists("Customer", customer):
            return
        self.adapter.create_resource(
            "Customer",
            {
                "customer_name": customer,
                "customer_type": "Company",
                "customer_group": "Commercial",
                "territory": "All Territories",
            },
        )

    def prepare_public_fixture(self) -> dict[str, str]:
        warehouses = {
            key: self._warehouse(str(self.fixture[key]))
            for key in (
                "source_warehouse",
                "transit_warehouse",
                "destination_warehouse",
                "protected_warehouse",
            )
        }
        self._ensure_item(self.fixture["transfer_item"], batch_tracked=True)
        self._ensure_item(self.fixture["unrelated_item"], batch_tracked=False)
        self._ensure_customer(str(self.fixture["deployment_customer"]))
        self._ensure_customer(str(self.fixture["protected_customer"]))
        self.adapter.update_resource(
            "Stock Settings",
            "Stock Settings",
            {
                "allow_negative_stock": 0,
                "enable_stock_reservation": 1,
                "auto_reserve_serial_and_batch": 1,
                "pick_serial_and_batch_based_on": "FIFO",
                "use_serial_batch_fields": 1,
            },
        )
        batch_id = str(self.fixture["transfer_item"]["batch_id"])
        if not self._exists("Batch", batch_id):
            self.adapter.create_resource(
                "Batch",
                {
                    "batch_id": batch_id,
                    "item": self.fixture["transfer_item"]["item_code"],
                    "description": "Traceable clinic gateway transfer batch",
                },
            )
        return warehouses

    def _sales_order(
        self,
        *,
        customer: str,
        item: dict[str, Any],
        quantity: float,
        warehouse: str,
        delivery_date: str,
        trace: list[dict[str, Any]],
    ) -> dict[str, Any]:
        order = _payload(
            self.adapter.create_resource(
                "Sales Order",
                {
                    "company": self.fixture["company"],
                    "customer": customer,
                    "transaction_date": datetime.now(UTC).date().isoformat(),
                    "delivery_date": delivery_date,
                    "currency": "USD",
                    "reserve_stock": 0,
                    "items": [
                        {
                            "item_code": item["item_code"],
                            "qty": quantity,
                            "rate": item["valuation_rate"],
                            "warehouse": warehouse,
                            "delivery_date": delivery_date,
                            "reserve_stock": 1,
                        }
                    ],
                },
            )
        )
        self._trace(trace, "create Sales Order", order)
        order = _payload(self.adapter.submit_document("Sales Order", order["name"]))
        self._trace(trace, "submit Sales Order", order)
        return order

    def build(self) -> MultiwarehousePrefix:
        warehouses = self.prepare_public_fixture()
        now = datetime.now(UTC).replace(microsecond=0)
        schedule_date = (now.date() + timedelta(days=2)).isoformat()
        trace: list[dict[str, Any]] = []
        transfer_item = self.fixture["transfer_item"]
        protected_item = self.fixture["unrelated_item"]
        quantity = float(transfer_item["quantity"])
        protected_quantity = float(protected_item["quantity"])
        batch_id = str(transfer_item["batch_id"])

        seed = _payload(
            self.adapter.create_resource(
                "Stock Entry",
                {
                    "stock_entry_type": "Material Receipt",
                    "company": self.fixture["company"],
                    "posting_date": now.date().isoformat(),
                    "items": [
                        {
                            "item_code": transfer_item["item_code"],
                            "qty": quantity,
                            "basic_rate": transfer_item["valuation_rate"],
                            "t_warehouse": warehouses["source_warehouse"],
                            "batch_no": batch_id,
                        },
                        {
                            "item_code": protected_item["item_code"],
                            "qty": protected_quantity,
                            "basic_rate": protected_item["valuation_rate"],
                            "t_warehouse": warehouses["protected_warehouse"],
                        },
                    ],
                },
            )
        )
        self._trace(trace, "create inventory seed Stock Entry", seed)
        seed = _payload(self.adapter.submit_document("Stock Entry", seed["name"]))
        self._trace(trace, "submit inventory seed Stock Entry", seed)

        request = _payload(
            self.adapter.create_resource(
                "Material Request",
                {
                    "company": self.fixture["company"],
                    "material_request_type": "Material Transfer",
                    "schedule_date": schedule_date,
                    "set_from_warehouse": warehouses["source_warehouse"],
                    "set_warehouse": warehouses["destination_warehouse"],
                    "items": [
                        {
                            "item_code": transfer_item["item_code"],
                            "qty": quantity,
                            "from_warehouse": warehouses["source_warehouse"],
                            "warehouse": warehouses["destination_warehouse"],
                            "schedule_date": schedule_date,
                        }
                    ],
                },
            )
        )
        self._trace(trace, "create Material Request", request)
        request = _payload(
            self.adapter.submit_document("Material Request", request["name"])
        )
        self._trace(trace, "submit Material Request", request)

        outgoing_template = _payload(
            self.adapter.call_method(
                "erpnext.stock.doctype.material_request.material_request.make_stock_entry",
                {"source_name": request["name"]},
            )
        )
        outgoing_template.update(
            {
                "add_to_transit": 1,
                "from_warehouse": warehouses["source_warehouse"],
                "to_warehouse": warehouses["transit_warehouse"],
            }
        )
        for item in outgoing_template.get("items", []):
            item["t_warehouse"] = warehouses["transit_warehouse"]
            item["batch_no"] = batch_id
        outgoing = _payload(
            self.adapter.create_resource("Stock Entry", outgoing_template)
        )
        self._trace(trace, "create first-leg Stock Entry", outgoing)
        outgoing = _payload(
            self.adapter.submit_document("Stock Entry", outgoing["name"])
        )
        self._trace(trace, "submit first-leg Stock Entry", outgoing)

        incoming_template = _payload(
            self.adapter.call_method(
                "erpnext.stock.doctype.stock_entry.stock_entry.make_stock_in_entry",
                {"source_name": outgoing["name"]},
            )
        )
        incoming_template["to_warehouse"] = warehouses["destination_warehouse"]
        for item in incoming_template.get("items", []):
            item["t_warehouse"] = warehouses["destination_warehouse"]
            item["batch_no"] = batch_id
        incoming = _payload(
            self.adapter.create_resource("Stock Entry", incoming_template)
        )
        self._trace(trace, "create prepared second-leg Stock Entry", incoming)

        clinic_order = self._sales_order(
            customer=str(self.fixture["deployment_customer"]),
            item=transfer_item,
            quantity=float(self.fixture["clinic_reserved_quantity"]),
            warehouse=warehouses["destination_warehouse"],
            delivery_date=schedule_date,
            trace=trace,
        )
        protected_order = self._sales_order(
            customer=str(self.fixture["protected_customer"]),
            item=protected_item,
            quantity=float(protected_item["reserved_quantity"]),
            warehouse=warehouses["protected_warehouse"],
            delivery_date=schedule_date,
            trace=trace,
        )
        protected_pick_template = _payload(
            self.adapter.call_method(
                "erpnext.selling.doctype.sales_order.sales_order.create_pick_list",
                {"source_name": protected_order["name"]},
            )
        )
        protected_pick = _payload(
            self.adapter.create_resource("Pick List", protected_pick_template)
        )
        self._trace(trace, "create protected Pick List", protected_pick)
        protected_pick = _payload(
            self.adapter.submit_document("Pick List", protected_pick["name"])
        )
        self._trace(trace, "submit protected Pick List", protected_pick)

        protected_order_item = protected_order["items"][0]
        protected_reservation = _payload(
            self.adapter.create_resource(
                "Stock Reservation Entry",
                {
                    "item_code": protected_item["item_code"],
                    "warehouse": warehouses["protected_warehouse"],
                    "voucher_type": "Sales Order",
                    "voucher_no": protected_order["name"],
                    "voucher_detail_no": protected_order_item["name"],
                    "available_qty": protected_quantity,
                    "voucher_qty": protected_item["reserved_quantity"],
                    "stock_uom": "Nos",
                    "reserved_qty": protected_item["reserved_quantity"],
                    "delivered_qty": 0,
                    "company": self.fixture["company"],
                },
            )
        )
        self._trace(trace, "create protected Stock Reservation Entry", protected_reservation)
        protected_reservation = _payload(
            self.adapter.submit_document(
                "Stock Reservation Entry", protected_reservation["name"]
            )
        )
        self._trace(trace, "submit protected Stock Reservation Entry", protected_reservation)

        protected_bin_rows = self.adapter.list_resources(
            "Bin",
            fields=["name", "item_code", "warehouse", "actual_qty"],
            filters={
                "item_code": protected_item["item_code"],
                "warehouse": warehouses["protected_warehouse"],
            },
            limit=10,
        ).get("data", [])
        if len(protected_bin_rows) != 1:
            raise RuntimeError("expected exactly one protected warehouse Bin")
        outgoing = _payload(
            self.adapter.get_resource("Stock Entry", str(outgoing["name"]))
        )

        return MultiwarehousePrefix(
            scenario_id=self.scenario_id,
            company=str(self.fixture["company"]),
            transfer_item=str(transfer_item["item_code"]),
            transfer_quantity=quantity,
            batch_id=batch_id,
            protected_item=str(protected_item["item_code"]),
            protected_stock_balance=float(protected_bin_rows[0]["actual_qty"]),
            source_warehouse=warehouses["source_warehouse"],
            transit_warehouse=warehouses["transit_warehouse"],
            destination_warehouse=warehouses["destination_warehouse"],
            protected_warehouse=warehouses["protected_warehouse"],
            stock_seed=str(seed["name"]),
            material_request=str(request["name"]),
            outgoing_stock_entry=str(outgoing["name"]),
            second_leg_stock_entry=str(incoming["name"]),
            clinic_sales_order=str(clinic_order["name"]),
            clinic_sales_order_item=str(clinic_order["items"][0]["name"]),
            clinic_reserved_quantity=float(self.fixture["clinic_reserved_quantity"]),
            protected_sales_order=str(protected_order["name"]),
            protected_pick_list=str(protected_pick["name"]),
            protected_reservation=str(protected_reservation["name"]),
            protected_fingerprints={
                "outgoing_stock_entry": multiwarehouse_document_fingerprint(outgoing),
                "protected_reservation": multiwarehouse_document_fingerprint(
                    protected_reservation
                ),
            },
            trace=tuple(trace),
        )


__all__ = ["ERPNextMultiwarehousePrefixBuilder", "MultiwarehousePrefix"]
