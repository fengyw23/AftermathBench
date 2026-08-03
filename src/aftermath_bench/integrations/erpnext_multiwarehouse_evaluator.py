from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Any


def _decimal(value: Any) -> Decimal:
    return Decimal(str(value or 0))


def _submitted(document: dict[str, Any]) -> bool:
    return int(document.get("docstatus", 0)) == 1


def _active(documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [document for document in documents if int(document.get("docstatus", 0)) != 2]


def _bin_quantity(
    rows: list[dict[str, Any]], *, item_code: str, warehouse: str
) -> Decimal:
    return sum(
        (
            _decimal(row.get("actual_qty"))
            for row in rows
            if str(row.get("item_code")) == item_code
            and str(row.get("warehouse")) == warehouse
        ),
        Decimal(0),
    )


def _voucher_warehouse_quantity(
    rows: list[dict[str, Any]],
    *,
    voucher_no: str,
    item_code: str,
    warehouse: str,
) -> Decimal:
    return sum(
        (
            _decimal(row.get("actual_qty"))
            for row in rows
            if str(row.get("voucher_no")) == voucher_no
            and str(row.get("item_code")) == item_code
            and str(row.get("warehouse")) == warehouse
            and not bool(row.get("is_cancelled", False))
        ),
        Decimal(0),
    )


def multiwarehouse_document_fingerprint(document: dict[str, Any]) -> str:
    """Fingerprint stable business fields while allowing native progress counters."""
    keys = (
        "doctype",
        "name",
        "docstatus",
        "purpose",
        "stock_entry_type",
        "add_to_transit",
        "outgoing_stock_entry",
        "item_code",
        "warehouse",
        "voucher_type",
        "voucher_no",
        "voucher_detail_no",
        "voucher_qty",
        "reserved_qty",
        "company",
    )
    payload = {key: document.get(key) for key in keys if key in document}
    if "items" in document:
        payload["items"] = sorted(
            (
                {
                    "item_code": row.get("item_code"),
                    "qty": row.get("qty"),
                    "s_warehouse": row.get("s_warehouse"),
                    "t_warehouse": row.get("t_warehouse"),
                    "batch_no": row.get("batch_no"),
                    "serial_no": row.get("serial_no"),
                    "against_stock_entry": row.get("against_stock_entry"),
                }
                for row in document.get("items", [])
            ),
            key=lambda row: json.dumps(row, sort_keys=True, default=str),
        )
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


@dataclass(frozen=True)
class MultiwarehouseRecoveryEvaluation:
    passed: bool
    components: dict[str, bool]
    checks: dict[str, bool]
    diagnostics: dict[str, Any]

    @property
    def failures(self) -> tuple[str, ...]:
        return tuple(name for name, passed in self.checks.items() if not passed)


def evaluate_multiwarehouse_recovery(
    evidence: dict[str, Any], *, prefix: dict[str, Any]
) -> MultiwarehouseRecoveryEvaluation:
    item_code = str(prefix["transfer_item"])
    quantity = _decimal(prefix["transfer_quantity"])
    reserved_quantity = _decimal(prefix["clinic_reserved_quantity"])
    outgoing_name = str(prefix["outgoing_stock_entry"])
    transit = str(prefix["transit_warehouse"])
    destination = str(prefix["destination_warehouse"])

    outgoing = evidence["outgoing_stock_entry"]
    second_legs = [
        document
        for document in _active(evidence.get("second_leg_stock_entries", []))
        if str(document.get("outgoing_stock_entry")) == outgoing_name
    ]
    submitted_second_legs = [document for document in second_legs if _submitted(document)]
    second_leg = submitted_second_legs[0] if len(submitted_second_legs) == 1 else {}
    second_leg_name = str(second_leg.get("name", ""))
    second_leg_items = [
        row
        for row in second_leg.get("items", [])
        if str(row.get("item_code")) == item_code
    ]

    reservations = _active(evidence.get("stock_reservation_entries", []))
    clinic_reservations = [
        reservation
        for reservation in reservations
        if str(reservation.get("voucher_no")) == str(prefix["clinic_sales_order"])
        and str(reservation.get("item_code")) == item_code
    ]
    clinic_reservation = clinic_reservations[0] if len(clinic_reservations) == 1 else {}

    ledger = evidence.get("stock_ledger_entries", [])
    bins = evidence.get("bins", [])
    transfer_checks = {
        "one_second_leg_submitted": len(submitted_second_legs) == 1,
        "second_leg_links_to_first_leg": (
            bool(second_leg_name)
            and str(second_leg.get("outgoing_stock_entry")) == outgoing_name
            and len(second_leg_items) == 1
            and _decimal(second_leg_items[0].get("qty")) == quantity
            and str(second_leg_items[0].get("s_warehouse")) == transit
            and str(second_leg_items[0].get("t_warehouse")) == destination
        ),
        "traceable_batch_preserved": (
            len(second_leg_items) == 1
            and str(second_leg_items[0].get("batch_no")) == str(prefix["batch_id"])
        ),
        "outgoing_transfer_closed": (
            _submitted(outgoing)
            and bool(outgoing.get("add_to_transit"))
            and _decimal(outgoing.get("per_transferred")) == Decimal(100)
        ),
    }
    posting_checks = {
        "transit_stock_removed_exactly_once": (
            bool(second_leg_name)
            and _voucher_warehouse_quantity(
                ledger,
                voucher_no=second_leg_name,
                item_code=item_code,
                warehouse=transit,
            )
            == -quantity
        ),
        "destination_stock_received_exactly_once": (
            bool(second_leg_name)
            and _voucher_warehouse_quantity(
                ledger,
                voucher_no=second_leg_name,
                item_code=item_code,
                warehouse=destination,
            )
            == quantity
        ),
        "transit_bin_empty": (
            _bin_quantity(bins, item_code=item_code, warehouse=transit) == 0
        ),
        "destination_bin_has_transfer": (
            _bin_quantity(bins, item_code=item_code, warehouse=destination)
            >= quantity
        ),
    }
    reservation_checks = {
        "clinic_reservation_restored": (
            len(clinic_reservations) == 1
            and _submitted(clinic_reservation)
            and str(clinic_reservation.get("warehouse")) == destination
            and _decimal(clinic_reservation.get("reserved_qty")) == reserved_quantity
            and str(clinic_reservation.get("status"))
            in {"Reserved", "Partially Reserved"}
        ),
        "protected_reservation_preserved": (
            multiwarehouse_document_fingerprint(evidence["protected_reservation"])
            == prefix["protected_fingerprints"]["protected_reservation"]
            and _submitted(evidence["protected_reservation"])
        ),
        "protected_warehouse_balance_preserved": (
            _bin_quantity(
                bins,
                item_code=str(prefix["protected_item"]),
                warehouse=str(prefix["protected_warehouse"]),
            )
            == _decimal(prefix["protected_stock_balance"])
        ),
    }

    reposts = [
        document
        for document in evidence.get("repost_item_valuations", [])
        if str(document.get("voucher_no")) in {outgoing_name, second_leg_name}
    ]
    unfinished_reposts = [
        document
        for document in reposts
        if str(document.get("status", "")).lower()
        in {"queued", "in progress", "failed"}
    ]
    safety_checks = {
        "no_duplicate_second_leg": len(second_legs) == 1,
        "no_duplicate_clinic_reservation": len(clinic_reservations) == 1,
        "no_unfinished_reposting": not unfinished_reposts,
        "first_leg_business_fields_preserved": (
            multiwarehouse_document_fingerprint(outgoing)
            == prefix["protected_fingerprints"]["outgoing_stock_entry"]
        ),
    }

    checks = {
        **transfer_checks,
        **posting_checks,
        **reservation_checks,
        **safety_checks,
    }
    components = {
        "goal_completion": all(transfer_checks.values()),
        "repair_completeness": all(posting_checks.values())
        and reservation_checks["clinic_reservation_restored"],
        "preservation": all(reservation_checks.values()),
        "protocol_safety": all(safety_checks.values()),
    }
    return MultiwarehouseRecoveryEvaluation(
        passed=all(components.values()),
        components=components,
        checks=checks,
        diagnostics={
            "active_second_leg_count": len(second_legs),
            "submitted_second_leg_count": len(submitted_second_legs),
            "clinic_reservation_count": len(clinic_reservations),
            "unfinished_reposting_count": len(unfinished_reposts),
            "destination_quantity": str(
                _bin_quantity(bins, item_code=item_code, warehouse=destination)
            ),
            "transit_quantity": str(
                _bin_quantity(bins, item_code=item_code, warehouse=transit)
            ),
        },
    )


__all__ = [
    "MultiwarehouseRecoveryEvaluation",
    "evaluate_multiwarehouse_recovery",
    "multiwarehouse_document_fingerprint",
]
