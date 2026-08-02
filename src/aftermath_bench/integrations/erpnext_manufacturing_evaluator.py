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
    return [doc for doc in documents if int(doc.get("docstatus", 0)) != 2]


def _ledger_quantity(
    rows: list[dict[str, Any]],
    *,
    voucher_no: str,
    item_code: str,
) -> Decimal:
    return sum(
        (
            _decimal(row.get("actual_qty"))
            for row in rows
            if str(row.get("voucher_no")) == voucher_no
            and str(row.get("item_code")) == item_code
            and not bool(row.get("is_cancelled", False))
        ),
        Decimal(0),
    )


def _gl_balanced(rows: list[dict[str, Any]], voucher_no: str) -> bool:
    relevant = [
        row
        for row in rows
        if str(row.get("voucher_no")) == voucher_no
        and not bool(row.get("is_cancelled", False))
    ]
    debit = sum((_decimal(row.get("debit")) for row in relevant), Decimal(0))
    credit = sum((_decimal(row.get("credit")) for row in relevant), Decimal(0))
    return len(relevant) >= 2 and debit > 0 and debit == credit


def manufacturing_document_fingerprint(document: dict[str, Any]) -> str:
    """Fingerprint only persistent business fields used by preservation checks."""
    keys = (
        "doctype",
        "name",
        "docstatus",
        "status",
        "work_order",
        "bom_no",
        "production_item",
        "fg_completed_qty",
        "purpose",
        "for_quantity",
        "total_completed_qty",
        "is_corrective_job_card",
        "for_job_card",
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
                    "is_finished_item": row.get("is_finished_item"),
                }
                for row in document.get("items", [])
            ),
            key=lambda row: json.dumps(row, sort_keys=True, default=str),
        )
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


@dataclass(frozen=True)
class ManufacturingRecoveryEvaluation:
    passed: bool
    components: dict[str, bool]
    checks: dict[str, bool]
    diagnostics: dict[str, Any]

    @property
    def failures(self) -> tuple[str, ...]:
        return tuple(name for name, passed in self.checks.items() if not passed)


