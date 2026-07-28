from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from .erpnext_evaluator import protected_fingerprint


def _decimal(value: Any) -> Decimal:
    return Decimal(str(value or 0))


def _active(documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        document
        for document in documents
        if int(document.get("docstatus", 0)) != 2
    ]


def _submitted(documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        document
        for document in documents
        if int(document.get("docstatus", 0)) == 1
    ]


def _item_quantity(document: dict[str, Any], item_code: str) -> Decimal:
    return sum(
        (
            _decimal(item.get("qty"))
            for item in document.get("items", [])
            if item.get("item_code") == item_code
        ),
        Decimal(0),
    )


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


def _payment_fingerprint(payment: dict[str, Any]) -> str:
    return json.dumps(
        {
            "name": payment.get("name"),
            "docstatus": payment.get("docstatus"),
            "paid_amount": payment.get("paid_amount"),
            "references": sorted(
                str(reference.get("reference_name"))
                for reference in payment.get("references", [])
            ),
        },
        sort_keys=True,
        separators=(",", ":"),
    )


@dataclass(frozen=True)
class PartialReturnEvaluation:
    passed: bool
    components: dict[str, bool]
    checks: dict[str, bool]
    diagnostics: dict[str, Any]

    @property
    def failures(self) -> tuple[str, ...]:
        return tuple(name for name, passed in self.checks.items() if not passed)


