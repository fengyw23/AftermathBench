from __future__ import annotations

import json
import subprocess
import time
from typing import Any, Callable

from aftermath_bench.core import RecordedEnvironment

from .erpnext_faults import ComposeWorkerControl
from .erpnext_relations import find_related_documents
from .erpnext_return_evidence import ERPNextPartialReturnEvidenceCollector
from .erpnext_return_prefix import (
    ERPNextPartialReturnPrefixBuilder,
    _payload,
    ensure_return_replacement_automation,
)
from .erpnext_stack import ERPNextStack
from .frappe import FrappeHTTPAdapter


UNFINISHED_JOB_STATUSES = {
    "queued",
    "started",
    "failed",
    "deferred",
    "scheduled",
}


class ERPNextPartialReturnEnvironment(RecordedEnvironment):
    """Generic, auditable tool boundary for native purchase-return recovery."""

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
        "create_purchase_return",
        "create_debit_note",
        "create_purchase_receipt_from_order",
        "create_purchase_invoice_from_receipt",
        "reconcile_supplier_documents",
        "enqueue_document_webhook",
        "resume_workers",
        "wait_for_external_delivery",
    )
    ALLOWED_DOCUMENT_TYPES = {
        "Purchase Order",
        "Purchase Receipt",
        "Purchase Invoice",
        "Payment Entry",
        "Quality Inspection",
        "Item",
        "Webhook",
    }

    def __init__(
        self,
        *,
        adapter: FrappeHTTPAdapter,
        prefix: dict[str, Any],
        stack: ERPNextStack,
        worker_control: ComposeWorkerControl,
        collector: ERPNextPartialReturnEvidenceCollector | None = None,
    ):
        super().__init__()
        self.adapter = adapter
        self.prefix = prefix
        self.stack = stack
        self.worker_control = worker_control
        self.collector = collector or ERPNextPartialReturnEvidenceCollector(
            adapter
        )

    def list_tools(self) -> tuple[str, ...]:
        return self.TOOL_NAMES

    def snapshot(self) -> dict[str, Any]:
        return self.collector.collect(self.prefix)

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

    def _validate_doctype(self, doctype: str) -> None:
        if doctype not in self.ALLOWED_DOCUMENT_TYPES:
            raise ValueError(f"doctype is not available: {doctype}")

    def invoke(self, tool: str, **kwargs: Any) -> dict[str, Any]:
        operations: dict[str, Callable[[], dict[str, Any]]] = {
            "get_document": lambda: self._get_document(
                str(kwargs["doctype"]),
                str(kwargs["name"]),
            ),
            "list_documents": lambda: self._list_documents(
                str(kwargs["doctype"]),
                kwargs.get("filters"),
            ),
            "list_related_documents": lambda: self._list_related_documents(
                str(kwargs["source_doctype"]),
                str(kwargs["source_name"]),
                str(kwargs["target_doctype"]),
                (
                    str(kwargs["relation_type"])
                    if kwargs.get("relation_type") is not None
                    else None
                ),
            ),
            "get_stock_ledger": lambda: self._ledger(
                "Stock Ledger Entry",
                str(kwargs["voucher_no"]),
            ),
            "get_general_ledger": lambda: self._ledger(
                "GL Entry",
                str(kwargs["voucher_no"]),
            ),
            "find_background_jobs": lambda: self._find_jobs(
                str(kwargs["reference"])
            ),
            "get_external_delivery": lambda: self._get_delivery(
                str(kwargs["reference"])
            ),
            "submit_document": lambda: self._submit(
                str(kwargs["doctype"]),
                str(kwargs["name"]),
            ),
            "cancel_document": lambda: self._cancel(
                str(kwargs["doctype"]),
                str(kwargs["name"]),
            ),
            "create_purchase_return": lambda: self._create_return(
                str(kwargs["purchase_receipt"]),
                dict(kwargs["item_quantities"]),
            ),
            "create_debit_note": lambda: self._create_debit_note(
                str(kwargs["purchase_invoice"]),
                dict(kwargs["item_quantities"]),
            ),
            "create_purchase_receipt_from_order": lambda: (
                self._create_receipt(str(kwargs["purchase_order"]))
            ),
            "create_purchase_invoice_from_receipt": lambda: (
                self._create_invoice(str(kwargs["purchase_receipt"]))
            ),
            "reconcile_supplier_documents": lambda: self._reconcile(
                str(kwargs["company"]),
                str(kwargs["supplier"]),
            ),
            "enqueue_document_webhook": lambda: self._enqueue_webhook(
                str(kwargs["doctype"]),
                str(kwargs["name"]),
                str(kwargs["webhook_name"]),
            ),
            "resume_workers": self._resume_workers,
            "wait_for_external_delivery": lambda: self._wait_for_delivery(
                str(kwargs["reference"]),
                int(kwargs.get("timeout_seconds", 10)),
            ),
        }
        if tool not in operations:
            raise KeyError(f"unknown ERPNext recovery tool: {tool}")
        return self._recorded_call(
            tool,
            dict(kwargs),
            lambda: self._guard(operations[tool]),
        )

    def _get_document(self, doctype: str, name: str) -> dict[str, Any]:
        self._validate_doctype(doctype)
        return {
            "ok": True,
            "doctype": doctype,
            "document": self.collector.get_document(doctype, name),
        }

    def _list_documents(
        self,
        doctype: str,
        filters: Any,
    ) -> dict[str, Any]:
        self._validate_doctype(doctype)
        if filters is not None and not isinstance(filters, (dict, list)):
            raise ValueError("filters must be an object, array, or null")
        return {
            "ok": True,
            "doctype": doctype,
            "filters": filters,
            "documents": self.collector.full_documents(
                doctype,
                filters=filters,
            ),
        }

    def _list_related_documents(
        self,
        source_doctype: str,
        source_name: str,
        target_doctype: str,
        relation_type: str | None,
    ) -> dict[str, Any]:
        self._validate_doctype(source_doctype)
        self._validate_doctype(target_doctype)
        # Reading the source first makes nonexistent identifiers fail
        # explicitly instead of silently producing an empty relation set.
        self.collector.get_document(source_doctype, source_name)
        documents = self.collector.full_documents(
            target_doctype,
            filters=None,
        )
        return {
            "ok": True,
            "source": {
                "doctype": source_doctype,
                "name": source_name,
            },
            "target_doctype": target_doctype,
            "relation_type": relation_type,
            "related": find_related_documents(
                source_doctype=source_doctype,
                source_name=source_name,
                target_doctype=target_doctype,
                documents=documents,
                relation_type=relation_type,
            ),
        }

    def _ledger(self, doctype: str, voucher_no: str) -> dict[str, Any]:
        fields = (
            [
                "name",
                "voucher_type",
                "voucher_no",
                "actual_qty",
                "is_cancelled",
                "item_code",
                "warehouse",
            ]
            if doctype == "Stock Ledger Entry"
            else [
                "name",
                "voucher_type",
                "voucher_no",
                "debit",
                "credit",
                "is_cancelled",
                "account",
            ]
        )
        return {
            "ok": True,
            "doctype": doctype,
            "voucher_no": voucher_no,
            "entries": self.collector.list_documents(
                doctype,
                filters={"voucher_no": voucher_no},
                fields=fields,
                limit=1000,
            ),
        }

    def _find_jobs(self, reference: str) -> dict[str, Any]:
        jobs = self.collector.list_documents(
            "RQ Job",
            fields=["name", "job_name", "status", "arguments", "queue"],
            order_by="creation desc",
            limit=500,
        )
        return {
            "ok": True,
            "reference": reference,
            "jobs": [
                job
                for job in jobs
                if reference in json.dumps(job, sort_keys=True, default=str)
            ],
        }

    def _get_delivery(self, reference: str) -> dict[str, Any]:
        delivery = self.collector.get_delivery(reference)
        return {
            "ok": True,
            "reference": reference,
            "delivered": delivery is not None,
            "delivery": delivery,
        }

    def _submit(self, doctype: str, name: str) -> dict[str, Any]:
        self._validate_doctype(doctype)
        document = _payload(
            self.adapter.submit_document(doctype, name)
        )
        result = {
            "ok": True,
            "doctype": doctype,
            "name": name,
            "document": document,
        }
        if (
            doctype == "Purchase Receipt"
            and name == self.prefix["purchase_return"]
            and int(document.get("docstatus", 0)) == 1
        ):
            result["post_submit_workflow"] = (
                ensure_return_replacement_automation(
                    self.adapter,
                    self.prefix,
                )
            )
        return result

    def _cancel(self, doctype: str, name: str) -> dict[str, Any]:
        self._validate_doctype(doctype)
        return {
            "ok": True,
            "doctype": doctype,
            "name": name,
            "document": _payload(
                self.adapter.cancel_document(doctype, name)
            ),
        }

    @staticmethod
    def _apply_quantities(
        template: dict[str, Any],
        item_quantities: dict[str, Any],
    ) -> None:
        selected = []
        for item in template.get("items", []):
            item_code = str(item.get("item_code"))
            if item_code not in item_quantities:
                continue
            selected_item = dict(item)
            ERPNextPartialReturnPrefixBuilder._set_return_quantity(
                selected_item,
                float(item_quantities[item_code]),
            )
            selected.append(selected_item)
        if len(selected) != len(item_quantities):
            found = {str(item.get("item_code")) for item in selected}
            raise ValueError(
                f"requested items are absent from source: "
                f"{sorted(set(item_quantities) - found)}"
            )
        template["items"] = selected

    def _create_return(
        self,
        purchase_receipt: str,
        item_quantities: dict[str, Any],
    ) -> dict[str, Any]:
        template = _payload(self.adapter.call_method(
            "erpnext.stock.doctype.purchase_receipt.purchase_receipt.make_purchase_return",
            {"source_name": purchase_receipt},
        ))
        self._apply_quantities(template, item_quantities)
        document = _payload(
            self.adapter.create_resource("Purchase Receipt", template)
        )
        return {"ok": True, "document": document}

    def _create_debit_note(
        self,
        purchase_invoice: str,
        item_quantities: dict[str, Any],
    ) -> dict[str, Any]:
        template = _payload(self.adapter.call_method(
            "erpnext.accounts.doctype.purchase_invoice.purchase_invoice.make_debit_note",
            {"source_name": purchase_invoice},
        ))
        self._apply_quantities(template, item_quantities)
        document = _payload(
            self.adapter.create_resource("Purchase Invoice", template)
        )
        return {"ok": True, "document": document}

    def _create_receipt(self, purchase_order: str) -> dict[str, Any]:
        template = _payload(self.adapter.call_method(
            "erpnext.buying.doctype.purchase_order.purchase_order.make_purchase_receipt",
            {"source_name": purchase_order},
        ))
        document = _payload(
            self.adapter.create_resource("Purchase Receipt", template)
        )
        return {"ok": True, "document": document}

    def _create_invoice(self, purchase_receipt: str) -> dict[str, Any]:
        template = _payload(self.adapter.call_method(
            "erpnext.stock.doctype.purchase_receipt.purchase_receipt.make_purchase_invoice",
            {"source_name": purchase_receipt},
        ))
        document = _payload(
            self.adapter.create_resource("Purchase Invoice", template)
        )
        return {"ok": True, "document": document}

    def _reconcile(self, company: str, supplier: str) -> dict[str, Any]:
        result = self.stack.reconcile_supplier_documents(
            company=company,
            supplier=supplier,
        )
        return {"ok": True, **result}

    def _enqueue_webhook(
        self,
        doctype: str,
        name: str,
        webhook_name: str,
    ) -> dict[str, Any]:
        self._validate_doctype(doctype)
        result = self.stack.enqueue_document_webhook(
            doctype=doctype,
            document_name=name,
            webhook_name=webhook_name,
        )
        return {"ok": True, **result}

    def _resume_workers(self) -> dict[str, Any]:
        self.worker_control.start()
        return {"ok": True, "status": "started"}

    def _wait_for_delivery(
        self,
        reference: str,
        timeout_seconds: int,
    ) -> dict[str, Any]:
        if timeout_seconds < 1 or timeout_seconds > 30:
            raise ValueError("timeout_seconds must be between 1 and 30")
        deadline = time.monotonic() + timeout_seconds
        delivery = None
        jobs: list[dict[str, Any]] = []
        while True:
            delivery = self.collector.get_delivery(reference)
            jobs = self._find_jobs(reference)["jobs"]
            unfinished = [
                job
                for job in jobs
                if str(job.get("status", "")).lower()
                in UNFINISHED_JOB_STATUSES
            ]
            if delivery is not None and not unfinished:
                break
            if time.monotonic() >= deadline:
                break
            time.sleep(0.25)
        return {
            "ok": True,
            "reference": reference,
            "delivered": delivery is not None,
            "delivery": delivery,
            "jobs": jobs,
        }


