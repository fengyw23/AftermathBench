from __future__ import annotations

from decimal import Decimal
from typing import Any


def _decimal(value: Any) -> Decimal:
    if isinstance(value, bool):
        raise ValueError("boolean is not a valid ERPNext quantity or amount")
    return Decimal(str(value))


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
            _decimal(primary["ordered_quantity"]) == primary_ordered
        ),
        "accepted_primary_quantity_preserved": (
            _decimal(primary["accepted_quantity"]) == accepted_quantity
        ),
        "corrective_quantity_completed": (
            _decimal(primary["corrective_completed_quantity"])
            == corrective_quantity
        ),
        "primary_manufacture_closes_order": (
            _decimal(primary["manufactured_quantity"]) == primary_ordered
        ),
        "corrective_quality_accepted": (
            _decimal(primary["corrective_accepted_quantity"])
            == corrective_quantity
        ),
        "secondary_output_preserved": (
            _decimal(secondary["manufactured_quantity"]) == secondary_ordered
            and _decimal(secondary["accepted_quantity"]) == secondary_ordered
        ),
        "customer_reservation_preserved": (
            str(secondary["reservation_sales_order"])
            == str(fixture["customer_reservation"]["sales_order"])
            and _decimal(secondary["reserved_quantity"])
            == _decimal(fixture["customer_reservation"]["quantity"])
        ),
        "shared_supplier_batch_identity_preserved": (
            str(shared["supplier_batch_id"])
            == str(shared_expected["supplier_batch_id"])
        ),
        "shared_batch_consumption_matches_both_orders": (
            _decimal(shared["primary_consumed_quantity"])
            == primary_ordered
            * _decimal(primary_expected["component_quantity_per_unit"])
            and _decimal(shared["secondary_consumed_quantity"])
            == secondary_ordered
            * _decimal(secondary_expected["component_quantity_per_unit"])
        ),
        "shared_batch_stock_conserved": (
            _decimal(shared["remaining_quantity"])
            + _decimal(shared["primary_consumed_quantity"])
            + _decimal(shared["secondary_consumed_quantity"])
            == _decimal(shared_expected["received_quantity"])
        ),
        "landed_cost_allocations_preserved": (
            _decimal(landed_cost["total_amount"])
            == _decimal(cost_expected["amount"])
            and _decimal(landed_cost["primary_allocation"])
            == _decimal(cost_expected["primary_allocation"])
            and _decimal(landed_cost["secondary_allocation"])
            == _decimal(cost_expected["secondary_allocation"])
        ),
        "general_ledger_balanced": (
            _decimal(landed_cost["gl_debit_total"])
            == _decimal(landed_cost["gl_credit_total"])
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
            and certificate_deliveries[0].get("idempotency_key")
            == certificate_expected["idempotency_key"]
            and certificate_deliveries[0].get("accepted") is True
            and _decimal(certificate_deliveries[0].get("quantity"))
            == corrective_quantity
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