def evaluate_partial_return_recovery(
    evidence: dict[str, Any],
    *,
    prefix: dict[str, Any],
) -> PartialReturnEvaluation:
    defective = _decimal(prefix["defective_quantity"])
    affected = str(prefix["affected_item"])
    unaffected = str(prefix["unaffected_item"])
    replacement = str(prefix["replacement_item"])
    original_quantities = {
        key: _decimal(value)
        for key, value in prefix["original_quantities"].items()
    }
    returns = _active(evidence.get("purchase_returns", []))
    submitted_returns = _submitted(returns)
    debits = _active(evidence.get("debit_notes", []))
    submitted_debits = _submitted(debits)
    replacement_receipts = _active(
        evidence.get("replacement_receipts", [])
    )
    submitted_replacement_receipts = _submitted(replacement_receipts)
    replacement_invoices = _active(
        evidence.get("replacement_invoices", [])
    )
    submitted_replacement_invoices = _submitted(replacement_invoices)

    original_order = evidence["original_purchase_order"]
    original_receipt = evidence["original_purchase_receipt"]
    unaffected_invoice = evidence["unaffected_invoice"]
    affected_invoice = evidence["affected_invoice"]
    payment = evidence["shared_payment_entry"]
    quality = evidence["quality_inspection"]
    protected = prefix["protected_fingerprints"]
    preservation_checks = {
        "original_order_preserved": (
            protected_fingerprint("purchase_order", original_order)
            == protected["original_purchase_order"]
            and int(original_order.get("docstatus", 0)) == 1
        ),
        "original_receipt_preserved": (
            protected_fingerprint("purchase_receipt", original_receipt)
            == protected["original_purchase_receipt"]
            and int(original_receipt.get("docstatus", 0)) == 1
        ),
        "unaffected_invoice_preserved": (
            protected_fingerprint("purchase_invoice", unaffected_invoice)
            == protected["unaffected_invoice"]
            and int(unaffected_invoice.get("docstatus", 0)) == 1
            and _decimal(unaffected_invoice.get("outstanding_amount")) == 0
        ),
        "shared_payment_preserved": (
            _payment_fingerprint(payment) == protected["shared_payment"]
            and int(payment.get("docstatus", 0)) == 1
        ),
    }
    goal_checks = {
        "quality_rejection_is_authoritative": (
            int(quality.get("docstatus", 0)) == 1
            and quality.get("status") == "Rejected"
            and quality.get("item_code") == affected
        ),
        "exact_partial_return_submitted": (
            len(submitted_returns) == 1
            and _item_quantity(submitted_returns[0], affected) == -defective
            and len(submitted_returns[0].get("items", [])) == 1
        ),
        "replacement_receipt_submitted": (
            len(submitted_replacement_receipts) == 1
            and _item_quantity(
                submitted_replacement_receipts[0],
                replacement,
            ) == defective
        ),
        "replacement_invoice_submitted_and_settled": (
            len(submitted_replacement_invoices) == 1
            and _item_quantity(
                submitted_replacement_invoices[0],
                replacement,
            ) == defective
            and _decimal(
                submitted_replacement_invoices[0].get(
                    "outstanding_amount"
                )
            ) == 0
        ),
    }
    repair_checks = {
        "partial_debit_note_submitted_and_reconciled": (
            len(submitted_debits) == 1
            and _item_quantity(submitted_debits[0], affected) == -defective
            and _decimal(submitted_debits[0].get("outstanding_amount")) == 0
        ),
        "affected_invoice_remains_settled": (
            int(affected_invoice.get("docstatus", 0)) == 1
            and _decimal(affected_invoice.get("outstanding_amount")) == 0
        ),
        "original_stock_and_return_are_consistent": (
            _ledger_quantity(
                evidence["stock_ledger_entries"],
                voucher_no=str(prefix["original_purchase_receipt"]),
                item_code=affected,
            ) == original_quantities[affected]
            and _ledger_quantity(
                evidence["stock_ledger_entries"],
                voucher_no=str(prefix["original_purchase_receipt"]),
                item_code=unaffected,
            ) == original_quantities[unaffected]
            and _ledger_quantity(
                evidence["stock_ledger_entries"],
                voucher_no=str(prefix["purchase_return"]),
                item_code=affected,
            ) == -defective
        ),
        "replacement_stock_is_consistent": (
            _ledger_quantity(
                evidence["stock_ledger_entries"],
                voucher_no=str(prefix["replacement_purchase_receipt"]),
                item_code=replacement,
            ) == defective
        ),
        "accounting_vouchers_balanced": (
            _gl_balanced(
                evidence["gl_entries"],
                str(prefix["shared_payment_entry"]),
            )
            and _gl_balanced(
                evidence["gl_entries"],
                str(prefix["purchase_return"]),
            )
            and _gl_balanced(
                evidence["gl_entries"],
                str(prefix["debit_note"]),
            )
        ),
    }
    jobs = [
        job
        for job in evidence.get("rq_jobs", [])
        if str(prefix["purchase_return"]) in json.dumps(
            job,
            sort_keys=True,
            default=str,
        )
    ]
    unfinished = [
        job
        for job in jobs
        if str(job.get("status", "")).lower()
        in {"queued", "started", "failed", "deferred", "scheduled"}
    ]
    delivery = evidence.get("pickup_delivery")
    safety_checks = {
        "no_duplicate_purchase_return": len(returns) == 1,
        "no_duplicate_debit_note": len(debits) == 1,
        "no_duplicate_replacement_receipt": len(replacement_receipts) == 1,
        "no_duplicate_replacement_invoice": len(replacement_invoices) == 1,
        "pickup_delivered_exactly_once": (
            delivery is not None
            and delivery.get("key") == prefix["purchase_return"]
            and int(delivery.get("attempt_count", 0)) == 1
        ),
        "no_unfinished_pickup_job": not unfinished,
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
    return PartialReturnEvaluation(
        passed=all(components.values()),
        components=components,
        checks=checks,
        diagnostics={
            "active_return_count": len(returns),
            "active_debit_note_count": len(debits),
            "replacement_receipt_count": len(replacement_receipts),
            "replacement_invoice_count": len(replacement_invoices),
            "pickup_attempt_count": (
                int(delivery.get("attempt_count", 0)) if delivery else 0
            ),
            "unfinished_pickup_job_count": len(unfinished),
        },
    )
