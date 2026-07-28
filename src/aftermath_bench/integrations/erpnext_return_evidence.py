from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from .frappe import FrappeHTTPAdapter


def _data(response: dict[str, Any]) -> Any:
    return response.get("data", response.get("message", response))


class ERPNextPartialReturnEvidenceCollector:
    def __init__(
        self,
        adapter: FrappeHTTPAdapter,
        *,
        event_url: str = "http://127.0.0.1:9092",
    ):
        self.adapter = adapter
        self.event_url = event_url.rstrip("/")

    def get_document(self, doctype: str, name: str) -> dict[str, Any]:
        return dict(_data(self.adapter.get_resource(doctype, name)))

    def list_documents(
        self,
        doctype: str,
        *,
        filters: dict[str, Any] | list[list[Any]] | None = None,
        fields: list[str] | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        summaries = _data(self.adapter.list_resources(
            doctype,
            fields=fields or ["name"],
            filters=filters,
            limit=limit,
        ))
        return [dict(row) for row in summaries]

    def full_documents(
        self,
        doctype: str,
        *,
        filters: dict[str, Any] | list[list[Any]] | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        return [
            self.get_document(doctype, row["name"])
            for row in self.list_documents(
                doctype,
                filters=filters,
                fields=["name"],
                limit=limit,
            )
        ]

    def get_delivery(self, key: str) -> dict[str, Any] | None:
        url = (
            f"{self.event_url}/deliveries/"
            f"{urllib.parse.quote(key, safe='')}"
        )
        request = urllib.request.Request(
            url,
            headers={"Accept": "application/json"},
            method="GET",
        )
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            if error.code == 404:
                return None
            raise

    @staticmethod
    def _references_item_field(
        document: dict[str, Any],
        field: str,
        value: str,
    ) -> bool:
        return any(
            str(item.get(field, "")) == value
            for item in document.get("items", [])
        )

    def collect(self, prefix: dict[str, Any]) -> dict[str, Any]:
        document_fields = {
            "original_purchase_order": "Purchase Order",
            "original_purchase_receipt": "Purchase Receipt",
            "quality_inspection": "Quality Inspection",
            "affected_invoice": "Purchase Invoice",
            "unaffected_invoice": "Purchase Invoice",
            "shared_payment_entry": "Payment Entry",
            "purchase_return": "Purchase Receipt",
            "debit_note": "Purchase Invoice",
            "replacement_purchase_order": "Purchase Order",
            "replacement_purchase_receipt": "Purchase Receipt",
        }
        evidence = {
            key: self.get_document(doctype, str(prefix[key]))
            for key, doctype in document_fields.items()
        }
        purchase_returns = self.full_documents(
            "Purchase Receipt",
            filters={
                "is_return": 1,
                "return_against": prefix["original_purchase_receipt"],
            },
        )
        debit_notes = self.full_documents(
            "Purchase Invoice",
            filters={
                "is_return": 1,
                "return_against": prefix["affected_invoice"],
            },
        )
        all_receipts = self.full_documents("Purchase Receipt")
        replacement_receipts = [
            document
            for document in all_receipts
            if self._references_item_field(
                document,
                "purchase_order",
                str(prefix["replacement_purchase_order"]),
            )
        ]
        all_invoices = self.full_documents("Purchase Invoice")
        replacement_invoices = [
            document
            for document in all_invoices
            if self._references_item_field(
                document,
                "purchase_receipt",
                str(prefix["replacement_purchase_receipt"]),
            )
        ]
        voucher_names = {
            str(prefix["shared_payment_entry"]),
            str(prefix["purchase_return"]),
            str(prefix["debit_note"]),
            str(prefix["replacement_purchase_receipt"]),
            *(
                str(document["name"])
                for document in replacement_invoices
            ),
        }
        stock_ledger = self.list_documents(
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
        jobs = self.list_documents(
            "RQ Job",
            fields=["name", "job_name", "status", "arguments", "queue"],
            limit=500,
        )
        return {
            **evidence,
            "purchase_returns": purchase_returns,
            "debit_notes": debit_notes,
            "replacement_receipts": replacement_receipts,
            "replacement_invoices": replacement_invoices,
            "stock_ledger_entries": stock_ledger,
            "gl_entries": general_ledger,
            "rq_jobs": jobs,
            "pickup_delivery": self.get_delivery(
                str(prefix["purchase_return"])
            ),
        }
