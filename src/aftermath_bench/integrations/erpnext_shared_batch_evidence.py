from __future__ import annotations

import json
from typing import Any

from .erpnext_return_evidence import ERPNextPartialReturnEvidenceCollector
from .frappe import FrappeHTTPAdapter


class ERPNextSharedBatchEvidenceCollector(ERPNextPartialReturnEvidenceCollector):
    """Collect raw native evidence for both consumers of one supplier batch."""

    def __init__(
        self,
        adapter: FrappeHTTPAdapter,
        *,
        event_url: str = "http://127.0.0.1:9092",
    ) -> None:
        super().__init__(adapter, event_url=event_url)

    def collect(self, prefix: dict[str, Any]) -> dict[str, Any]:
        document_fields = {
            "shared_purchase_receipt": "Purchase Receipt",
            "shared_landed_cost_voucher": "Landed Cost Voucher",
            "primary_bom": "BOM",
            "secondary_bom": "BOM",
            "primary_work_order": "Work Order",
            "secondary_work_order": "Work Order",
            "primary_transfer": "Stock Entry",
            "secondary_transfer": "Stock Entry",
            "primary_material_quality_inspection": "Quality Inspection",
            "secondary_material_quality_inspection": "Quality Inspection",
            "accepted_primary_job_card": "Job Card",
            "rejected_primary_job_card": "Job Card",
            "secondary_job_card": "Job Card",
            "accepted_primary_manufacture": "Stock Entry",
            "secondary_manufacture": "Stock Entry",
            "corrective_job_card": "Job Card",
            "customer_reservation": "Sales Order",
            "stock_reservation_entry": "Stock Reservation Entry",
            "unrelated_receipt": "Stock Entry",
        }
        documents = {
            key: self.get_document(doctype, str(prefix[key]))
            for key, doctype in document_fields.items()
        }
        work_orders = {
            str(prefix["primary_work_order"]),
            str(prefix["secondary_work_order"]),
        }
        job_cards = [
            document
            for work_order in sorted(work_orders)
            for document in self.full_documents(
                "Job Card", filters={"work_order": work_order}, limit=100
            )
        ]
        stock_entries = [
            document
            for work_order in sorted(work_orders)
            for document in self.full_documents(
                "Stock Entry", filters={"work_order": work_order}, limit=100
            )
        ]
        active_names = {
            str(document.get("name"))
            for document in (*job_cards, *stock_entries)
            if int(document.get("docstatus", 0)) != 2
        }
        quality_inspections = [
            document
            for document in self.full_documents("Quality Inspection", limit=300)
            if str(document.get("reference_name")) in active_names
        ]
        voucher_names = {
            str(prefix["shared_purchase_receipt"]),
            str(prefix["shared_landed_cost_voucher"]),
            str(prefix["accepted_primary_manufacture"]),
            str(prefix["secondary_manufacture"]),
            str(prefix["primary_transfer"]),
            str(prefix["secondary_transfer"]),
            str(prefix["unrelated_receipt"]),
            *(str(document.get("name")) for document in stock_entries),
        }
        stock_ledger = [
            row
            for row in self.list_documents(
                "Stock Ledger Entry",
                fields=[
                    "name",
                    "voucher_type",
                    "voucher_no",
                    "actual_qty",
                    "qty_after_transaction",
                    "valuation_rate",
                    "is_cancelled",
                    "item_code",
                    "warehouse",
                    "serial_and_batch_bundle",
                ],
                limit=4000,
            )
            if str(row.get("voucher_no")) in voucher_names
        ]
        general_ledger = [
            row
            for row in self.list_documents(
                "GL Entry",
                fields=[
                    "name",
                    "voucher_type",
                    "voucher_no",
                    "debit",
                    "credit",
                    "is_cancelled",
                    "account",
                    "against_voucher_type",
                    "against_voucher",
                ],
                limit=5000,
            )
            if str(row.get("voucher_no")) in voucher_names
        ]
        corrective_name = str(prefix["corrective_job_card"])
        jobs = [
            row
            for row in self.list_documents(
                "RQ Job",
                fields=["name", "job_name", "status", "arguments", "queue"],
                order_by="creation desc",
                limit=500,
            )
            if corrective_name in json.dumps(row, sort_keys=True, default=str)
        ]
        return {
            **documents,
            "supplier_batch": self.get_document(
                "Batch", str(prefix["supplier_batch_id"])
            ),
            "job_cards": sorted(job_cards, key=lambda row: str(row.get("name", ""))),
            "manufacture_stock_entries": sorted(
                stock_entries, key=lambda row: str(row.get("name", ""))
            ),
            "quality_inspections": sorted(
                quality_inspections, key=lambda row: str(row.get("name", ""))
            ),
            "stock_ledger_entries": sorted(
                stock_ledger, key=lambda row: str(row.get("name", ""))
            ),
            "gl_entries": sorted(
                general_ledger, key=lambda row: str(row.get("name", ""))
            ),
            "rq_jobs": sorted(jobs, key=lambda row: str(row.get("name", ""))),
            "certificate_delivery": self.get_delivery(
                str(prefix["certificate_reference"])
            ),
        }


__all__ = ["ERPNextSharedBatchEvidenceCollector"]
