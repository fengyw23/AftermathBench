from __future__ import annotations

from collections.abc import Callable
from typing import Any, ClassVar

from .erpnext_multiwarehouse_evidence import (
    ERPNextMultiwarehouseEvidenceCollector,
)
from .erpnext_return_agent import ERPNextPartialReturnEnvironment
from .erpnext_return_prefix import _payload
from .frappe import FrappeHTTPAdapter


class ERPNextMultiwarehouseEnvironment(ERPNextPartialReturnEnvironment):
    """Ordinary ERPNext tools for inter-warehouse transfer recovery."""

    TOOL_NAMES = (
        "get_document",
        "list_documents",
        "list_related_documents",
        "get_stock_ledger",
        "get_stock_balance",
        "find_background_jobs",
        "submit_document",
        "cancel_document",
        "create_second_transfer_leg",
        "create_pick_list_from_sales_order",
        "create_stock_reservation_entry",
        "enqueue_stock_reposting",
        "resume_workers",
    )
    ALLOWED_DOCUMENT_TYPES: ClassVar[set[str]] = {
        "Stock Entry",
        "Material Request",
        "Warehouse",
        "Item",
        "Batch",
        "Serial No",
        "Serial and Batch Bundle",
        "Sales Order",
        "Pick List",
        "Stock Reservation Entry",
        "Repost Item Valuation",
    }
    MUTATION_TOOLS: ClassVar[set[str]] = {
        "submit_document",
        "cancel_document",
        "create_second_transfer_leg",
        "create_pick_list_from_sales_order",
        "create_stock_reservation_entry",
        "enqueue_stock_reposting",
        "resume_workers",
    }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        if kwargs.get("collector") is None:
            adapter = kwargs.get("adapter")
            if not isinstance(adapter, FrappeHTTPAdapter):
                raise TypeError("adapter must be a FrappeHTTPAdapter")
            kwargs["collector"] = ERPNextMultiwarehouseEvidenceCollector(adapter)
        super().__init__(*args, **kwargs)

    def invoke(self, tool: str, **kwargs: Any) -> dict[str, Any]:
        operations: dict[str, Callable[[], dict[str, Any]]] = {
            "get_document": lambda: self._get_document(
                str(kwargs["doctype"]), str(kwargs["name"])
            ),
            "list_documents": lambda: self._list_documents(
                str(kwargs["doctype"]), kwargs.get("filters")
            ),
            "list_related_documents": lambda: self._list_related_documents(
                str(kwargs["source_doctype"]),
                str(kwargs["source_name"]),
                str(kwargs["target_doctype"]),
                str(kwargs["relation_type"]) if kwargs.get("relation_type") else None,
            ),
            "get_stock_ledger": lambda: self._ledger(
                "Stock Ledger Entry", str(kwargs["voucher_no"])
            ),
            "get_stock_balance": lambda: self._get_stock_balance(
                str(kwargs["item_code"]), str(kwargs["warehouse"])
            ),
            "find_background_jobs": lambda: self._find_jobs(
                str(kwargs["reference"])
            ),
            "submit_document": lambda: self._submit(
                str(kwargs["doctype"]), str(kwargs["name"])
            ),
            "cancel_document": lambda: self._cancel(
                str(kwargs["doctype"]), str(kwargs["name"])
            ),
            "create_second_transfer_leg": lambda: self._create_second_transfer_leg(
                str(kwargs["outgoing_stock_entry"]),
                str(kwargs["destination_warehouse"]),
            ),
            "create_pick_list_from_sales_order": lambda: self._create_pick_list(
                str(kwargs["sales_order"])
            ),
            "create_stock_reservation_entry": lambda: self._create_reservation(
                str(kwargs["sales_order"]),
                str(kwargs["item_code"]),
                str(kwargs["warehouse"]),
                float(kwargs["quantity"]),
            ),
            "enqueue_stock_reposting": self._enqueue_stock_reposting,
            "resume_workers": self._resume_workers,
        }
        if tool not in operations:
            raise KeyError(f"unknown ERPNext multiwarehouse recovery tool: {tool}")
        return self._recorded_call(
            tool, dict(kwargs), lambda: self._guard(operations[tool])
        )

    def _get_stock_balance(self, item_code: str, warehouse: str) -> dict[str, Any]:
        bins = self.collector.list_documents(
            "Bin",
            fields=[
                "name",
                "item_code",
                "warehouse",
                "actual_qty",
                "reserved_qty",
                "reserved_stock",
                "projected_qty",
            ],
            filters={"item_code": item_code, "warehouse": warehouse},
            limit=10,
        )
        return {
            "ok": True,
            "item_code": item_code,
            "warehouse": warehouse,
            "bins": bins,
        }

    def _create_second_transfer_leg(
        self, outgoing_stock_entry: str, destination_warehouse: str
    ) -> dict[str, Any]:
        template = _payload(
            self.adapter.call_method(
                "erpnext.stock.doctype.stock_entry.stock_entry.make_stock_in_entry",
                {"source_name": outgoing_stock_entry},
            )
        )
        template["to_warehouse"] = destination_warehouse
        for item in template.get("items", []):
            item["t_warehouse"] = destination_warehouse
        document = _payload(self.adapter.create_resource("Stock Entry", template))
        return {"ok": True, "document": document}

    def _create_pick_list(self, sales_order: str) -> dict[str, Any]:
        template = _payload(
            self.adapter.call_method(
                "erpnext.selling.doctype.sales_order.sales_order.create_pick_list",
                {"source_name": sales_order},
            )
        )
        document = _payload(self.adapter.create_resource("Pick List", template))
        return {"ok": True, "document": document}

    def _create_reservation(
        self,
        sales_order: str,
        item_code: str,
        warehouse: str,
        quantity: float,
    ) -> dict[str, Any]:
        order = self.collector.get_document("Sales Order", sales_order)
        matching_items = [
            row
            for row in order.get("items", [])
            if str(row.get("item_code")) == item_code
        ]
        if len(matching_items) != 1:
            raise ValueError("sales order must contain exactly one matching item")
        bins = self.collector.list_documents(
            "Bin",
            fields=["actual_qty"],
            filters={"item_code": item_code, "warehouse": warehouse},
            limit=10,
        )
        available = sum(float(row.get("actual_qty", 0)) for row in bins)
        item = matching_items[0]
        document = _payload(
            self.adapter.create_resource(
                "Stock Reservation Entry",
                {
                    "item_code": item_code,
                    "warehouse": warehouse,
                    "voucher_type": "Sales Order",
                    "voucher_no": sales_order,
                    "voucher_detail_no": item["name"],
                    "available_qty": available,
                    "voucher_qty": item.get("stock_qty", item.get("qty")),
                    "stock_uom": item.get("stock_uom", item.get("uom", "Nos")),
                    "reserved_qty": quantity,
                    "delivered_qty": item.get("delivered_qty", 0),
                    "company": order["company"],
                },
            )
        )
        return {"ok": True, "document": document}

    def _enqueue_stock_reposting(self) -> dict[str, Any]:
        response = self.adapter.call_method(
            "erpnext.stock.doctype.repost_item_valuation.repost_item_valuation.execute_repost_item_valuation"
        )
        return {"ok": True, "result": response}


