from __future__ import annotations

from typing import Any, ClassVar

from .erpnext_manufacturing_agent import ERPNextManufacturingEnvironment
from .erpnext_return_prefix import _payload
from .erpnext_shared_batch_evidence import ERPNextSharedBatchEvidenceCollector
from .frappe import FrappeHTTPAdapter


class ERPNextSharedBatchEnvironment(ERPNextManufacturingEnvironment):
    """Model-visible native tools for shared-batch recovery."""

    ALLOWED_DOCUMENT_TYPES: ClassVar[set[str]] = {
        *ERPNextManufacturingEnvironment.ALLOWED_DOCUMENT_TYPES,
        "Purchase Receipt",
        "Purchase Receipt Item",
        "Landed Cost Voucher",
        "Sales Order",
        "Stock Reservation Entry",
    }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        if kwargs.get("collector") is None:
            adapter = kwargs.get("adapter")
            if not isinstance(adapter, FrappeHTTPAdapter):
                raise TypeError("adapter must be a FrappeHTTPAdapter")
            kwargs["collector"] = ERPNextSharedBatchEvidenceCollector(adapter)
        super().__init__(*args, **kwargs)

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
        for row in template.get("items", []):
            if row.get("item_code") == self.prefix["shared_component"]:
                row["use_serial_batch_fields"] = 1
                row["batch_no"] = self.prefix["supplier_batch_id"]
                row.pop("serial_and_batch_bundle", None)
        document = _payload(self.adapter.create_resource("Stock Entry", template))
        return {"ok": True, "document": document}


def reference_shared_batch_recovery(
    environment: ERPNextSharedBatchEnvironment,
) -> tuple[dict[str, Any], ...]:
    """Recover through ordinary tools after reconstructing all obligations."""

    prefix = environment.prefix
    trace: list[dict[str, Any]] = []

    def call(tool: str, **kwargs: Any) -> dict[str, Any]:
        result = environment.invoke(tool, **kwargs)
        trace.append({"tool": tool, "arguments": kwargs, "result": result})
        if not result.get("ok"):
            raise RuntimeError(f"reference tool failed: {tool}: {result}")
        return result

    # Reconstruct the failed branch and every protected cross-obligation before
    # any mutation.  No benchmark-only state summary is available.
    corrective = call(
        "get_document", doctype="Job Card", name=prefix["corrective_job_card"]
    )["document"]
    for doctype, key in (
        ("Work Order", "primary_work_order"),
        ("Work Order", "secondary_work_order"),
        ("Stock Entry", "accepted_primary_manufacture"),
        ("Stock Entry", "secondary_manufacture"),
        ("Purchase Receipt", "shared_purchase_receipt"),
        ("Landed Cost Voucher", "shared_landed_cost_voucher"),
        ("Sales Order", "customer_reservation"),
        ("Stock Reservation Entry", "stock_reservation_entry"),
        ("Stock Entry", "unrelated_receipt"),
    ):
        call("get_document", doctype=doctype, name=prefix[key])
    call("get_stock_ledger", voucher_no=prefix["shared_purchase_receipt"])
    call("get_general_ledger", voucher_no=prefix["shared_purchase_receipt"])

    if int(corrective.get("docstatus", 0)) == 0:
        call(
            "submit_document",
            doctype="Job Card",
            name=prefix["corrective_job_card"],
        )

    delivery = call(
        "get_external_delivery", reference=prefix["certificate_reference"]
    ).get("delivery")
    if delivery is None:
        jobs = call("find_background_jobs", reference=prefix["corrective_job_card"])[
            "jobs"
        ]
        unfinished = [
            job
            for job in jobs
            if str(job.get("status", "")).lower()
            in {"queued", "started", "failed", "deferred", "scheduled"}
        ]
        if unfinished:
            call("resume_workers")
        else:
            call(
                "enqueue_document_webhook",
                doctype="Job Card",
                name=prefix["corrective_job_card"],
                webhook_name=prefix["certificate_webhook"],
            )
        call(
            "wait_for_external_delivery",
            reference=prefix["certificate_reference"],
            timeout_seconds=15,
        )

    entries = call(
        "list_documents",
        doctype="Stock Entry",
        filters={"work_order": prefix["primary_work_order"]},
    )["documents"]
    final_entries = [
        document
        for document in entries
        if document.get("purpose") == "Manufacture"
        and document.get("name") != prefix["accepted_primary_manufacture"]
        and int(document.get("docstatus", 0)) != 2
    ]
    if not final_entries:
        final_entry = call(
            "create_manufacture_stock_entry",
            work_order=prefix["primary_work_order"],
            quantity=prefix["rework_quantity"],
        )["document"]
    elif len(final_entries) == 1:
        final_entry = final_entries[0]
    else:
        raise RuntimeError("duplicate active corrective manufacture entries")

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
            item_code=prefix["primary_finished_item"],
            sample_size=prefix["rework_quantity"],
            measured_value=1,
        )["document"]
    elif len(active_inspections) == 1:
        inspection = active_inspections[0]
    else:
        raise RuntimeError("duplicate active corrective quality inspections")
    if int(inspection.get("docstatus", 0)) == 0:
        call("submit_document", doctype="Quality Inspection", name=inspection["name"])
    final_entry = call("get_document", doctype="Stock Entry", name=final_entry["name"])[
        "document"
    ]
    if int(final_entry.get("docstatus", 0)) == 0:
        call("submit_document", doctype="Stock Entry", name=final_entry["name"])

    # Verify the repaired branch and the obligations that should not move.
    for doctype, key in (
        ("Work Order", "primary_work_order"),
        ("Work Order", "secondary_work_order"),
        ("Landed Cost Voucher", "shared_landed_cost_voucher"),
        ("Stock Reservation Entry", "stock_reservation_entry"),
    ):
        call("get_document", doctype=doctype, name=prefix[key])
    call("get_stock_ledger", voucher_no=final_entry["name"])
    call("get_general_ledger", voucher_no=final_entry["name"])
    call("get_external_delivery", reference=prefix["certificate_reference"])
    return tuple(trace)


__all__ = [
    "ERPNextSharedBatchEnvironment",
    "reference_shared_batch_recovery",
]
