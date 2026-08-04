from __future__ import annotations

from typing import Any

from .erpnext_inventory_cost_agent import ERPNextInventoryCostEnvironment


INVENTORY_COST_BASELINE_NAMES = (
    "no_op",
    "blind_submit",
    "assume_committed",
    "failed_record_only",
    "scheduler_only",
    "duplicate_attestation",
    "all_rollback",
)


def _call(
    environment: ERPNextInventoryCostEnvironment,
    trace: list[dict[str, Any]],
    tool: str,
    **arguments: Any,
) -> dict[str, Any]:
    result = environment.invoke(tool, **arguments)
    trace.append({"tool": tool, "arguments": arguments, "result": result})
    return result


def run_fixed_inventory_cost_baseline(
    name: str,
    *,
    environment: ERPNextInventoryCostEnvironment,
    prefix: dict[str, Any],
) -> tuple[dict[str, Any], ...]:
    """Execute one deliberately state-insensitive policy through public tools."""

    if name not in INVENTORY_COST_BASELINE_NAMES:
        raise ValueError(f"unknown inventory-cost baseline: {name}")
    trace: list[dict[str, Any]] = []
    if name == "no_op":
        return ()
    if name == "blind_submit":
        _call(
            environment,
            trace,
            "submit_document",
            doctype="Landed Cost Voucher",
            name=prefix["landed_cost_voucher"],
        )
    elif name == "assume_committed":
        _call(environment, trace, "resume_workers")
        _call(
            environment,
            trace,
            "wait_for_external_delivery",
            reference=prefix["attestation_reference"],
            timeout_seconds=30,
        )
    elif name == "failed_record_only":
        voucher = _call(
            environment,
            trace,
            "get_document",
            doctype="Landed Cost Voucher",
            name=prefix["landed_cost_voucher"],
        ).get("document", {})
        if int(voucher.get("docstatus", 0)) == 0:
            _call(
                environment,
                trace,
                "submit_document",
                doctype="Landed Cost Voucher",
                name=prefix["landed_cost_voucher"],
            )
    elif name == "scheduler_only":
        _call(environment, trace, "run_stock_reposting_scheduler")
    elif name == "duplicate_attestation":
        _call(
            environment,
            trace,
            "enqueue_document_webhook",
            doctype="Landed Cost Voucher",
            name=prefix["landed_cost_voucher"],
            webhook_name=prefix["settlement_webhook"],
        )
        _call(environment, trace, "resume_workers")
        _call(
            environment,
            trace,
            "wait_for_external_delivery",
            reference=prefix["attestation_reference"],
            timeout_seconds=30,
        )
    else:
        for doctype, document_name in (
            ("Stock Entry", prefix["secondary_manufacture"]),
            ("Stock Entry", prefix["primary_manufacture"]),
            ("Purchase Receipt", prefix["shared_purchase_receipt"]),
        ):
            _call(
                environment,
                trace,
                "cancel_document",
                doctype=doctype,
                name=document_name,
            )
    return tuple(trace)


__all__ = [
    "INVENTORY_COST_BASELINE_NAMES",
    "run_fixed_inventory_cost_baseline",
]
