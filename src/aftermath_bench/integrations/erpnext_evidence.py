from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

from .frappe import FrappeHTTPAdapter


def _data(response: dict[str, Any]) -> Any:
    return response.get("data", response.get("message", response))


@dataclass(frozen=True)
class ProcurementPaymentIDs:
    purchase_order: str
    purchase_receipt: str
    purchase_invoice: str


class ERPNextEvidenceCollector:
    def __init__(
        self,
        adapter: FrappeHTTPAdapter,
        *,
        remittance_url: str = "http://127.0.0.1:9092",
    ):
        self.adapter = adapter
        self.remittance_url = remittance_url.rstrip("/")

    def _get(self, doctype: str, name: str) -> dict[str, Any]:
        return dict(_data(self.adapter.get_resource(doctype, name)))

    def _list(
        self,
        doctype: str,
        *,
        fields: list[str],
        filters: list[list[Any]] | dict[str, Any] | None = None,
        order_by: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        response = self.adapter.list_resources(
            doctype,
            fields=fields,
            filters=filters,
            order_by=order_by,
            limit=limit,
        )
        return [dict(item) for item in _data(response)]

    def _remittance(self, payment_name: str) -> dict[str, Any] | None:
        url = (
            f"{self.remittance_url}/deliveries/"
            f"{urllib.parse.quote(payment_name, safe='')}"
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

    def get_remittance_delivery(
        self,
        payment_name: str,
    ) -> dict[str, Any] | None:
        return self._remittance(payment_name)

    def collect(self, ids: ProcurementPaymentIDs) -> dict[str, Any]:
        purchase_order = self._get("Purchase Order", ids.purchase_order)
        receipt = self._get("Purchase Receipt", ids.purchase_receipt)
        invoice = self._get("Purchase Invoice", ids.purchase_invoice)

        payment_summaries = self._list(
            "Payment Entry",
            fields=["name", "docstatus", "paid_amount", "party"],
        )
        payments = [
            self._get("Payment Entry", summary["name"])
            for summary in payment_summaries
        ]
        relevant_payments = [
            payment
            for payment in payments
            if any(
                reference.get("reference_doctype") == "Purchase Invoice"
                and reference.get("reference_name") == ids.purchase_invoice
                for reference in payment.get("references", [])
            )
        ]

        stock_rows = self._list(
            "Stock Ledger Entry",
            fields=[
                "name",
                "voucher_no",
                "actual_qty",
                "is_cancelled",
                "item_code",
                "warehouse",
            ],
            filters={"voucher_no": ids.purchase_receipt},
        )
        payment_names = {payment["name"] for payment in relevant_payments}
        gl_rows = self._list(
            "GL Entry",
            fields=[
                "name",
                "voucher_no",
                "debit",
                "credit",
                "is_cancelled",
                "account",
            ],
            limit=500,
        )
        payment_gl = [
            row for row in gl_rows if row.get("voucher_no") in payment_names
        ]
        jobs = self._list(
            "RQ Job",
            fields=["name", "job_name", "status", "arguments", "queue"],
            order_by="creation desc",
            limit=500,
        )

        submitted = [
            payment
            for payment in relevant_payments
            if int(payment.get("docstatus", 0)) == 1
        ]
        remittance = (
            self._remittance(str(submitted[0]["name"]))
            if len(submitted) == 1
            else None
        )
        return {
            "purchase_order": purchase_order,
            "purchase_receipt": receipt,
            "purchase_invoice": invoice,
            "payment_entries": relevant_payments,
            "stock_ledger_entries": stock_rows,
            "gl_entries": payment_gl,
            "rq_jobs": jobs,
            "remittance": remittance,
        }
