from __future__ import annotations

from typing import Any

from .erpnext_return_agent import UNFINISHED_JOB_STATUSES
from .erpnext_shared_batch_agent import ERPNextSharedBatchEnvironment


SHARED_BATCH_BASELINE_NAMES = (
    "no_op",
    "blind_retry",
    "assume_committed",
    "repair_failed_record_only",
    "all_rollback",
    "cancel_secondary_output",
    "duplicate_corrective",
)


def _call(
    environment: ERPNextSharedBatchEnvironment,
    trace: list[dict[str, Any]],
    tool: str,
    **arguments: Any,
) -> dict[str, Any]:
    result = environment.invoke(tool, **arguments)
    trace.append({"tool": tool, "arguments": arguments, "result": result})
    return result


def _complete_corrective_inventory(
    environment: ERPNextSharedBatchEnvironment,
    prefix: dict[str, Any],
    trace: list[dict[str, Any]],
) -> None:
    entry = _call(
        environment,
        trace,
        "create_manufacture_stock_entry",
        work_order=prefix["primary_work_order"],
        quantity=prefix["rework_quantity"],
    ).get("document")
    if not isinstance(entry, dict):
        return
    inspection = _call(
        environment,
        trace,
        "create_quality_inspection",
        reference_type="Stock Entry",
        reference_name=entry["name"],
        item_code=prefix["primary_finished_item"],
        sample_size=prefix["rework_quantity"],
        measured_value=1,
    ).get("document")
    if not isinstance(inspection, dict):
        return
    if not _call(
        environment,
        trace,
        "submit_document",
        doctype="Quality Inspection",
        name=inspection["name"],
    ).get("ok"):
        return
    _call(
        environment,
        trace,
        "submit_document",
        doctype="Stock Entry",
        name=entry["name"],
    )


def _repair_failed_record_only(
    environment: ERPNextSharedBatchEnvironment,
    prefix: dict[str, Any],
    trace: list[dict[str, Any]],
) -> None:
    corrective = _call(
        environment,
        trace,
        "get_document",
        doctype="Job Card",
        name=prefix["corrective_job_card"],
    ).get("document", {})
    if int(corrective.get("docstatus", 0)) == 0:
        _call(
            environment,
            trace,
            "submit_document",
            doctype="Job Card",
            name=prefix["corrective_job_card"],
        )
    delivery = _call(
        environment,
        trace,
        "get_external_delivery",
        reference=prefix["certificate_reference"],
    )
    if delivery.get("delivered"):
        return
    jobs = _call(
        environment,
        trace,
        "find_background_jobs",
        reference=prefix["corrective_job_card"],
    ).get("jobs", [])
    if any(
        str(job.get("status", "")).lower() in UNFINISHED_JOB_STATUSES for job in jobs
    ):
        _call(environment, trace, "resume_workers")
    else:
        _call(
            environment,
            trace,
            "enqueue_document_webhook",
            doctype="Job Card",
            name=prefix["corrective_job_card"],
            webhook_name=prefix["certificate_webhook"],
        )
    _call(
        environment,
        trace,
        "wait_for_external_delivery",
        reference=prefix["certificate_reference"],
        timeout_seconds=30,
    )


def run_fixed_shared_batch_baseline(
    name: str,
    *,
    environment: ERPNextSharedBatchEnvironment,
    prefix: dict[str, Any],
) -> tuple[dict[str, Any], ...]:
    """Execute one deliberately non-adaptive heuristic through public tools."""

    if name not in SHARED_BATCH_BASELINE_NAMES:
        raise ValueError(f"unknown shared-batch baseline: {name}")
    trace: list[dict[str, Any]] = []
    if name == "no_op":
        return ()
    if name == "blind_retry":
        _call(
            environment,
            trace,
            "submit_document",
            doctype="Job Card",
            name=prefix["corrective_job_card"],
        )
    elif name == "assume_committed":
        _complete_corrective_inventory(environment, prefix, trace)
    elif name == "repair_failed_record_only":
        _repair_failed_record_only(environment, prefix, trace)
    elif name == "all_rollback":
        for doctype, document_name in (
            ("Stock Entry", prefix["secondary_manufacture"]),
            ("Stock Entry", prefix["accepted_primary_manufacture"]),
            ("Landed Cost Voucher", prefix["shared_landed_cost_voucher"]),
            ("Purchase Receipt", prefix["shared_purchase_receipt"]),
        ):
            _call(
                environment,
                trace,
                "cancel_document",
                doctype=doctype,
                name=document_name,
            )
    elif name == "cancel_secondary_output":
        _call(
            environment,
            trace,
            "cancel_document",
            doctype="Stock Entry",
            name=prefix["secondary_manufacture"],
        )
    else:
        _call(
            environment,
            trace,
            "create_corrective_job_card",
            source_job_card=prefix["rejected_primary_job_card"],
            operation=prefix["corrective_operation"],
        )
    return tuple(trace)


__all__ = ["SHARED_BATCH_BASELINE_NAMES", "run_fixed_shared_batch_baseline"]
