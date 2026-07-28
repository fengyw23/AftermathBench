from __future__ import annotations

import json
import subprocess
import time
from typing import Any, Callable

from aftermath_bench.core import RecordedEnvironment

from .erpnext_evidence import ERPNextEvidenceCollector, ProcurementPaymentIDs
from .erpnext_faults import ComposeWorkerControl
from .erpnext_stack import ERPNextStack
from .frappe import FrappeHTTPAdapter


UNFINISHED_JOB_STATUSES = {
    "queued",
    "started",
    "failed",
    "deferred",
    "scheduled",
}


def _data(response: dict[str, Any]) -> Any:
    return response.get("data", response.get("message", response))


def _document(response: dict[str, Any]) -> dict[str, Any]:
    value = _data(response)
    if not isinstance(value, dict):
        raise RuntimeError(f"expected a document response, got {value!r}")
    return value


class ERPNextRecoveryEnvironment(RecordedEnvironment):
    """Restricted agent boundary over the admitted native ERPNext runtime."""

    TOOL_NAMES = (
        "get_purchase_order",
        "get_purchase_receipt",
        "get_purchase_invoice",
        "get_payment_entry",
        "find_payments_for_invoice",
        "get_payment_ledger",
        "find_remittance_jobs",
        "get_remittance_delivery",
        "submit_payment_entry",
        "requeue_payment_remittance",
        "resume_remittance_workers",
        "wait_for_remittance_delivery",
    )

    def __init__(
        self,
        *,
        adapter: FrappeHTTPAdapter,
        ids: ProcurementPaymentIDs,
        payment_entry: str,
        stack: ERPNextStack,
        worker_control: ComposeWorkerControl,
        collector: ERPNextEvidenceCollector | None = None,
    ):
        super().__init__()
        self.adapter = adapter
        self.ids = ids
        self.payment_entry = payment_entry
        self.stack = stack
        self.worker_control = worker_control
        self.collector = collector or ERPNextEvidenceCollector(adapter)

    def list_tools(self) -> tuple[str, ...]:
        return self.TOOL_NAMES

    def snapshot(self) -> dict[str, Any]:
        return self.collector.collect(self.ids)

    @staticmethod
    def _guard(operation: Callable[[], dict[str, Any]]) -> dict[str, Any]:
        try:
            return operation()
        except (
            KeyError,
            OSError,
            RuntimeError,
            TypeError,
            ValueError,
            subprocess.CalledProcessError,
        ) as error:
            return {
                "ok": False,
                "error": str(error),
                "exception_type": type(error).__name__,
            }

    def invoke(self, tool: str, **kwargs: Any) -> dict[str, Any]:
        operations: dict[str, Callable[[], dict[str, Any]]] = {
            "get_purchase_order": lambda: self._get_document(
                "Purchase Order",
                str(kwargs["purchase_order"]),
            ),
            "get_purchase_receipt": lambda: self._get_document(
                "Purchase Receipt",
                str(kwargs["purchase_receipt"]),
            ),
            "get_purchase_invoice": lambda: self._get_document(
                "Purchase Invoice",
                str(kwargs["purchase_invoice"]),
            ),
            "get_payment_entry": lambda: self._get_document(
                "Payment Entry",
                str(kwargs["payment_entry"]),
            ),
            "find_payments_for_invoice": lambda: self._find_payments(
                str(kwargs["purchase_invoice"])
            ),
            "get_payment_ledger": lambda: self._get_payment_ledger(
                str(kwargs["payment_entry"])
            ),
            "find_remittance_jobs": lambda: self._find_remittance_jobs(
                str(kwargs["payment_entry"])
            ),
            "get_remittance_delivery": lambda: self._get_remittance_delivery(
                str(kwargs["payment_entry"])
            ),
            "submit_payment_entry": lambda: self._submit_payment(
                str(kwargs["payment_entry"])
            ),
            "requeue_payment_remittance": lambda: self._requeue_remittance(
                str(kwargs["payment_entry"])
            ),
            "resume_remittance_workers": self._resume_workers,
            "wait_for_remittance_delivery": lambda: self._wait_for_remittance(
                str(kwargs["payment_entry"]),
                int(kwargs.get("timeout_seconds", 10)),
            ),
        }
        if tool not in operations:
            raise KeyError(f"unknown ERPNext recovery tool: {tool}")
        arguments = dict(kwargs)
        return self._recorded_call(
            tool,
            arguments,
            lambda: self._guard(operations[tool]),
        )

    def _get_document(self, doctype: str, name: str) -> dict[str, Any]:
        document = _document(self.adapter.get_resource(doctype, name))
        return {"ok": True, "doctype": doctype, "document": document}

    def _find_payments(self, invoice_name: str) -> dict[str, Any]:
        summaries = _data(self.adapter.list_resources(
            "Payment Entry",
            fields=["name", "docstatus", "paid_amount", "party"],
            limit=100,
        ))
        payments = []
        for summary in summaries:
            payment = _document(
                self.adapter.get_resource("Payment Entry", summary["name"])
            )
            if any(
                reference.get("reference_doctype") == "Purchase Invoice"
                and reference.get("reference_name") == invoice_name
                for reference in payment.get("references", [])
            ):
                payments.append(payment)
        return {
            "ok": True,
            "purchase_invoice": invoice_name,
            "payments": payments,
        }

    def _get_payment_ledger(self, payment_name: str) -> dict[str, Any]:
        rows = _data(self.adapter.list_resources(
            "GL Entry",
            fields=[
                "name",
                "voucher_no",
                "debit",
                "credit",
                "is_cancelled",
                "account",
            ],
            filters={"voucher_no": payment_name},
            limit=500,
        ))
        return {
            "ok": True,
            "payment_entry": payment_name,
            "gl_entries": rows,
        }

    def _find_remittance_jobs(self, payment_name: str) -> dict[str, Any]:
        relevant = self._list_relevant_jobs(payment_name)
        return {
            "ok": True,
            "payment_entry": payment_name,
            "jobs": relevant,
        }

    def _list_relevant_jobs(
        self,
        payment_name: str,
    ) -> list[dict[str, Any]]:
        jobs = _data(self.adapter.list_resources(
            "RQ Job",
            fields=["name", "job_name", "status", "arguments", "queue"],
            order_by="creation desc",
            limit=500,
        ))
        relevant = [
            dict(job)
            for job in jobs
            if payment_name in json.dumps(
                job,
                sort_keys=True,
                default=str,
            )
        ]
        return relevant

    def _get_remittance_delivery(self, payment_name: str) -> dict[str, Any]:
        delivery = self.collector.get_remittance_delivery(payment_name)
        return {
            "ok": True,
            "payment_entry": payment_name,
            "delivered": delivery is not None,
            "delivery": delivery,
        }

    def _submit_payment(self, payment_name: str) -> dict[str, Any]:
        submitted = _data(
            self.adapter.submit_document("Payment Entry", payment_name)
        )
        return {
            "ok": True,
            "payment_entry": payment_name,
            "submitted": submitted,
        }

    def _requeue_remittance(self, payment_name: str) -> dict[str, Any]:
        queued = self.stack.requeue_payment_remittance(payment_name)
        return {"ok": True, **queued}

    def _resume_workers(self) -> dict[str, Any]:
        self.worker_control.start()
        return {
            "ok": True,
            "workers": ["queue-short", "queue-long"],
            "status": "started",
        }

    def _wait_for_remittance(
        self,
        payment_name: str,
        timeout_seconds: int,
    ) -> dict[str, Any]:
        if timeout_seconds < 1 or timeout_seconds > 30:
            raise ValueError("timeout_seconds must be between 1 and 30")
        deadline = time.monotonic() + timeout_seconds
        delivery = None
        relevant_jobs: list[dict[str, Any]] = []
        unfinished_jobs: list[dict[str, Any]] = []
        while True:
            delivery = self.collector.get_remittance_delivery(payment_name)
            relevant_jobs = self._list_relevant_jobs(payment_name)
            unfinished_jobs = [
                job
                for job in relevant_jobs
                if str(job.get("status", "")).lower()
                in UNFINISHED_JOB_STATUSES
            ]
            if delivery is not None and not unfinished_jobs:
                break
            if time.monotonic() >= deadline:
                break
            time.sleep(0.25)
        return {
            "ok": True,
            "payment_entry": payment_name,
            "delivered": delivery is not None,
            "delivery": delivery,
            "jobs_settled": not unfinished_jobs,
            "relevant_jobs": relevant_jobs,
        }


