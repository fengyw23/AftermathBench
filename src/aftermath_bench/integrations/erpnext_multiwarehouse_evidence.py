from __future__ import annotations

import json
from typing import Any

from .erpnext_return_evidence import ERPNextPartialReturnEvidenceCollector
from .frappe import FrappeHTTPAdapter


class ERPNextMultiwarehouseEvidenceCollector(ERPNextPartialReturnEvidenceCollector):
    """Collect transfer, reservation, traceability and reposting closure."""

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
            "material_request": "Material Request",
            "outgoing_stock_entry": "Stock Entry",
            "clinic_sales_order": "Sales Order",
            "protected_sales_order": "Sales Order",
            "protected_pick_list": "Pick List",
            "protected_reservation": "Stock Reservation Entry",
        }
        documents = {
            key: self.get_document(doctype, str(prefix[key]))
            for key, doctype in document_fields.items()
        }
        second_legs = self.full_documents(
            "Stock Entry",
            filters={"outgoing_stock_entry": prefix["outgoing_stock_entry"]},
            limit=20,
        )
        reservations = self.full_documents(
            "Stock Reservation Entry",
            filters=[
                [
                    "voucher_no",
                    "in",
                    [prefix["clinic_sales_order"], prefix["protected_sales_order"]],
                ]
            ],
            limit=50,
        )
        voucher_names = {
            str(prefix["stock_seed"]),
            str(prefix["outgoing_stock_entry"]),
            *(str(document.get("name")) for document in second_legs),
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
        bins = self.list_documents(
            "Bin",
            fields=[
                "name",
                "item_code",
                "warehouse",
                "actual_qty",
                "reserved_qty",
                "reserved_stock",
            ],
            filters=[
                [
                    "item_code",
                    "in",
                    [prefix["transfer_item"], prefix["protected_item"]],
                ]
            ],
            limit=100,
        )
        reposts = [
            document
            for document in self.full_documents("Repost Item Valuation", limit=100)
            if str(document.get("voucher_no")) in voucher_names
        ]
        batch = self.get_document("Batch", str(prefix["batch_id"]))
        bundles = self.full_documents("Serial and Batch Bundle", limit=100)
        relevant_bundles = [
            document
            for document in bundles
            if str(document.get("voucher_no")) in voucher_names
            or str(document.get("name"))
            in {
                str(row.get("serial_and_batch_bundle"))
                for row in stock_ledger
                if row.get("serial_and_batch_bundle")
            }
        ]
        second_leg_names = {
            str(document.get("name")) for document in second_legs
        }
        jobs = [
            job
            for job in self.list_documents(
                "RQ Job",
                fields=["name", "job_name", "status", "arguments", "queue"],
                order_by="creation desc",
                limit=500,
            )
            if any(
                name and name in json.dumps(job, sort_keys=True, default=str)
                for name in second_leg_names
            )
        ]
        deliveries = {
            name: self.get_delivery(name)
            for name in second_leg_names
            if name
        }
        return {
            **documents,
            "second_leg_stock_entries": sorted(
                second_legs, key=lambda row: str(row.get("name", ""))
            ),
            "stock_reservation_entries": sorted(
                reservations, key=lambda row: str(row.get("name", ""))
            ),
            "stock_ledger_entries": sorted(
                stock_ledger, key=lambda row: str(row.get("name", ""))
            ),
            "bins": sorted(
                bins,
                key=lambda row: (
                    str(row.get("item_code", "")),
                    str(row.get("warehouse", "")),
                ),
            ),
            "repost_item_valuations": sorted(
                reposts, key=lambda row: str(row.get("name", ""))
            ),
            "batch": batch,
            "serial_and_batch_bundles": sorted(
                relevant_bundles, key=lambda row: str(row.get("name", ""))
            ),
            "rq_jobs": sorted(jobs, key=lambda row: str(row.get("name", ""))),
            "arrival_deliveries": deliveries,
        }


__all__ = ["ERPNextMultiwarehouseEvidenceCollector"]
