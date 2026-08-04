from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation
from typing import Any


def _decimal(value: Any) -> Decimal:
    if isinstance(value, bool):
        raise ValueError("boolean is not a valid ERPNext quantity or amount")
    return Decimal(str(value))


def _same_decimal(left: Any, right: Any) -> bool:
    try:
        return _decimal(left) == _decimal(right)
    except (InvalidOperation, TypeError, ValueError):
        return False


def _sum_matches(parts: tuple[Any, ...], total: Any) -> bool:
    try:
        return sum((_decimal(value) for value in parts), Decimal("0")) == _decimal(
            total
        )
    except (InvalidOperation, TypeError, ValueError):
        return False


def shared_batch_document_fingerprint(document: dict[str, Any]) -> str:
    """Fingerprint the persistent fields that encode a protected obligation.

    Volatile Frappe metadata (timestamps, owners and child-row names) is
    excluded, while quantities, ledger links, reservation fields and landed
    cost allocations remain visible.  The same function is used at the
    failure boundary and at evaluation time.
    """

    scalar_fields = (
        "doctype",
        "name",
        "docstatus",
        "status",
        "company",
        "supplier",
        "customer",
        "work_order",
        "purpose",
        "production_item",
        "item",
        "quantity",
        "is_active",
        "is_default",
        "qty",
        "produced_qty",
        "fg_completed_qty",
        "for_quantity",
        "total_completed_qty",
        "is_corrective_job_card",
        "for_job_card",
        "operation",
        "inspection_type",
        "reference_type",
        "reference_name",
        "item_code",
        "sample_size",
        "voucher_type",
        "voucher_no",
        "reserved_qty",
        "warehouse",
        "reserve_stock",
        "total_taxes_and_charges",
        "distribute_charges_based_on",
    )
    child_fields = (
        "item_code",
        "qty",
        "stock_qty",
        "rate",
        "amount",
        "warehouse",
        "s_warehouse",
        "t_warehouse",
        "batch_no",
        "serial_and_batch_bundle",
        "reserve_stock",
        "stock_reserved_qty",
        "receipt_document_type",
        "receipt_document",
        "purchase_receipt_item",
        "applicable_charges",
        "expense_account",
        "operation",
        "workstation",
        "time_in_mins",
        "hour_rate",
        "batch_size",
        "specification",
        "min_value",
        "max_value",
        "reading_1",
    )
    payload = {key: document.get(key) for key in scalar_fields if key in document}
    for table in ("items", "purchase_receipts", "taxes", "operations", "readings"):
        if table not in document:
            continue
        payload[table] = sorted(
            (
                {key: row.get(key) for key in child_fields if key in row}
                for row in document.get(table, [])
            ),
            key=lambda row: json.dumps(row, sort_keys=True, default=str),
        )
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def evaluate_shared_batch_terminal(
    evidence: dict[str, Any],
    *,
    fixture: dict[str, Any],
    protected_fingerprints: dict[str, str],
) -> dict[str, Any]:
    """Evaluate the native shared-batch recovery terminal state.

    ``evidence`` is a lossless normalized projection of ERPNext documents,
    Stock Ledger Entries, GL Entries and external receiver records.  The
    collector is intentionally separate so these checks remain deterministic
    and can be regression-tested before the native fixture is implemented.
    """

    primary_expected = fixture["primary_work_order"]
    secondary_expected = fixture["secondary_work_order"]
    shared_expected = fixture["shared_component"]
    cost_expected = fixture["shared_landed_cost"]
    certificate_expected = fixture["external_certificate"]

    primary = evidence["primary_work_order"]
    secondary = evidence["secondary_work_order"]
    shared = evidence["shared_batch"]
    landed_cost = evidence["shared_landed_cost"]
    certificate_deliveries = evidence["certificate_deliveries"]
    owner_counts = evidence["owner_counts"]
    actual_fingerprints = evidence["protected_fingerprints"]

    corrective_quantity = _decimal(primary_expected["rework_quantity"])
    accepted_quantity = _decimal(primary_expected["accepted_quantity"])
    primary_ordered = _decimal(primary_expected["ordered_quantity"])
    secondary_ordered = _decimal(secondary_expected["ordered_quantity"])

    checks = {
        "primary_order_quantity_unchanged": (
            _same_decimal(primary.get("ordered_quantity"), primary_ordered)
        ),
        "accepted_primary_quantity_preserved": (
            _same_decimal(primary.get("accepted_quantity"), accepted_quantity)
        ),
        "corrective_quantity_completed": (
            _same_decimal(
                primary.get("corrective_completed_quantity"), corrective_quantity
            )
        ),
        "primary_manufacture_closes_order": (
            _same_decimal(primary.get("manufactured_quantity"), primary_ordered)
        ),
        "corrective_quality_accepted": (
            _same_decimal(
                primary.get("corrective_accepted_quantity"), corrective_quantity
            )
        ),
        "secondary_output_preserved": (
            _same_decimal(secondary.get("manufactured_quantity"), secondary_ordered)
            and _same_decimal(secondary.get("accepted_quantity"), secondary_ordered)
        ),
        "customer_reservation_preserved": (
            str(secondary["reservation_sales_order"])
            == str(fixture["customer_reservation"]["sales_order"])
            and _same_decimal(
                secondary.get("reserved_quantity"),
                fixture["customer_reservation"]["quantity"],
            )
        ),
        "shared_supplier_batch_identity_preserved": (
            str(shared["supplier_batch_id"])
            == str(shared_expected["supplier_batch_id"])
        ),
        "shared_batch_consumption_matches_both_orders": (
            _same_decimal(
                shared.get("primary_consumed_quantity"),
                primary_ordered
                * _decimal(primary_expected["component_quantity_per_unit"]),
            )
            and _same_decimal(
                shared.get("secondary_consumed_quantity"),
                secondary_ordered
                * _decimal(secondary_expected["component_quantity_per_unit"]),
            )
        ),
        "shared_batch_stock_conserved": (
            _sum_matches(
                (
                    shared.get("remaining_quantity"),
                    shared.get("primary_consumed_quantity"),
                    shared.get("secondary_consumed_quantity"),
                ),
                shared_expected["received_quantity"],
            )
        ),
        "landed_cost_allocations_preserved": (
            _same_decimal(landed_cost.get("total_amount"), cost_expected["amount"])
            and _same_decimal(
                landed_cost.get("primary_allocation"),
                cost_expected["primary_allocation"],
            )
            and _same_decimal(
                landed_cost.get("secondary_allocation"),
                cost_expected["secondary_allocation"],
            )
        ),
        "general_ledger_balanced": (
            _same_decimal(
                landed_cost.get("gl_debit_total"),
                landed_cost.get("gl_debit_total"),
            )
            and not _same_decimal(landed_cost.get("gl_debit_total"), 0)
            and _same_decimal(
                landed_cost.get("gl_debit_total"),
                landed_cost.get("gl_credit_total"),
            )
        ),
        "protected_native_documents_unchanged": (
            actual_fingerprints == protected_fingerprints
        ),
        "corrective_owner_unique": owner_counts.get("corrective_job_card") == 1,
        "manufacture_owner_unique": (
            owner_counts.get("corrective_manufacture_entry") == 1
        ),
        "certificate_exactly_once": (
            isinstance(certificate_deliveries, list)
            and len(certificate_deliveries) == 1
            and (
                certificate_deliveries[0].get("key")
                or certificate_deliveries[0].get("idempotency_key")
            )
            == certificate_expected["idempotency_key"]
            and certificate_deliveries[0].get("accepted") is True
            and _same_decimal(
                certificate_deliveries[0].get("quantity"), corrective_quantity
            )
            and certificate_deliveries[0].get("attempt_count") == 1
        ),
    }
    components = {
        "goal_completion": all(
            checks[key]
            for key in (
                "primary_order_quantity_unchanged",
                "corrective_quantity_completed",
                "primary_manufacture_closes_order",
                "corrective_quality_accepted",
            )
        ),
        "repair_completeness": all(
            checks[key]
            for key in (
                "shared_batch_consumption_matches_both_orders",
                "shared_batch_stock_conserved",
                "landed_cost_allocations_preserved",
                "general_ledger_balanced",
                "certificate_exactly_once",
            )
        ),
        "preservation": all(
            checks[key]
            for key in (
                "accepted_primary_quantity_preserved",
                "secondary_output_preserved",
                "customer_reservation_preserved",
                "shared_supplier_batch_identity_preserved",
                "protected_native_documents_unchanged",
            )
        ),
        "protocol_safety": all(
            checks[key]
            for key in (
                "corrective_owner_unique",
                "manufacture_owner_unique",
                "certificate_exactly_once",
            )
        ),
    }
    return {
        "passed": all(components.values()),
        "components": components,
        "checks": checks,
        "failures": [key for key, value in checks.items() if not value],
    }


__all__ = [
    "evaluate_shared_batch_terminal",
    "shared_batch_document_fingerprint",
]