def reference_partial_return_recovery(
    environment: ERPNextPartialReturnEnvironment,
) -> tuple[dict[str, Any], ...]:
    """Reference policy composed exclusively from model-visible tools."""
    prefix = environment.prefix
    trace: list[dict[str, Any]] = []

    def call(tool: str, **kwargs: Any) -> dict[str, Any]:
        result = environment.invoke(tool, **kwargs)
        trace.append({"tool": tool, "arguments": kwargs, "result": result})
        if not result.get("ok"):
            raise RuntimeError(f"reference tool failed: {tool}: {result}")
        return result

    purchase_return = call(
        "get_document",
        doctype="Purchase Receipt",
        name=prefix["purchase_return"],
    )["document"]
    debit_note = call(
        "get_document",
        doctype="Purchase Invoice",
        name=prefix["debit_note"],
    )["document"]
    replacement_receipt = call(
        "get_document",
        doctype="Purchase Receipt",
        name=prefix["replacement_purchase_receipt"],
    )["document"]
    call(
        "get_document",
        doctype="Payment Entry",
        name=prefix["shared_payment_entry"],
    )
    call(
        "get_document",
        doctype="Quality Inspection",
        name=prefix["quality_inspection"],
    )

    if int(purchase_return.get("docstatus", 0)) == 0:
        call(
            "submit_document",
            doctype="Purchase Receipt",
            name=prefix["purchase_return"],
        )
    replacement_receipt = call(
        "get_document",
        doctype="Purchase Receipt",
        name=prefix["replacement_purchase_receipt"],
    )["document"]
    if int(debit_note.get("docstatus", 0)) == 0:
        call(
            "submit_document",
            doctype="Purchase Invoice",
            name=prefix["debit_note"],
        )
    if int(replacement_receipt.get("docstatus", 0)) == 0:
        call(
            "submit_document",
            doctype="Purchase Receipt",
            name=prefix["replacement_purchase_receipt"],
        )

    invoices = call(
        "list_documents",
        doctype="Purchase Invoice",
        filters=None,
    )["documents"]
    replacement_invoices = [
        invoice
        for invoice in invoices
        if any(
            item.get("purchase_receipt")
            == prefix["replacement_purchase_receipt"]
            for item in invoice.get("items", [])
        )
        and int(invoice.get("docstatus", 0)) != 2
    ]
    if not replacement_invoices:
        replacement_invoice = call(
            "create_purchase_invoice_from_receipt",
            purchase_receipt=prefix["replacement_purchase_receipt"],
        )["document"]
    elif len(replacement_invoices) == 1:
        replacement_invoice = replacement_invoices[0]
    else:
        raise RuntimeError("duplicate active replacement invoices")
    if int(replacement_invoice.get("docstatus", 0)) == 0:
        call(
            "submit_document",
            doctype="Purchase Invoice",
            name=replacement_invoice["name"],
        )
    call(
        "reconcile_supplier_documents",
        company=prefix["company"],
        supplier=prefix["supplier"],
    )

    delivery = call(
        "get_external_delivery",
        reference=prefix["purchase_return"],
    )
    jobs = call(
        "find_background_jobs",
        reference=prefix["purchase_return"],
    )["jobs"]
    if not delivery["delivered"]:
        if any(
            str(job.get("status", "")).lower()
            in UNFINISHED_JOB_STATUSES
            for job in jobs
        ):
            call("resume_workers")
        else:
            call(
                "enqueue_document_webhook",
                doctype="Purchase Receipt",
                name=prefix["purchase_return"],
                webhook_name=ERPNextPartialReturnPrefixBuilder.PICKUP_WEBHOOK,
            )
        call(
            "wait_for_external_delivery",
            reference=prefix["purchase_return"],
            timeout_seconds=30,
        )
    call(
        "get_stock_ledger",
        voucher_no=prefix["purchase_return"],
    )
    call(
        "get_stock_ledger",
        voucher_no=prefix["replacement_purchase_receipt"],
    )
    for voucher_no in (
        prefix["shared_payment_entry"],
        prefix["purchase_return"],
        prefix["debit_note"],
    ):
        call("get_general_ledger", voucher_no=voucher_no)
    return tuple(trace)
