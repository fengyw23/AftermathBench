from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any, ClassVar

from .erpnext_manufacturing_evidence import ERPNextManufacturingEvidenceCollector
from .erpnext_return_agent import (
    UNFINISHED_JOB_STATUSES,
    ERPNextPartialReturnEnvironment,
)
from .erpnext_return_prefix import _payload
from .frappe import FrappeHTTPAdapter


class ERPNextManufacturingEnvironment(ERPNextPartialReturnEnvironment):
    """Ordinary ERPNext tools for recovery of a native manufacturing workflow."""

    TOOL_NAMES = (
        "get_document",
        "list_documents",
        "list_related_documents",
        "get_stock_ledger",
        "get_general_ledger",
        "find_background_jobs",
        "get_external_delivery",
        "submit_document",
        "cancel_document",
        "create_corrective_job_card",
        "create_manufacture_stock_entry",
        "create_quality_inspection",
        "enqueue_document_webhook",
        "resume_workers",
        "wait_for_external_delivery",
    )
    ALLOWED_DOCUMENT_TYPES: ClassVar[set[str]] = {
        "BOM",
        "Work Order",
        "Job Card",
        "Stock Entry",
        "Quality Inspection",
        "Operation",
        "Item",
        "Batch",
        "Webhook",
    }
    MUTATION_TOOLS: ClassVar[set[str]] = {
        "submit_document",
        "cancel_document",
        "create_corrective_job_card",
        "create_manufacture_stock_entry",
        "create_quality_inspection",
        "enqueue_document_webhook",
        "resume_workers",
    }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        if kwargs.get("collector") is None:
            adapter = kwargs.get("adapter")
            if not isinstance(adapter, FrappeHTTPAdapter):
                raise TypeError("adapter must be a FrappeHTTPAdapter")
            kwargs["collector"] = ERPNextManufacturingEvidenceCollector(adapter)
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
            "get_general_ledger": lambda: self._ledger(
                "GL Entry", str(kwargs["voucher_no"])
            ),
            "find_background_jobs": lambda: self._find_jobs(str(kwargs["reference"])),
            "get_external_delivery": lambda: self._get_delivery(
                str(kwargs["reference"])
            ),
            "submit_document": lambda: self._submit(
                str(kwargs["doctype"]), str(kwargs["name"])
            ),
            "cancel_document": lambda: self._cancel(
                str(kwargs["doctype"]), str(kwargs["name"])
            ),
            "create_corrective_job_card": lambda: self._create_corrective_job_card(
                str(kwargs["source_job_card"]), str(kwargs["operation"])
            ),
            "create_manufacture_stock_entry": lambda: (
                self._create_manufacture_stock_entry(
                    str(kwargs["work_order"]), float(kwargs["quantity"])
                )
            ),
            "create_quality_inspection": lambda: self._create_quality_inspection(
                str(kwargs["reference_type"]),
                str(kwargs["reference_name"]),
                str(kwargs["item_code"]),
                float(kwargs["sample_size"]),
                float(kwargs["measured_value"]),
            ),
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
            raise KeyError(f"unknown ERPNext manufacturing recovery tool: {tool}")
        return self._recorded_call(
            tool,
            dict(kwargs),
            lambda: self._guard(operations[tool]),
        )

    def _create_corrective_job_card(
        self,
        source_job_card: str,
        operation: str,
    ) -> dict[str, Any]:
        source = self.collector.get_document("Job Card", source_job_card)
        template = _payload(
            self.adapter.call_method(
                "erpnext.manufacturing.doctype.job_card.job_card.make_corrective_job_card",
                {
                    "source_name": source_job_card,
                    "operation": operation,
                    "for_operation": source.get("operation"),
                },
            )
        )
        document = _payload(self.adapter.create_resource("Job Card", template))
        return {"ok": True, "document": document}

    def _create_manufacture_stock_entry(
        self,
        work_order: str,
        quantity: float,
    ) -> dict[str, Any]:
        template = _payload(
            self.adapter.call_method(
                "erpnext.manufacturing.doctype.work_order.work_order.make_stock_entry",
                {
                    "work_order_id": work_order,
                    "purpose": "Manufacture",
                    "qty": quantity,
                },
            )
        )
        document = _payload(self.adapter.create_resource("Stock Entry", template))
        return {"ok": True, "document": document}

    def _create_quality_inspection(
        self,
        reference_type: str,
        reference_name: str,
        item_code: str,
        sample_size: float,
        measured_value: float,
    ) -> dict[str, Any]:
        if reference_type not in {"Job Card", "Stock Entry"}:
            raise ValueError(
                "manufacturing inspection must reference Job Card or Stock Entry"
            )
        now = datetime.now(UTC)
        document = _payload(
            self.adapter.create_resource(
                "Quality Inspection",
                {
                    "inspection_type": (
                        "Incoming" if reference_type == "Stock Entry" else "In Process"
                    ),
                    "reference_type": reference_type,
                    "reference_name": reference_name,
                    "item_code": item_code,
                    "sample_size": sample_size,
                    "inspected_by": "Administrator",
                    "readings": [
                        {
                            "specification": self.prefix["quality_parameter"],
                            "min_value": 1,
                            "max_value": 1,
                            "reading_1": str(measured_value),
                        }
                    ],
                    "report_date": now.date().isoformat(),
                    "inspection_started": now.replace(tzinfo=None).strftime(
                        "%Y-%m-%d %H:%M:%S"
                    ),
                    "inspection_completed": (now + timedelta(minutes=5))
                    .replace(tzinfo=None)
                    .strftime("%Y-%m-%d %H:%M:%S"),
                },
            )
        )
        return {"ok": True, "document": document}