def evaluate_manufacturing_rework_recovery(
    evidence: dict[str, Any],
    *,
    prefix: dict[str, Any],
) -> ManufacturingRecoveryEvaluation:
    work_order = evidence["work_order"]
    accepted_entry = evidence["accepted_manufacture_stock_entry"]
    corrective_job = evidence["corrective_job_card"]
    accepted_quantity = _decimal(prefix["accepted_quantity"])
    rework_quantity = _decimal(prefix["rework_quantity"])
    total_quantity = accepted_quantity + rework_quantity
    finished_item = str(prefix["finished_item"])

    final_entries = [
        document
        for document in _active(evidence.get("manufacture_stock_entries", []))
        if str(document.get("work_order")) == str(prefix["work_order"])
        and str(document.get("purpose")) == "Manufacture"
        and str(document.get("name")) != str(prefix["accepted_manufacture_stock_entry"])
    ]
    submitted_final_entries = [doc for doc in final_entries if _submitted(doc)]
    final_entry = (
        submitted_final_entries[0] if len(submitted_final_entries) == 1 else {}
    )

    final_inspections = [
        document
        for document in _active(evidence.get("quality_inspections", []))
        if document.get("reference_type") == "Stock Entry"
        and str(document.get("reference_name"))
        in {str(document.get("name")) for document in final_entries}
    ]
    accepted_final_inspections = [
        document
        for document in final_inspections
        if _submitted(document) and document.get("status") == "Accepted"
    ]
    corrective_jobs = [
        document
        for document in _active(evidence.get("job_cards", []))
        if bool(document.get("is_corrective_job_card"))
        and str(document.get("for_job_card")) == str(prefix["rejected_job_card"])
    ]

    goal_checks = {
        "work_order_completed_exact_quantity": (
            _submitted(work_order)
            and work_order.get("status") == "Completed"
            and _decimal(work_order.get("produced_qty")) == total_quantity
        ),
        "corrective_job_card_completed": (
            _submitted(corrective_job)
            and corrective_job.get("status") == "Completed"
            and bool(corrective_job.get("is_corrective_job_card"))
            and str(corrective_job.get("for_job_card"))
            == str(prefix["rejected_job_card"])
            and _decimal(corrective_job.get("total_completed_qty")) == rework_quantity
        ),
        "one_final_manufacture_entry_submitted": (
            len(submitted_final_entries) == 1
            and _decimal(final_entry.get("fg_completed_qty")) == rework_quantity
        ),
        "final_rework_inspection_accepted": (
            len(accepted_final_inspections) == 1
            and accepted_final_inspections[0].get("item_code") == finished_item
        ),
    }

    ledger = evidence.get("stock_ledger_entries", [])
    gl = evidence.get("gl_entries", [])
    final_name = str(final_entry.get("name", ""))
    repair_checks = {
        "accepted_inventory_posting_retained": (
            _ledger_quantity(
                ledger,
                voucher_no=str(prefix["accepted_manufacture_stock_entry"]),
                item_code=finished_item,
            )
            == accepted_quantity
        ),
        "reworked_inventory_posting_exact": (
            bool(final_name)
            and _ledger_quantity(
                ledger,
                voucher_no=final_name,
                item_code=finished_item,
            )
            == rework_quantity
        ),
        "manufacturing_accounting_balanced": (
            _gl_balanced(gl, str(prefix["accepted_manufacture_stock_entry"]))
            and bool(final_name)
            and _gl_balanced(gl, final_name)
        ),
        "corrective_cost_preserved_in_work_order": (
            _decimal(work_order.get("corrective_operation_cost"))
            == _decimal(prefix["expected_corrective_operation_cost"])
            and _decimal(work_order.get("corrective_operation_cost")) > 0
        ),
    }

    protected = prefix["protected_fingerprints"]
    preservation_checks = {
        "accepted_manufacture_entry_preserved": (
            manufacturing_document_fingerprint(accepted_entry)
            == protected["accepted_manufacture_stock_entry"]
            and _submitted(accepted_entry)
        ),
        "accepted_job_card_preserved": (
            manufacturing_document_fingerprint(evidence["accepted_job_card"])
            == protected["accepted_job_card"]
            and _submitted(evidence["accepted_job_card"])
        ),
        "bom_preserved": (
            manufacturing_document_fingerprint(evidence["bom"]) == protected["bom"]
            and _submitted(evidence["bom"])
        ),
        "unrelated_stock_entry_preserved": (
            manufacturing_document_fingerprint(evidence["unrelated_stock_entry"])
            == protected["unrelated_stock_entry"]
            and _submitted(evidence["unrelated_stock_entry"])
        ),
    }

    relevant_jobs = [
        job
        for job in evidence.get("rq_jobs", [])
        if str(prefix["corrective_job_card"])
        in json.dumps(job, sort_keys=True, default=str)
    ]
    unfinished = [
        job
        for job in relevant_jobs
        if str(job.get("status", "")).lower()
        in {"queued", "started", "failed", "deferred", "scheduled"}
    ]
    delivery = evidence.get("quality_release_delivery")
    safety_checks = {
        "no_duplicate_corrective_job_card": len(corrective_jobs) == 1,
        "no_duplicate_final_manufacture_entry": len(final_entries) == 1,
        "no_duplicate_final_quality_inspection": len(final_inspections) == 1,
        "quality_release_applied_exactly_once": (
            delivery is not None
            and delivery.get("key") == prefix["corrective_job_card"]
            and int(delivery.get("attempt_count", 0)) == 1
        ),
        "no_unfinished_quality_release_job": not unfinished,
    }

    checks = {
        **goal_checks,
        **repair_checks,
        **preservation_checks,
        **safety_checks,
    }
    components = {
        "goal_completion": all(goal_checks.values()),
        "repair_completeness": all(repair_checks.values()),
        "preservation": all(preservation_checks.values()),
        "protocol_safety": all(safety_checks.values()),
    }
    return ManufacturingRecoveryEvaluation(
        passed=all(components.values()),
        components=components,
        checks=checks,
        diagnostics={
            "active_corrective_job_card_count": len(corrective_jobs),
            "active_final_manufacture_entry_count": len(final_entries),
            "final_quality_inspection_count": len(final_inspections),
            "unfinished_quality_release_job_count": len(unfinished),
            "quality_release_attempt_count": (
                int(delivery.get("attempt_count", 0)) if delivery else 0
            ),
        },
    )


__all__ = [
    "ManufacturingRecoveryEvaluation",
    "evaluate_manufacturing_rework_recovery",
    "manufacturing_document_fingerprint",
]
