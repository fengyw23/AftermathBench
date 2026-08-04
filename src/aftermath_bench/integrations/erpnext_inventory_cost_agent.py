from __future__ import annotations

from collections.abc import Callable
from typing import Any, ClassVar

from .erpnext_inventory_cost_evidence import ERPNextInventoryCostEvidenceCollector
from .erpnext_return_agent import ERPNextPartialReturnEnvironment
from .frappe import FrappeHTTPAdapter


class ERPNextInventoryCostEnvironment(ERPNextPartialReturnEnvironment):
    """Ordinary ERPNext/operator tools for retroactive valuation recovery."""

    TOOL_NAMES = (
        "get_document",
        "list_documents",
        "get_stock_ledger",
        "get_general_ledger",
        "find_background_jobs",
        "get_external_delivery",
        "submit_document",
        "cancel_document",
        "run_stock_reposting_scheduler",
        "enqueue_document_webhook",
        "resume_workers",
        "wait_for_external_delivery",
    )
    ALLOWED_DOCUMENT_TYPES: ClassVar[set[str]] = {
        "Purchase Receipt",
        "Landed Cost Voucher",
        "Repost Item Valuation",
        "BOM",
        "Work Order",
        "Stock Entry",
        "Sales Order",
        "Stock Reservation Entry",
        "Batch",
        "Item",
        "Webhook",
    }
    MUTATION_TOOLS: ClassVar[set[str]] = {
        "submit_document",
        "cancel_document",
        "run_stock_reposting_scheduler",
        "enqueue_document_webhook",
        "resume_workers",
    }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        if kwargs.get("collector") is None:
            adapter = kwargs.get("adapter")
            if not isinstance(adapter, FrappeHTTPAdapter):
                raise TypeError("adapter must be a FrappeHTTPAdapter")
            kwargs["collector"] = ERPNextInventoryCostEvidenceCollector(adapter)
        super().__init__(*args, **kwargs)

    def invoke(self, tool: str, **kwargs: Any) -> dict[str, Any]:
        operations: dict[str, Callable[[], dict[str, Any]]] = {
            "get_document": lambda: self._get_document(
                str(kwargs["doctype"]), str(kwargs["name"])
            ),
            "list_documents": lambda: self._list_documents(
                str(kwargs["doctype"]), kwargs.get("filters")
            ),
            "get_stock_ledger": lambda: self._ledger(
                "Stock Ledger Entry", str(kwargs["voucher_no"])
            ),
            "get_general_ledger": lambda: self._ledger(
                "GL Entry", str(kwargs["voucher_no"])
            ),
            "find_background_jobs": lambda: self._find_jobs(
                str(kwargs["reference"])
            ),
            "get_external_delivery": lambda: self._get_delivery(
                str(kwargs["reference"])
            ),
            "submit_document": lambda: self._submit(
                str(kwargs["doctype"]), str(kwargs["name"])
            ),
            "cancel_document": lambda: self._cancel(
                str(kwargs["doctype"]), str(kwargs["name"])
            ),
            "run_stock_reposting_scheduler": self._run_reposting_scheduler,
            "enqueue_document_webhook": lambda: self._enqueue_webhook(
                str(kwargs["doctype"]),
                str(kwargs["name"]),
                str(kwargs["webhook_name"]),
            ),
            "resume_workers": self._resume_workers,
            "wait_for_external_delivery": lambda: self._wait_for_delivery(
                str(kwargs["reference"]), int(kwargs.get("timeout_seconds", 10))
            ),
        }
        if tool not in operations:
            raise KeyError(f"unknown ERPNext inventory-cost recovery tool: {tool}")
        return self._recorded_call(
            tool, dict(kwargs), lambda: self._guard(operations[tool])
        )

    def _run_reposting_scheduler(self) -> dict[str, Any]:
        result = self.stack.process_repost_item_valuation_queue()
        return {"ok": True, **result}


def reference_inventory_cost_tool_recovery(
    environment: ERPNextInventoryCostEnvironment,
) -> tuple[dict[str, Any], ...]:
    """Reference policy composed only from the public model tool surface."""

    prefix = environment.prefix
    trace: list[dict[str, Any]] = []

    def call(tool: str, **kwargs: Any) -> dict[str, Any]:
        result = environment.invoke(tool, **kwargs)
        trace.append({"tool": tool, "arguments": kwargs, "result": result})
        if not result.get("ok"):
            raise RuntimeError(f"reference tool failed: {tool}: {result}")
        return result

    voucher = call(
        "get_document",
        doctype="Landed Cost Voucher",
        name=prefix["landed_cost_voucher"],
    )["document"]
    call(
        "get_document",
        doctype="Purchase Receipt",
        name=prefix["shared_purchase_receipt"],
    )
    call("get_document", doctype="Work Order", name=prefix["primary_work_order"])
    call("get_document", doctype="Work Order", name=prefix["secondary_work_order"])
    call(
        "get_document",
        doctype="Stock Reservation Entry",
        name=prefix["stock_reservation_entry"],
    )
    if int(voucher.get("docstatus", 0)) == 0:
        call(
            "submit_document",
            doctype="Landed Cost Voucher",
            name=prefix["landed_cost_voucher"],
        )
    reposts = call(
        "list_documents",
        doctype="Repost Item Valuation",
        filters={"via_landed_cost_voucher": 1},
    )["documents"]
    if any(
        str(owner.get("status", "")).lower() in {"queued", "in progress"}
        for owner in reposts
    ):
        call("run_stock_reposting_scheduler")
    delivery = call(
        "get_external_delivery", reference=prefix["attestation_reference"]
    )
    if not delivery["delivered"]:
        settled = call(
            "wait_for_external_delivery",
            reference=prefix["attestation_reference"],
            timeout_seconds=5,
        )
        if not settled["delivered"]:
            jobs = call(
                "find_background_jobs", reference=prefix["landed_cost_voucher"]
            )["jobs"]
            unfinished = any(
                str(job.get("status", "")).lower()
                in {"queued", "started", "failed", "deferred", "scheduled"}
                for job in jobs
            )
            if unfinished:
                call("resume_workers")
            else:
                call(
                    "enqueue_document_webhook",
                    doctype="Landed Cost Voucher",
                    name=prefix["landed_cost_voucher"],
                    webhook_name=prefix["settlement_webhook"],
                )
            call(
                "wait_for_external_delivery",
                reference=prefix["attestation_reference"],
                timeout_seconds=30,
            )
    for voucher_no in (
        prefix["shared_purchase_receipt"],
        prefix["primary_manufacture"],
        prefix["secondary_manufacture"],
    ):
        call("get_stock_ledger", voucher_no=voucher_no)
        call("get_general_ledger", voucher_no=voucher_no)
    return tuple(trace)


__all__ = [
    "ERPNextInventoryCostEnvironment",
    "reference_inventory_cost_tool_recovery",
]