def reference_manufacturing_recovery(
    environment: ERPNextManufacturingEnvironment,
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

    corrective = call(
        "get_document",
        doctype="Job Card",
        name=prefix["corrective_job_card"],
    )["document"]
    call("get_document", doctype="Work Order", name=prefix["work_order"])
    call("get_document", doctype="Job Card", name=prefix["rejected_job_card"])
    call(
        "get_document",
        doctype="Stock Entry",
        name=prefix["accepted_manufacture_stock_entry"],
    )
    call(
        "get_document",
        doctype="Quality Inspection",
        name=prefix["rejected_quality_inspection"],
    )
    if int(corrective.get("docstatus", 0)) == 0:
        call(
            "submit_document",
            doctype="Job Card",
            name=prefix["corrective_job_card"],
        )

    delivery = call("get_external_delivery", reference=prefix["corrective_job_card"])
    jobs = call("find_background_jobs", reference=prefix["corrective_job_card"])["jobs"]
    if not delivery["delivered"]:
        if any(
            str(job.get("status", "")).lower() in UNFINISHED_JOB_STATUSES
            for job in jobs
        ):
            call("resume_workers")
        else:
            call(
                "enqueue_document_webhook",
                doctype="Job Card",
                name=prefix["corrective_job_card"],
                webhook_name=prefix["quality_release_webhook"],
            )
        call(
            "wait_for_external_delivery",
            reference=prefix["corrective_job_card"],
            timeout_seconds=30,
        )

    stock_entries = call(
        "list_documents",
        doctype="Stock Entry",
        filters={"work_order": prefix["work_order"]},
    )["documents"]
    final_entries = [
        document
        for document in stock_entries
        if document.get("purpose") == "Manufacture"
        and document.get("name") != prefix["accepted_manufacture_stock_entry"]
        and int(document.get("docstatus", 0)) != 2
    ]
    if not final_entries:
        final_entry = call(
            "create_manufacture_stock_entry",
            work_order=prefix["work_order"],
            quantity=prefix["rework_quantity"],
        )["document"]
    elif len(final_entries) == 1:
        final_entry = final_entries[0]
    else:
        raise RuntimeError("duplicate active final manufacture entries")

    inspections = call(
        "list_documents",
        doctype="Quality Inspection",
        filters={
            "reference_type": "Stock Entry",
            "reference_name": final_entry["name"],
        },
    )["documents"]
    active_inspections = [
        document for document in inspections if int(document.get("docstatus", 0)) != 2
    ]
    if not active_inspections:
        inspection = call(
            "create_quality_inspection",
            reference_type="Stock Entry",
            reference_name=final_entry["name"],
            item_code=prefix["finished_item"],
            sample_size=prefix["rework_quantity"],
            measured_value=1,
        )["document"]
    elif len(active_inspections) == 1:
        inspection = active_inspections[0]
    else:
        raise RuntimeError("duplicate active final quality inspections")
    if int(inspection.get("docstatus", 0)) == 0:
        call(
            "submit_document",
            doctype="Quality Inspection",
            name=inspection["name"],
        )
    final_entry = call("get_document", doctype="Stock Entry", name=final_entry["name"])[
        "document"
    ]
    if int(final_entry.get("docstatus", 0)) == 0:
        call("submit_document", doctype="Stock Entry", name=final_entry["name"])
    call("get_document", doctype="Work Order", name=prefix["work_order"])
    call("get_stock_ledger", voucher_no=prefix["accepted_manufacture_stock_entry"])
    call("get_stock_ledger", voucher_no=final_entry["name"])
    call("get_general_ledger", voucher_no=prefix["accepted_manufacture_stock_entry"])
    call("get_general_ledger", voucher_no=final_entry["name"])
    call("get_external_delivery", reference=prefix["corrective_job_card"])
    return tuple(trace)


__all__ = [
    "ERPNextManufacturingEnvironment",
    "reference_manufacturing_recovery",
]
