from __future__ import annotations

from typing import Any

from .erpnext_manufacturing_agent import ERPNextManufacturingEnvironment
from .erpnext_return_agent import UNFINISHED_JOB_STATUSES

BASELINE_NAMES = (
    "no_op",
    "blind_retry",
    "assume_committed",
    "repair_failed_record_only",
    "all_rollback",
    "cancel_accepted_output",
    "duplicate_corrective",
)


def _call(
    environment: ERPNextManufacturingEnvironment,
    trace: list[dict[str, Any]],
    tool: str,
    **arguments: Any,
) -> dict[str, Any]:
    result = environment.invoke(tool, **arguments)
    trace.append({"tool": tool, "arguments": arguments, "result": result})
    return result


def _resolve_failed_job_card_only(
    environment: ERPNextManufacturingEnvironment,
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


def _resolve_release_only(
    environment: ERPNextManufacturingEnvironment,
    prefix: dict[str, Any],
    trace: list[dict[str, Any]],
) -> None:
    delivery = _call(
        environment,
        trace,
        "get_external_delivery",
        reference=prefix["corrective_job_card"],
    )
    jobs = _call(
        environment,
        trace,
        "find_background_jobs",
        reference=prefix["corrective_job_card"],
    ).get("jobs", [])
    if delivery.get("delivered"):
        return
    if any(
        str(job.get("status", "")).lower() in UNFINISHED_JOB_STATUSES
        for job in jobs
    ):
        _call(environment, trace, "resume_workers")
    else:
        _call(
            environment,
            trace,
            "enqueue_document_webhook",
            doctype="Job Card",
            name=prefix["corrective_job_card"],
            webhook_name=prefix["quality_release_webhook"],
        )
    _call(
        environment,
        trace,
        "wait_for_external_delivery",
        reference=prefix["corrective_job_card"],
        timeout_seconds=30,
    )


def _complete_remaining_inventory(
    environment: ERPNextManufacturingEnvironment,
    prefix: dict[str, Any],
    trace: list[dict[str, Any]],
) -> None:
    entry_result = _call(
        environment,
        trace,
        "create_manufacture_stock_entry",
        work_order=prefix["work_order"],
        quantity=prefix["rework_quantity"],
    )
    entry = entry_result.get("document")
    if not entry_result.get("ok") or not isinstance(entry, dict):
        return
    inspection_result = _call(
        environment,
        trace,
        "create_quality_inspection",
        reference_type="Stock Entry",
        reference_name=entry["name"],
        item_code=prefix["finished_item"],
        sample_size=prefix["rework_quantity"],
        measured_value=1,
    )
    inspection = inspection_result.get("document")
    if not inspection_result.get("ok") or not isinstance(inspection, dict):
        return
    submitted_inspection = _call(
        environment,
        trace,
        "submit_document",
        doctype="Quality Inspection",
        name=inspection["name"],
    )
    if not submitted_inspection.get("ok"):
        return
    _call(
        environment,
        trace,
        "submit_document",
        doctype="Stock Entry",
        name=entry["name"],
    )


def run_fixed_manufacturing_baseline(
    name: str,
    *,
    environment: ERPNextManufacturingEnvironment,
    prefix: dict[str, Any],
) -> tuple[dict[str, Any], ...]:
    """Run one fixed recovery heuristic through model-visible tools only."""
    if name not in BASELINE_NAMES:
        raise ValueError(f"unknown fixed manufacturing baseline: {name}")
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
        return tuple(trace)
    if name == "assume_committed":
        _complete_remaining_inventory(environment, prefix, trace)
        return tuple(trace)
    if name == "repair_failed_record_only":
        _resolve_failed_job_card_only(environment, prefix, trace)
        _resolve_release_only(environment, prefix, trace)
        return tuple(trace)
    if name == "all_rollback":
        for doctype, document_name in (
            ("Stock Entry", prefix["accepted_manufacture_stock_entry"]),
            ("Job Card", prefix["accepted_job_card"]),
            ("Work Order", prefix["work_order"]),
        ):
            _call(
                environment,
                trace,
                "cancel_document",
                doctype=doctype,
                name=document_name,
            )
        return tuple(trace)
    if name == "cancel_accepted_output":
        _call(
            environment,
            trace,
            "cancel_document",
            doctype="Stock Entry",
            name=prefix["accepted_manufacture_stock_entry"],
        )
        return tuple(trace)
    _call(
        environment,
        trace,
        "create_corrective_job_card",
        source_job_card=prefix["rejected_job_card"],
        operation=prefix["corrective_operation"],
    )
    return tuple(trace)


__all__ = ["BASELINE_NAMES", "run_fixed_manufacturing_baseline"]