def reference_multiwarehouse_recovery(
    environment: ERPNextMultiwarehouseEnvironment,
) -> tuple[dict[str, Any], ...]:
    """Reference recovery expressed only through model-visible tools."""
    prefix = environment.prefix
    trace: list[dict[str, Any]] = []

    def call(tool: str, **kwargs: Any) -> dict[str, Any]:
        result = environment.invoke(tool, **kwargs)
        trace.append({"tool": tool, "arguments": kwargs, "result": result})
        if not result.get("ok"):
            raise RuntimeError(f"reference tool failed: {tool}: {result}")
        return result

    outgoing = call(
        "get_document",
        doctype="Stock Entry",
        name=prefix["outgoing_stock_entry"],
    )["document"]
    second_legs = call(
        "list_documents",
        doctype="Stock Entry",
        filters={"outgoing_stock_entry": prefix["outgoing_stock_entry"]},
    )["documents"]
    active_legs = [
        document
        for document in second_legs
        if int(document.get("docstatus", 0)) != 2
    ]
    if not active_legs:
        second_leg = call(
            "create_second_transfer_leg",
            outgoing_stock_entry=prefix["outgoing_stock_entry"],
            destination_warehouse=prefix["destination_warehouse"],
        )["document"]
    elif len(active_legs) == 1:
        second_leg = active_legs[0]
    else:
        raise RuntimeError("duplicate active second transfer legs")
    if int(second_leg.get("docstatus", 0)) == 0:
        second_leg = call(
            "submit_document", doctype="Stock Entry", name=second_leg["name"]
        )["document"]

    call("get_stock_ledger", voucher_no=second_leg["name"])
    call(
        "get_stock_balance",
        item_code=prefix["transfer_item"],
        warehouse=prefix["destination_warehouse"],
    )
    reservations = call(
        "list_documents",
        doctype="Stock Reservation Entry",
        filters={"voucher_no": prefix["clinic_sales_order"]},
    )["documents"]
    active_reservations = [
        document
        for document in reservations
        if int(document.get("docstatus", 0)) != 2
    ]
    if not active_reservations:
        reservation = call(
            "create_stock_reservation_entry",
            sales_order=prefix["clinic_sales_order"],
            item_code=prefix["transfer_item"],
            warehouse=prefix["destination_warehouse"],
            quantity=prefix["clinic_reserved_quantity"],
        )["document"]
        call(
            "submit_document",
            doctype="Stock Reservation Entry",
            name=reservation["name"],
        )
    elif len(active_reservations) > 1:
        raise RuntimeError("duplicate active clinic reservations")

    reposts = call(
        "list_documents",
        doctype="Repost Item Valuation",
        filters={"voucher_no": second_leg["name"]},
    )["documents"]
    unfinished = [
        document
        for document in reposts
        if str(document.get("status", "")).lower()
        in {"queued", "in progress", "failed"}
    ]
    if unfinished:
        call("enqueue_stock_reposting")
        call("resume_workers")
    call(
        "get_document",
        doctype="Stock Entry",
        name=prefix["outgoing_stock_entry"],
    )
    call(
        "get_document",
        doctype="Stock Reservation Entry",
        name=prefix["protected_reservation"],
    )
    _ = outgoing
    return tuple(trace)


__all__ = [
    "ERPNextMultiwarehouseEnvironment",
    "reference_multiwarehouse_recovery",
]