def reference_erpnext_recovery(
    environment: ERPNextRecoveryEnvironment,
) -> tuple[dict[str, Any], ...]:
    """State-driven recovery control using only model-visible tools."""
    results: list[dict[str, Any]] = []

    def call(tool: str, **kwargs: Any) -> dict[str, Any]:
        result = environment.invoke(tool, **kwargs)
        results.append({"tool": tool, "arguments": kwargs, "result": result})
        if not result.get("ok"):
            raise RuntimeError(f"reference tool failed: {tool}: {result}")
        return result

    call("get_purchase_order", purchase_order=environment.ids.purchase_order)
    call(
        "get_purchase_receipt",
        purchase_receipt=environment.ids.purchase_receipt,
    )
    invoice = call(
        "get_purchase_invoice",
        purchase_invoice=environment.ids.purchase_invoice,
    )["document"]
    payment = call(
        "get_payment_entry",
        payment_entry=environment.payment_entry,
    )["document"]
    call(
        "find_payments_for_invoice",
        purchase_invoice=invoice["name"],
    )
    call("get_payment_ledger", payment_entry=environment.payment_entry)
    delivery = call(
        "get_remittance_delivery",
        payment_entry=environment.payment_entry,
    )
    jobs = call(
        "find_remittance_jobs",
        payment_entry=environment.payment_entry,
    )["jobs"]

    if int(payment.get("docstatus", 0)) == 0:
        call(
            "submit_payment_entry",
            payment_entry=environment.payment_entry,
        )
    elif delivery["delivered"]:
        return tuple(results)
    elif any(
        str(job.get("status", "")).lower() in UNFINISHED_JOB_STATUSES
        for job in jobs
    ):
        call("resume_remittance_workers")
    else:
        call(
            "requeue_payment_remittance",
            payment_entry=environment.payment_entry,
        )

    call(
        "wait_for_remittance_delivery",
        payment_entry=environment.payment_entry,
        timeout_seconds=30,
    )
    return tuple(results)
