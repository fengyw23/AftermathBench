from __future__ import annotations

import argparse
import json
from decimal import Decimal
from pathlib import Path
from typing import Any

from aftermath_bench.integrations.erpnext_shared_batch_evaluator import (
    shared_batch_document_fingerprint,
)
from aftermath_bench.native_scenario import load_native_scenario


def _decimal(value: Any) -> Decimal:
    return Decimal(str(value or 0))


def _submitted(document: dict[str, Any]) -> bool:
    return int(document.get("docstatus", 0)) == 1


def validate_prefix(
    prefix: dict[str, Any],
    evidence: dict[str, Any],
    fixture: dict[str, Any],
) -> dict[str, Any]:
    primary = fixture["primary_work_order"]
    secondary = fixture["secondary_work_order"]
    shared = fixture["shared_component"]
    cost = fixture["shared_landed_cost"]
    reservation = fixture["customer_reservation"]

    lcv = evidence["shared_landed_cost_voucher"]
    purchase_receipt = evidence["shared_purchase_receipt"]
    primary_wo = evidence["primary_work_order"]
    secondary_wo = evidence["secondary_work_order"]
    corrective = evidence["corrective_job_card"]
    stock_reservation = evidence["stock_reservation_entry"]
    lcv_items = lcv.get("items", [])
    receipt_items = purchase_receipt.get("items", [])
    receipt_by_name = {str(row.get("name")): row for row in receipt_items}
    lcv_by_receipt_item = {
        str(row.get("purchase_receipt_item")): row for row in lcv_items
    }
    primary_receipt_item = receipt_by_name.get(
        str(prefix["primary_purchase_receipt_item"]), {}
    )
    secondary_receipt_item = receipt_by_name.get(
        str(prefix["secondary_purchase_receipt_item"]), {}
    )
    primary_lcv_item = lcv_by_receipt_item.get(
        str(prefix["primary_purchase_receipt_item"]), {}
    )
    secondary_lcv_item = lcv_by_receipt_item.get(
        str(prefix["secondary_purchase_receipt_item"]), {}
    )
    # ERPNext posts the LCV revaluation by cancelling/reposting the referenced
    # Purchase Receipt's GL entries; the voucher identity remains the PR.
    relevant_lcv_gl = [
        row
        for row in evidence.get("gl_entries", [])
        if str(row.get("voucher_no")) == str(prefix["shared_purchase_receipt"])
        and not bool(row.get("is_cancelled"))
    ]
    gl_debit = sum((_decimal(row.get("debit")) for row in relevant_lcv_gl), Decimal(0))
    gl_credit = sum(
        (_decimal(row.get("credit")) for row in relevant_lcv_gl), Decimal(0)
    )

    protected_documents = {
        "accepted_primary_manufacture": evidence["accepted_primary_manufacture"],
        "secondary_manufacture": evidence["secondary_manufacture"],
        "customer_reservation": evidence["customer_reservation"],
        "shared_landed_cost_voucher": lcv,
        "unrelated_receipt": evidence["unrelated_receipt"],
    }
    actual_fingerprints = {
        key: shared_batch_document_fingerprint(document)
        for key, document in protected_documents.items()
    }
    checks = {
        "purchase_receipt_submitted": _submitted(purchase_receipt),
        "two_native_branch_receipt_rows_share_one_batch": (
            len(receipt_items) == 2
            and all(
                row.get("item_code") == shared["item_code"] for row in receipt_items
            )
            and sum((_decimal(row.get("qty")) for row in receipt_items), Decimal(0))
            == _decimal(shared["received_quantity"])
            and all(
                row.get("batch_no") == shared["supplier_batch_id"]
                and bool(row.get("serial_and_batch_bundle"))
                for row in receipt_items
            )
            and _decimal(primary_receipt_item.get("qty"))
            == _decimal(primary["ordered_quantity"])
            and _decimal(secondary_receipt_item.get("qty"))
            == _decimal(secondary["ordered_quantity"])
        ),
        "landed_cost_submitted_and_native": (
            _submitted(lcv)
            and _decimal(lcv.get("total_taxes_and_charges")) == _decimal(cost["amount"])
            and len(lcv_items) == 2
            and _decimal(primary_lcv_item.get("applicable_charges"))
            == _decimal(cost["primary_allocation"])
            and _decimal(secondary_lcv_item.get("applicable_charges"))
            == _decimal(cost["secondary_allocation"])
            and _decimal(primary_receipt_item.get("landed_cost_voucher_amount"))
            == _decimal(cost["primary_allocation"])
            and _decimal(secondary_receipt_item.get("landed_cost_voucher_amount"))
            == _decimal(cost["secondary_allocation"])
        ),
        "landed_cost_gl_balanced": (
            len(relevant_lcv_gl) >= 2 and gl_debit > 0 and gl_debit == gl_credit
        ),
        "primary_boundary_quantity": (
            _submitted(primary_wo)
            and _decimal(primary_wo.get("qty")) == _decimal(primary["ordered_quantity"])
            and _decimal(primary_wo.get("produced_qty"))
            == _decimal(primary["accepted_quantity"])
        ),
        "secondary_branch_completed": (
            _submitted(secondary_wo)
            and str(secondary_wo.get("status")) == "Completed"
            and _decimal(secondary_wo.get("produced_qty"))
            == _decimal(secondary["accepted_quantity"])
        ),
        "corrective_job_card_is_unique_draft": (
            int(corrective.get("docstatus", -1)) == 0
            and bool(corrective.get("is_corrective_job_card"))
            and _decimal(corrective.get("for_quantity"))
            == _decimal(primary["rework_quantity"])
            and sum(
                1
                for card in evidence.get("job_cards", [])
                if int(card.get("docstatus", 0)) != 2
                and bool(card.get("is_corrective_job_card"))
            )
            == 1
        ),
        "customer_stock_reservation_submitted": (
            _submitted(evidence["customer_reservation"])
            and _submitted(stock_reservation)
            and str(stock_reservation.get("voucher_no"))
            == str(reservation["sales_order"])
            and _decimal(stock_reservation.get("reserved_qty"))
            == _decimal(reservation["quantity"])
            and str(stock_reservation.get("status")) == "Reserved"
        ),
        "certificate_absent_before_failure": evidence.get("certificate_delivery")
        is None,
        "protected_fingerprints_replay": (
            actual_fingerprints == prefix["protected_fingerprints"]
        ),
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "failures": [name for name, passed in checks.items() if not passed],
        "diagnostics": {
            "lcv_gl_entry_count": len(relevant_lcv_gl),
            "lcv_gl_debit": str(gl_debit),
            "lcv_gl_credit": str(gl_credit),
            "prefix_write_count": len(prefix.get("trace", [])),
            "job_card_count": len(evidence.get("job_cards", [])),
            "stock_entry_count": len(evidence.get("manufacture_stock_entries", [])),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate a real ERPNext shared-batch failure prefix."
    )
    parser.add_argument("--scenario", type=Path, required=True)
    parser.add_argument("--prefix", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    scenario = load_native_scenario(args.scenario)
    prefix = json.loads(args.prefix.read_text(encoding="utf-8"))
    evidence = json.loads(args.evidence.read_text(encoding="utf-8"))
    result = validate_prefix(prefix, evidence, scenario.raw["fixture"])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
