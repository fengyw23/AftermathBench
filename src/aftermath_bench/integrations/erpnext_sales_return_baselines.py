from __future__ import annotations

from typing import Any

from .erpnext_return_agent import UNFINISHED_JOB_STATUSES
from .erpnext_sales_return_agent import ERPNextSalesReturnEnvironment
from .erpnext_sales_return_prefix import ERPNextSalesReturnPrefixBuilder

BASELINE_NAMES = (
    "no_op",
    "blind_retry",
    "assume_committed",
    "repair_failed_record_only",
    "all_rollback",
    "cancel_shared_payment",
    "compact_boundary_tree",
)


def _call(
    environment: ERPNextSalesReturnEnvironment,
    trace: list[dict[str, Any]],
    tool: str,
    **arguments: Any,
) -> dict[str, Any]:
    result = environment.invoke(tool, **arguments)
    trace.append(
        {"tool": tool, "arguments": arguments, "result": result}
    )
    return result


def _complete_downstream_naively(
    environment: ERPNextSalesReturnEnvironment,
    prefix: dict[str, Any],
    trace: list[dict[str, Any]],
) -> None:
    _call(
        environment,
        trace,
        "submit_document",
        doctype="Sales Invoice",
        name=prefix["credit_note"],
    )
    _call(
        environment,
        trace,
        "submit_document",
        doctype="Delivery Note",
        name=prefix["replacement_delivery_note"],
    )
    invoice = _call(
        environment,
        trace,
        "create_sales_invoice_from_delivery",
        delivery_note=prefix["replacement_delivery_note"],
    )
    document = invoice.get("document")
    if invoice.get("ok") and isinstance(document, dict):
        _call(
            environment,
            trace,
            "submit_document",
            doctype="Sales Invoice",
            name=document["name"],
        )
    _call(
        environment,
        trace,
        "reconcile_customer_documents",
        company=prefix["company"],
        customer=prefix["customer"],
    )


def _resolve_boundary_only(
    environment: ERPNextSalesReturnEnvironment,
    prefix: dict[str, Any],
    trace: list[dict[str, Any]],
) -> None:
    sales_return = _call(
        environment,
        trace,
        "get_document",
        doctype="Delivery Note",
        name=prefix["sales_return"],
    ).get("document", {})
    if int(sales_return.get("docstatus", 0)) == 0:
        _call(
            environment,
            trace,
            "submit_document",
            doctype="Delivery Note",
            name=prefix["sales_return"],
        )
    delivery = _call(
        environment,
        trace,
        "get_external_delivery",
        reference=prefix["sales_return"],
    )
    jobs = _call(
        environment,
        trace,
        "find_background_jobs",
        reference=prefix["sales_return"],
    ).get("jobs", [])
    if not delivery.get("delivered"):
        if any(
            str(job.get("status", "")).lower()
            in UNFINISHED_JOB_STATUSES
            for job in jobs
        ):
            _call(environment, trace, "resume_workers")
        else:
            _call(
                environment,
                trace,
                "enqueue_document_webhook",
                doctype="Delivery Note",
                name=prefix["sales_return"],
                webhook_name=ERPNextSalesReturnPrefixBuilder.PICKUP_WEBHOOK,
            )
        _call(
            environment,
            trace,
            "wait_for_external_delivery",
            reference=prefix["sales_return"],
            timeout_seconds=30,
        )


def run_fixed_sales_return_baseline(
    name: str,
    *,
    environment: ERPNextSalesReturnEnvironment,
    prefix: dict[str, Any],
) -> tuple[dict[str, Any], ...]:
    """Execute a deliberately fixed heuristic against the native state."""
    if name not in BASELINE_NAMES:
        raise ValueError(f"unknown fixed sales-return baseline: {name}")
    trace: list[dict[str, Any]] = []
    if name == "no_op":
        return ()
    if name == "blind_retry":
        retry = _call(
            environment,
            trace,
            "submit_document",
            doctype="Delivery Note",
            name=prefix["sales_return"],
        )
        if retry.get("ok"):
            _complete_downstream_naively(environment, prefix, trace)
            _call(
                environment,
                trace,
                "wait_for_external_delivery",
                reference=prefix["sales_return"],
                timeout_seconds=30,
            )
        return tuple(trace)
    if name == "assume_committed":
        _complete_downstream_naively(environment, prefix, trace)
        return tuple(trace)
    if name == "repair_failed_record_only":
        _resolve_boundary_only(environment, prefix, trace)
        return tuple(trace)
    if name == "all_rollback":
        for doctype, document_name in (
            ("Payment Entry", prefix["shared_payment_entry"]),
            ("Sales Invoice", prefix["unaffected_invoice"]),
            ("Sales Invoice", prefix["affected_invoice"]),
            ("Delivery Note", prefix["original_delivery_note"]),
        ):
            _call(
                environment,
                trace,
                "cancel_document",
                doctype=doctype,
                name=document_name,
            )
        return tuple(trace)
    if name == "cancel_shared_payment":
        _call(
            environment,
            trace,
            "cancel_document",
            doctype="Payment Entry",
            name=prefix["shared_payment_entry"],
        )
        return tuple(trace)
    _resolve_boundary_only(environment, prefix, trace)
    _complete_downstream_naively(environment, prefix, trace)
    return tuple(trace)
