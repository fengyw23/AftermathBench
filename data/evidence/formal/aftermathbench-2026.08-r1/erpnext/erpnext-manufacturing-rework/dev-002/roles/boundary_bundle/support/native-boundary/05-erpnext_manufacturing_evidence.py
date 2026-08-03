from __future__ import annotations

import json
from typing import Any

from .erpnext_return_evidence import ERPNextPartialReturnEvidenceCollector
from .frappe import FrappeHTTPAdapter


class ERPNextManufacturingEvidenceCollector(ERPNextPartialReturnEvidenceCollector):
    """Collect the native manufacturing, stock, accounting and queue closure."""

    def __init__(
        self,
        adapter: FrappeHTTPAdapter,
        *,
        event_url: str = "http://127.0.0.1:9092",
    ) -> None:
        super().__init__(adapter, event_url=event_url)

    def collect(self, prefix: dict[str, Any]) -> dict[str, Any]:
        document_fields = {
            "bom": "BOM",
            "work_order": "Work Order",
            "accepted_job_card": "Job Card",
            "rejected_job_card": "Job Card",
            "corrective_job_card": "Job Card",
            "accepted_quality_inspection": "Quality Inspection",
            "rejected_quality_inspection": "Quality Inspection",
            "accepted_manufacture_stock_entry": "Stock Entry",
            "material_transfer_stock_entry": "Stock Entry",
            "unrelated_stock_entry": "Stock Entry",
        }
        evidence = {
            key: self.get_document(doctype, str(prefix[key]))
            for key, doctype in document_fields.items()
        }
        work_order = str(prefix["work_order"])
        job_cards = self.full_documents(
            "Job Card",
            filters={"work_order": work_order},
            limit=100,
        )
        stock_entries = self.full_documents(
            "Stock Entry",
            filters={"work_order": work_order},
            limit=100,
        )
        active_names = {
            str(document.get("name"))
            for document in (*job_cards, *stock_entries)
            if int(document.get("docstatus", 0)) != 2
        }
        quality_inspections = [
            document
            for document in self.full_documents("Quality Inspection", limit=200)
            if str(document.get("reference_name")) in active_names
        ]
        voucher_names = {
            str(prefix["accepted_manufacture_stock_entry"]),
            str(prefix["material_transfer_stock_entry"]),
            str(prefix["unrelated_stock_entry"]),
            *(
                str(document.get("name"))
                for document in stock_entries
                if int(document.get("docstatus", 0)) != 2
            ),
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
                    "is_cancelled",
                    "item_code",
                    "warehouse",
                    "serial_and_batch_bundle",
                ],
                limit=2000,
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
                ],
                limit=3000,
            )
            if str(row.get("voucher_no")) in voucher_names
        ]
        corrective_name = str(prefix["corrective_job_card"])
        jobs = [
            job
            for job in self.list_documents(
                "RQ Job",
                fields=["name", "job_name", "status", "arguments", "queue"],
                order_by="creation desc",
                limit=500,
            )
            if corrective_name in json.dumps(job, sort_keys=True, default=str)
        ]
        return {
            **evidence,
            "job_cards": sorted(job_cards, key=lambda row: str(row.get("name", ""))),
            "manufacture_stock_entries": sorted(
                stock_entries,
                key=lambda row: str(row.get("name", "")),
            ),
            "quality_inspections": sorted(
                quality_inspections,
                key=lambda row: str(row.get("name", "")),
            ),
            "stock_ledger_entries": sorted(
                stock_ledger,
                key=lambda row: str(row.get("name", "")),
            ),
            "gl_entries": sorted(
                general_ledger,
                key=lambda row: str(row.get("name", "")),
            ),
            "rq_jobs": sorted(jobs, key=lambda row: str(row.get("name", ""))),
            "quality_release_delivery": self.get_delivery(corrective_name),
        }


__all__ = ["ERPNextManufacturingEvidenceCollector"]
