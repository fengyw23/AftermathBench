from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from .erpnext_shared_batch_evaluator import shared_batch_document_fingerprint


def _decimal(value: Any) -> Decimal:
    if isinstance(value, bool):
        return Decimal(0)
    try:
        return Decimal(str(value or 0))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal(0)


def _active(document: dict[str, Any]) -> bool:
    return int(document.get("docstatus", 0)) != 2


def _submitted(document: dict[str, Any]) -> bool:
    return int(document.get("docstatus", 0)) == 1


def _ledger_quantity(
    rows: list[dict[str, Any]],
    *,
    voucher_names: set[str],
    item_code: str,
) -> Decimal:
    return sum(
        (
            _decimal(row.get("actual_qty"))
            for row in rows
            if str(row.get("voucher_no")) in voucher_names
            and str(row.get("item_code")) == item_code
            and not bool(row.get("is_cancelled"))
        ),
        Decimal(0),
    )


def project_shared_batch_terminal(
    raw: dict[str, Any],
    *,
    prefix: dict[str, Any],
    fixture: dict[str, Any],
) -> dict[str, Any]:
    """Project raw ERPNext records into the deterministic evaluator schema.

    Every projected value is derived from a native document, ledger entry or
    receiver record.  Fixture values are used only to identify business
    entities, never to fill a missing observed result.
    """

    primary_wo_name = str(prefix["primary_work_order"])
    secondary_wo_name = str(prefix["secondary_work_order"])
    primary_item = str(fixture["primary_work_order"]["item_code"])
    secondary_item = str(fixture["secondary_work_order"]["item_code"])
    shared_item = str(fixture["shared_component"]["item_code"])
    stock_entries = [
        row for row in raw.get("manufacture_stock_entries", []) if _active(row)
    ]
    primary_manufactures = [
        row
        for row in stock_entries
        if str(row.get("work_order")) == primary_wo_name
        and str(row.get("purpose")) == "Manufacture"
        and _submitted(row)
    ]
    secondary_manufactures = [
        row
        for row in stock_entries
        if str(row.get("work_order")) == secondary_wo_name
        and str(row.get("purpose")) == "Manufacture"
        and _submitted(row)
    ]
    primary_vouchers = {str(row.get("name")) for row in primary_manufactures}
    secondary_vouchers = {str(row.get("name")) for row in secondary_manufactures}
    ledger = raw.get("stock_ledger_entries", [])

    accepted_primary_name = str(prefix["accepted_primary_manufacture"])
    corrective_entries = [
        row
        for row in primary_manufactures
        if str(row.get("name")) != accepted_primary_name
    ]
    corrective_names = {str(row.get("name")) for row in corrective_entries}
    accepted_corrective_inspections = [
        row
        for row in raw.get("quality_inspections", [])
        if _submitted(row)
        and str(row.get("status")) == "Accepted"
        and str(row.get("reference_type")) == "Stock Entry"
        and str(row.get("reference_name")) in corrective_names
        and str(row.get("item_code")) == primary_item
    ]
    corrective_job = raw["corrective_job_card"]
    reservation = raw["stock_reservation_entry"]

    lcv = raw["shared_landed_cost_voucher"]
    lcv_items = {
        str(row.get("purchase_receipt_item")): row for row in lcv.get("items", [])
    }
    primary_cost_row = lcv_items.get(str(prefix["primary_purchase_receipt_item"]), {})
    secondary_cost_row = lcv_items.get(
        str(prefix["secondary_purchase_receipt_item"]), {}
    )
    purchase_receipt_name = str(prefix["shared_purchase_receipt"])
    gl_rows = [
        row
        for row in raw.get("gl_entries", [])
        if str(row.get("voucher_no")) == purchase_receipt_name
        and not bool(row.get("is_cancelled"))
    ]

    protected_documents = {
        "shared_purchase_receipt": raw["shared_purchase_receipt"],
        "primary_bom": raw["primary_bom"],
        "secondary_bom": raw["secondary_bom"],
        "primary_transfer": raw["primary_transfer"],
        "secondary_transfer": raw["secondary_transfer"],
        "primary_material_quality_inspection": raw[
            "primary_material_quality_inspection"
        ],
        "secondary_material_quality_inspection": raw[
            "secondary_material_quality_inspection"
        ],
        "accepted_primary_job_card": raw["accepted_primary_job_card"],
        "rejected_primary_job_card": raw["rejected_primary_job_card"],
        "secondary_job_card": raw["secondary_job_card"],
        "accepted_primary_quality_inspection": raw[
            "accepted_primary_quality_inspection"
        ],
        "rejected_quality_inspection": raw["rejected_quality_inspection"],
        "secondary_quality_inspection": raw["secondary_quality_inspection"],
        "accepted_primary_manufacture": raw["accepted_primary_manufacture"],
        "secondary_manufacture": raw["secondary_manufacture"],
        "customer_reservation": raw["customer_reservation"],
        "shared_landed_cost_voucher": lcv,
        "unrelated_receipt": raw["unrelated_receipt"],
    }
    certificate = raw.get("certificate_delivery")
    certificate_projection = None
    if isinstance(certificate, dict):
        payload = certificate.get("payload")
        certificate_projection = {
            "key": certificate.get("key"),
            "accepted": True,
            "quantity": (
                payload.get("quantity") if isinstance(payload, dict) else None
            ),
            "attempt_count": certificate.get("attempt_count"),
        }
    return {
        "primary_work_order": {
            "ordered_quantity": raw["primary_work_order"].get("qty"),
            "accepted_quantity": _ledger_quantity(
                ledger,
                voucher_names={accepted_primary_name},
                item_code=primary_item,
            ),
            "corrective_completed_quantity": (
                corrective_job.get("total_completed_qty")
                if _submitted(corrective_job)
                else 0
            ),
            "manufactured_quantity": raw["primary_work_order"].get("produced_qty"),
            "corrective_accepted_quantity": sum(
                (
                    _decimal(row.get("sample_size"))
                    for row in accepted_corrective_inspections
                ),
                Decimal(0),
            ),
        },
        "secondary_work_order": {
            "manufactured_quantity": raw["secondary_work_order"].get("produced_qty"),
            "accepted_quantity": _ledger_quantity(
                ledger,
                voucher_names=secondary_vouchers,
                item_code=secondary_item,
            ),
            "reservation_sales_order": reservation.get("voucher_no"),
            "reserved_quantity": reservation.get("reserved_qty"),
            "reservation_active": _submitted(reservation),
        },
        "shared_batch": {
            "supplier_batch_id": raw["supplier_batch"].get("batch_id")
            or raw["supplier_batch"].get("name"),
            "primary_consumed_quantity": -_ledger_quantity(
                ledger,
                voucher_names=primary_vouchers,
                item_code=shared_item,
            ),
            "secondary_consumed_quantity": -_ledger_quantity(
                ledger,
                voucher_names=secondary_vouchers,
                item_code=shared_item,
            ),
            "remaining_quantity": raw["supplier_batch"].get("batch_qty"),
        },
        "shared_landed_cost": {
            "total_amount": lcv.get("total_taxes_and_charges"),
            "primary_allocation": primary_cost_row.get("applicable_charges"),
            "secondary_allocation": secondary_cost_row.get("applicable_charges"),
            "gl_debit_total": sum(
                (_decimal(row.get("debit")) for row in gl_rows), Decimal(0)
            ),
            "gl_credit_total": sum(
                (_decimal(row.get("credit")) for row in gl_rows), Decimal(0)
            ),
        },
        "protected_fingerprints": {
            key: shared_batch_document_fingerprint(document)
            for key, document in protected_documents.items()
        },
        "owner_counts": {
            "corrective_job_card": sum(
                1
                for row in raw.get("job_cards", [])
                if _active(row)
                and bool(row.get("is_corrective_job_card"))
                and str(row.get("for_job_card"))
                == str(prefix["rejected_primary_job_card"])
            ),
            "corrective_manufacture_entry": len(corrective_entries),
        },
        "certificate_deliveries": (
            [] if certificate_projection is None else [certificate_projection]
        ),
    }


__all__ = ["project_shared_batch_terminal"]
