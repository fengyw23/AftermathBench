from __future__ import annotations

from collections.abc import Callable
from typing import Any, ClassVar

from .erpnext_faults import ComposeWorkerControl
from .erpnext_return_agent import ERPNextPartialReturnEnvironment
from .erpnext_return_prefix import _payload
from .erpnext_sales_return_evidence import (
    ERPNextSalesReturnEvidenceCollector,
)
from .erpnext_sales_return_prefix import (
    ERPNextSalesReturnPrefixBuilder,
    ensure_sales_exchange_automation,
)
from .erpnext_stack import ERPNextStack
from .frappe import FrappeHTTPAdapter


class ERPNextSalesReturnEnvironment(ERPNextPartialReturnEnvironment):
    """Auditable tool boundary for native customer return recovery."""

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
        "create_sales_return",
        "create_credit_note",
        "create_delivery_note_from_order",
        "create_sales_invoice_from_delivery",
        "reconcile_customer_documents",
        "enqueue_document_webhook",
        "resume_workers",
        "wait_for_external_delivery",
    )
    ALLOWED_DOCUMENT_TYPES: ClassVar[set[str]] = {
        "Sales Order",
        "Delivery Note",
        "Sales Invoice",
        "Payment Entry",
        "Quality Inspection",
        "Stock Entry",
        "Item",
        "Customer",
        "Webhook",
    }

    def __init__(
        self,
        *,
        adapter: FrappeHTTPAdapter,
        prefix: dict[str, Any],
        stack: ERPNextStack,
        worker_control: ComposeWorkerControl,
        collector: ERPNextSalesReturnEvidenceCollector | None = None,
    ) -> None:
        super().__init__(
            adapter=adapter,
            prefix=prefix,
            stack=stack,
            worker_control=worker_control,
            collector=collector
            or ERPNextSalesReturnEvidenceCollector(adapter),
        )

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
            "submit_document": lambda: self._submit_sales_document(
                str(kwargs["doctype"]),
                str(kwargs["name"]),
            ),
            "cancel_document": lambda: self._cancel(
                str(kwargs["doctype"]),
                str(kwargs["name"]),
            ),
            "create_sales_return": lambda: self._create_sales_return(
                str(kwargs["delivery_note"]),
                dict(kwargs["item_quantities"]),
            ),
            "create_credit_note": lambda: self._create_credit_note(
                str(kwargs["sales_invoice"]),
                dict(kwargs["item_quantities"]),
            ),
            "create_delivery_note_from_order": lambda: (
                self._create_delivery(str(kwargs["sales_order"]))
            ),
            "create_sales_invoice_from_delivery": lambda: (
                self._create_invoice(str(kwargs["delivery_note"]))
            ),
            "reconcile_customer_documents": lambda: (
                self._reconcile_customer(
                    str(kwargs["company"]),
                    str(kwargs["customer"]),
                )
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
            raise KeyError(f"unknown ERPNext sales recovery tool: {tool}")
        return self._recorded_call(
            tool,
            dict(kwargs),
            lambda: self._guard(operations[tool]),
        )

    def _submit_sales_document(
        self,
        doctype: str,
        name: str,
    ) -> dict[str, Any]:
        self._validate_doctype(doctype)
        document = _payload(self.adapter.submit_document(doctype, name))
        result: dict[str, Any] = {
            "ok": True,
            "doctype": doctype,
            "name": name,
            "document": document,
        }
        if (
            doctype == "Delivery Note"
            and name == self.prefix["sales_return"]
            and int(document.get("docstatus", 0)) == 1
        ):
            result["post_submit_workflow"] = ensure_sales_exchange_automation(
                self.adapter,
                self.prefix,
            )
        return result

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
            ERPNextSalesReturnPrefixBuilder._set_return_quantity(
                selected_item,
                float(item_quantities[item_code]),
            )
            selected.append(selected_item)
        if len(selected) != len(item_quantities):
            found = {str(item.get("item_code")) for item in selected}
            raise ValueError(
                "requested items are absent from source: "
                f"{sorted(set(item_quantities) - found)}"
            )
        template["items"] = selected

    def _create_sales_return(
        self,
        delivery_note: str,
        item_quantities: dict[str, Any],
    ) -> dict[str, Any]:
        template = _payload(
            self.adapter.call_method(
                "erpnext.stock.doctype.delivery_note.delivery_note.make_sales_return",
                {"source_name": delivery_note},
            )
        )
        self._apply_quantities(template, item_quantities)
        document = _payload(
            self.adapter.create_resource("Delivery Note", template)
        )
        return {"ok": True, "document": document}

    def _create_credit_note(
        self,
        sales_invoice: str,
        item_quantities: dict[str, Any],
    ) -> dict[str, Any]:
        template = _payload(
            self.adapter.call_method(
                "erpnext.accounts.doctype.sales_invoice.sales_invoice.make_sales_return",
                {"source_name": sales_invoice},
            )
        )
        self._apply_quantities(template, item_quantities)
        document = _payload(
            self.adapter.create_resource("Sales Invoice", template)
        )
        return {"ok": True, "document": document}

    def _create_delivery(self, sales_order: str) -> dict[str, Any]:
        template = _payload(
            self.adapter.call_method(
                "erpnext.selling.doctype.sales_order.sales_order.make_delivery_note",
                {"source_name": sales_order},
            )
        )
        document = _payload(
            self.adapter.create_resource("Delivery Note", template)
        )
        return {"ok": True, "document": document}

    def _create_invoice(self, delivery_note: str) -> dict[str, Any]:
        template = _payload(
            self.adapter.call_method(
                "erpnext.stock.doctype.delivery_note.delivery_note.make_sales_invoice",
                {"source_name": delivery_note},
            )
        )
        document = _payload(
            self.adapter.create_resource("Sales Invoice", template)
        )
        return {"ok": True, "document": document}

    def _reconcile_customer(
        self,
        company: str,
        customer: str,
    ) -> dict[str, Any]:
        return {
            "ok": True,
            **self.stack.reconcile_customer_documents(
                company=company,
                customer=customer,
            ),
        }
