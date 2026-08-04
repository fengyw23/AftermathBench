from __future__ import annotations

from typing import Any

from .erpnext_return_evidence import ERPNextPartialReturnEvidenceCollector
from .frappe import FrappeHTTPAdapter


class ERPNextInventoryCostEvidenceCollector(ERPNextPartialReturnEvidenceCollector):
    """Collect native documents, ledgers, repost owners and external evidence."""

    def __init__(
        self,
        adapter: FrappeHTTPAdapter,
        *,
        event_url: str = "http://127.0.0.1:9092",
    ) -> None:
        super().__init__(adapter, event_url=event_url)

    def find_background_jobs(self, reference: str) -> list[dict[str, Any]]:
        response = self.adapter.call_method(
            "frappe.aftermath_bridge.find_background_jobs", {"reference": reference}
        )
        payload = response.get("message")
        if not isinstance(payload, dict) or not isinstance(payload.get("jobs"), list):
            raise TypeError("native background-job query returned no jobs list")
        return [dict(row) for row in payload["jobs"]]

    def collect(self, prefix: dict[str, Any]) -> dict[str, Any]:
        document_fields = {
            "shared_purchase_receipt": "Purchase Receipt",
            "primary_bom": "BOM",
            "secondary_bom": "BOM",
            "primary_work_order": "Work Order",
            "secondary_work_order": "Work Order",
            "primary_transfer": "Stock Entry",
            "secondary_transfer": "Stock Entry",
            "primary_manufacture": "Stock Entry",
            "secondary_manufacture": "Stock Entry",
            "customer_reservation": "Sales Order",
            "stock_reservation_entry": "Stock Reservation Entry",
            "unrelated_receipt": "Stock Entry",
            "landed_cost_voucher": "Landed Cost Voucher",
        }
        documents = {
            key: self.get_document(doctype, str(prefix[key]))
            for key, doctype in document_fields.items()
        }
        receipt = str(prefix["shared_purchase_receipt"])
        voucher_names = {
            receipt,
            str(prefix["primary_transfer"]),
            str(prefix["secondary_transfer"]),
            str(prefix["primary_manufacture"]),
            str(prefix["secondary_manufacture"]),
            str(prefix["unrelated_receipt"]),
        }
        stock_ledger = [
            row
            for row in self.list_documents(
                "Stock Ledger Entry",
                fields=[
                    "name",
                    "voucher_type",
                    "voucher_no",
                    "voucher_detail_no",
                    "actual_qty",
                    "qty_after_transaction",
                    "valuation_rate",
                    "stock_value",
                    "stock_value_difference",
                    "is_cancelled",
                    "item_code",
                    "warehouse",
                    "posting_date",
                    "posting_time",
                ],
                limit=5000,
            )
            if str(row.get("voucher_no")) in voucher_names
        ]
        gl_entries = [
            row
            for row in self.list_documents(
                "GL Entry",
                fields=[
                    "name",
                    "voucher_type",
                    "voucher_no",
                    "voucher_detail_no",
                    "debit",
                    "credit",
                    "is_cancelled",
                    "account",
                    "against",
                ],
                limit=6000,
            )
            if str(row.get("voucher_no")) in voucher_names
        ]
        reposting = self.full_documents(
            "Repost Item Valuation",
            filters={"voucher_type": "Purchase Receipt", "voucher_no": receipt},
            limit=100,
        )
        lcv_name = str(prefix["landed_cost_voucher"])
        lcv_documents = self.full_documents(
            "Landed Cost Voucher", filters={"name": lcv_name}, limit=20
        )
        return {
            **documents,
            "supplier_batch": self.get_document(
                "Batch", str(prefix["supplier_batch_id"])
            ),
            "landed_cost_vouchers": lcv_documents,
            "repost_item_valuations": sorted(
                reposting, key=lambda row: str(row.get("name", ""))
            ),
            "stock_ledger_entries": sorted(
                stock_ledger, key=lambda row: str(row.get("name", ""))
            ),
            "gl_entries": sorted(
                gl_entries, key=lambda row: str(row.get("name", ""))
            ),
            "rq_jobs": sorted(
                self.find_background_jobs(lcv_name),
                key=lambda row: str(row.get("name", "")),
            ),
            "settlement_attestation": self.get_delivery(
                str(prefix["attestation_reference"])
            ),
        }


__all__ = ["ERPNextInventoryCostEvidenceCollector"]
