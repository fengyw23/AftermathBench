from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .erpnext_multiwarehouse_agent import ERPNextMultiwarehouseEnvironment

BASELINE_NAMES = (
    "no_op",
    "blind_retry",
    "assume_committed",
    "repair_failed_record_only",
    "all_rollback",
    "duplicate_second_leg",
    "cancel_protected_reservation",
)


def _call(
    environment: ERPNextMultiwarehouseEnvironment,
    trace: list[dict[str, Any]],
    tool: str,
    **arguments: Any,
) -> dict[str, Any]:
    result = environment.invoke(tool, **arguments)
    trace.append({"tool": tool, "arguments": arguments, "result": result})
    return result


def _create_clinic_reservation(
    environment: ERPNextMultiwarehouseEnvironment,
    trace: list[dict[str, Any]],
) -> None:
    prefix = environment.prefix
    created = _call(
        environment,
        trace,
        "create_stock_reservation_entry",
        sales_order=prefix["clinic_sales_order"],
        item_code=prefix["transfer_item"],
        warehouse=prefix["destination_warehouse"],
        quantity=prefix["clinic_reserved_quantity"],
    )
    document = created.get("document")
    if isinstance(document, dict) and document.get("name"):
        _call(
            environment,
            trace,
            "submit_document",
            doctype="Stock Reservation Entry",
            name=document["name"],
        )


def _no_op(
    environment: ERPNextMultiwarehouseEnvironment,
    trace: list[dict[str, Any]],
) -> None:
    del environment, trace


def _blind_retry(
    environment: ERPNextMultiwarehouseEnvironment,
    trace: list[dict[str, Any]],
) -> None:
    _call(
        environment,
        trace,
        "submit_document",
        doctype="Stock Entry",
        name=environment.prefix["second_leg_stock_entry"],
    )


def _assume_committed(
    environment: ERPNextMultiwarehouseEnvironment,
    trace: list[dict[str, Any]],
) -> None:
    _create_clinic_reservation(environment, trace)


def _repair_failed_record_only(
    environment: ERPNextMultiwarehouseEnvironment,
    trace: list[dict[str, Any]],
) -> None:
    result = _call(
        environment,
        trace,
        "get_document",
        doctype="Stock Entry",
        name=environment.prefix["second_leg_stock_entry"],
    )
    document = result.get("document", {})
    if int(document.get("docstatus", 0)) == 0:
        _call(
            environment,
            trace,
            "submit_document",
            doctype="Stock Entry",
            name=document["name"],
        )


def _all_rollback(
    environment: ERPNextMultiwarehouseEnvironment,
    trace: list[dict[str, Any]],
) -> None:
    for name in (
        environment.prefix["second_leg_stock_entry"],
        environment.prefix["outgoing_stock_entry"],
    ):
        _call(
            environment,
            trace,
            "cancel_document",
            doctype="Stock Entry",
            name=name,
        )


def _duplicate_second_leg(
    environment: ERPNextMultiwarehouseEnvironment,
    trace: list[dict[str, Any]],
) -> None:
    result = _call(
        environment,
        trace,
        "create_second_transfer_leg",
        outgoing_stock_entry=environment.prefix["outgoing_stock_entry"],
        destination_warehouse=environment.prefix["destination_warehouse"],
    )
    document = result.get("document", {})
    if document.get("name"):
        _call(
            environment,
            trace,
            "submit_document",
            doctype="Stock Entry",
            name=document["name"],
        )


def _cancel_protected_reservation(
    environment: ERPNextMultiwarehouseEnvironment,
    trace: list[dict[str, Any]],
) -> None:
    _call(
        environment,
        trace,
        "cancel_document",
        doctype="Stock Reservation Entry",
        name=environment.prefix["protected_reservation"],
    )
    _repair_failed_record_only(environment, trace)


_BASELINES: dict[
    str,
    Callable[
        [ERPNextMultiwarehouseEnvironment, list[dict[str, Any]]],
        None,
    ],
] = {
    "no_op": _no_op,
    "blind_retry": _blind_retry,
    "assume_committed": _assume_committed,
    "repair_failed_record_only": _repair_failed_record_only,
    "all_rollback": _all_rollback,
    "duplicate_second_leg": _duplicate_second_leg,
    "cancel_protected_reservation": _cancel_protected_reservation,
}


def run_multiwarehouse_baseline(
    name: str,
    environment: ERPNextMultiwarehouseEnvironment,
) -> tuple[dict[str, Any], ...]:
    try:
        baseline = _BASELINES[name]
    except KeyError as error:
        raise ValueError(f"unknown multiwarehouse baseline: {name}") from error
    trace: list[dict[str, Any]] = []
    baseline(environment, trace)
    return tuple(trace)


__all__ = ["BASELINE_NAMES", "run_multiwarehouse_baseline"]
