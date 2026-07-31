from __future__ import annotations

import json
from typing import Any

from .erpnext_return_evidence import ERPNextPartialReturnEvidenceCollector
from .frappe import FrappeHTTPAdapter


class ERPNextSalesReturnEvidenceCollector(ERPNextPartialReturnEvidenceCollector):
    """Collect native sales, stock, accounting, queue, and delivery evidence."""

    def __init__(
        self,
        adapter: FrappeHTTPAdapter,
        *,
        event_url: str = "http://127.0.0.1:9092",
    ) -> None:
        super().__init__(adapter, event_url=event_url)

    def collect(self, prefix: dict[str, Any]) -> dict[str, Any]:
        document_fields = {
            "stock_seed": "Stock Entry",
            "original_sales_order": "Sales Order",
            "original_delivery_note": "Delivery Note",
            "quality_inspection": "Quality Inspection",
            "affected_invoice": "Sales Invoice",
            "unaffected_invoice": "Sales Invoice",
            "shared_payment_entry": "Payment Entry",
            "sales_return": "Delivery Note",
            "credit_note": "Sales Invoice",
            "replacement_sales_order": "Sales Order",
            "replacement_delivery_note": "Delivery Note",
        }
        evidence = {
            key: self.get_document(doctype, str(prefix[key]))
            for key, doctype in document_fields.items()
        }
        sales_returns = self.full_documents(
            "Delivery Note",
            filters={
                "is_return": 1,
                "return_against": prefix["original_delivery_note"],
            },
        )
        credit_notes = self.full_documents(
            "Sales Invoice",
            filters={
                "is_return": 1,
                "return_against": prefix["affected_invoice"],
            },
        )
        all_deliveries = self.full_documents("Delivery Note")
        replacement_deliveries = [
            document
            for document in all_deliveries
            if self._references_item_field(
                document,
                "against_sales_order",
                str(prefix["replacement_sales_order"]),
            )
        ]
        all_invoices = self.full_documents("Sales Invoice")
        replacement_invoices = [
            document
            for document in all_invoices
            if self._references_item_field(
                document,
                "sales_order",
                str(prefix["replacement_sales_order"]),
            )
        ]
        voucher_names = {
            str(prefix["stock_seed"]),
            str(prefix["original_delivery_note"]),
            str(prefix["shared_payment_entry"]),
            str(prefix["sales_return"]),
            str(prefix["credit_note"]),
            str(prefix["replacement_delivery_note"]),
            *(str(document["name"]) for document in replacement_invoices),
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
                ],
                limit=1000,
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
                limit=2000,
            )
            if str(row.get("voucher_no")) in voucher_names
        ]
        sales_return_name = str(prefix["sales_return"])
        jobs = [
            job
            for job in self.list_documents(
                "RQ Job",
                fields=["name", "job_name", "status", "arguments", "queue"],
                order_by="creation desc",
                limit=500,
            )
            if sales_return_name
            in json.dumps(job, ensure_ascii=False, sort_keys=True, default=str)
        ]
        return {
            **evidence,
            "sales_returns": sorted(
                sales_returns,
                key=lambda row: str(row.get("name", "")),
            ),
            "credit_notes": sorted(
                credit_notes,
                key=lambda row: str(row.get("name", "")),
            ),
            "replacement_delivery_notes": sorted(
                replacement_deliveries,
                key=lambda row: str(row.get("name", "")),
            ),
            "replacement_invoices": sorted(
                replacement_invoices,
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
            "rq_jobs": sorted(
                jobs,
                key=lambda row: str(row.get("name", "")),
            ),
            "pickup_delivery": self.get_delivery(str(prefix["sales_return"])),
        }
