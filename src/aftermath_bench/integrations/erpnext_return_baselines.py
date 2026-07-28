from __future__ import annotations

from typing import Any, Callable

from .erpnext_return_agent import (
    ERPNextPartialReturnEnvironment,
    UNFINISHED_JOB_STATUSES,
)
from .erpnext_return_prefix import ERPNextPartialReturnPrefixBuilder


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
    environment: ERPNextPartialReturnEnvironment,
    trace: list[dict[str, Any]],
    tool: str,
    **arguments: Any,
) -> dict[str, Any]:
    result = environment.invoke(tool, **arguments)
    trace.append(
        {"tool": tool, "arguments": arguments, "result": result}
    )
    return result


def _complete_downstream(
    environment: ERPNextPartialReturnEnvironment,
    prefix: dict[str, Any],
    trace: list[dict[str, Any]],
) -> None:
    _call(
        environment,
        trace,
        "submit_document",
        doctype="Purchase Invoice",
        name=prefix["debit_note"],
    )
    _call(
        environment,
        trace,
        "submit_document",
        doctype="Purchase Receipt",
        name=prefix["replacement_purchase_receipt"],
    )
    invoice = _call(
        environment,
        trace,
        "create_purchase_invoice_from_receipt",
        purchase_receipt=prefix["replacement_purchase_receipt"],
    )
    document = invoice.get("document")
    if invoice.get("ok") and isinstance(document, dict):
        _call(
            environment,
            trace,
            "submit_document",
            doctype="Purchase Invoice",
            name=document["name"],
        )
    _call(
        environment,
        trace,
        "reconcile_supplier_documents",
        company=prefix["company"],
        supplier=prefix["supplier"],
    )


def _resolve_boundary_only(
    environment: ERPNextPartialReturnEnvironment,
    prefix: dict[str, Any],
    trace: list[dict[str, Any]],
) -> None:
    purchase_return = _call(
        environment,
        trace,
        "get_document",
        doctype="Purchase Receipt",
        name=prefix["purchase_return"],
    ).get("document", {})
    if int(purchase_return.get("docstatus", 0)) == 0:
        _call(
            environment,
            trace,
            "submit_document",
            doctype="Purchase Receipt",
            name=prefix["purchase_return"],
        )
    delivery = _call(
        environment,
        trace,
        "get_external_delivery",
        reference=prefix["purchase_return"],
    )
    jobs = _call(
        environment,
        trace,
        "find_background_jobs",
        reference=prefix["purchase_return"],
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
                doctype="Purchase Receipt",
                name=prefix["purchase_return"],
                webhook_name=(
                    ERPNextPartialReturnPrefixBuilder.PICKUP_WEBHOOK
                ),
            )
        _call(
            environment,
            trace,
            "wait_for_external_delivery",
            reference=prefix["purchase_return"],
            timeout_seconds=30,
        )


def run_fixed_return_baseline(
    name: str,
    *,
    environment: ERPNextPartialReturnEnvironment,
    prefix: dict[str, Any],
) -> tuple[dict[str, Any], ...]:
    if name not in BASELINE_NAMES:
        raise ValueError(f"unknown fixed baseline: {name}")
    trace: list[dict[str, Any]] = []
    if name == "no_op":
        return ()
    if name == "blind_retry":
        retry = _call(
            environment,
            trace,
            "submit_document",
            doctype="Purchase Receipt",
            name=prefix["purchase_return"],
        )
        if retry.get("ok"):
            _complete_downstream(environment, prefix, trace)
            _call(
                environment,
                trace,
                "wait_for_external_delivery",
                reference=prefix["purchase_return"],
                timeout_seconds=30,
            )
        return tuple(trace)
    if name == "assume_committed":
        _complete_downstream(environment, prefix, trace)
        return tuple(trace)
    if name == "repair_failed_record_only":
        _resolve_boundary_only(environment, prefix, trace)
        return tuple(trace)
    if name == "all_rollback":
        for doctype, document_name in (
            ("Payment Entry", prefix["shared_payment_entry"]),
            ("Purchase Invoice", prefix["unaffected_invoice"]),
            ("Purchase Invoice", prefix["affected_invoice"]),
            ("Purchase Receipt", prefix["original_purchase_receipt"]),
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
    return tuple(trace)

