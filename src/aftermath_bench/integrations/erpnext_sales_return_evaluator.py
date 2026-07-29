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
        document for document in documents if int(document.get("docstatus", 0)) != 2
    ]


def _submitted(documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        document for document in documents if int(document.get("docstatus", 0)) == 1
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
            "received_amount": payment.get("received_amount"),
            "references": sorted(
                str(reference.get("reference_name"))
                for reference in payment.get("references", [])
            ),
        },
        sort_keys=True,
        separators=(",", ":"),
    )


@dataclass(frozen=True)
class SalesReturnEvaluation:
    passed: bool
    components: dict[str, bool]
    checks: dict[str, bool]
    diagnostics: dict[str, Any]

    @property
    def failures(self) -> tuple[str, ...]:
        return tuple(name for name, passed in self.checks.items() if not passed)


def evaluate_sales_return_recovery(
    evidence: dict[str, Any],
    *,
    prefix: dict[str, Any],
) -> SalesReturnEvaluation:
    defective = _decimal(prefix["defective_quantity"])
    affected = str(prefix["affected_item"])
    unaffected = str(prefix["unaffected_item"])
    replacement = str(prefix["replacement_item"])
    original_quantities = {
        key: _decimal(value) for key, value in prefix["original_quantities"].items()
    }

    returns = _active(evidence.get("sales_returns", []))
    credit_notes = _active(evidence.get("credit_notes", []))
    replacement_deliveries = _active(evidence.get("replacement_delivery_notes", []))
    replacement_invoices = _active(evidence.get("replacement_invoices", []))
    submitted_returns = _submitted(returns)
    submitted_credits = _submitted(credit_notes)
    submitted_deliveries = _submitted(replacement_deliveries)
    submitted_invoices = _submitted(replacement_invoices)

    original_order = evidence["original_sales_order"]
    original_delivery = evidence["original_delivery_note"]
    affected_invoice = evidence["affected_invoice"]
    unaffected_invoice = evidence["unaffected_invoice"]
    payment = evidence["shared_payment_entry"]
    inspection = evidence["quality_inspection"]
    protected = prefix["protected_fingerprints"]
    preservation_checks = {
        "original_sales_order_preserved": (
            protected_fingerprint("sales_order", original_order)
            == protected["original_sales_order"]
            and int(original_order.get("docstatus", 0)) == 1
        ),
        "original_delivery_preserved": (
            protected_fingerprint("delivery_note", original_delivery)
            == protected["original_delivery_note"]
            and int(original_delivery.get("docstatus", 0)) == 1
        ),
        "unaffected_invoice_preserved": (
            protected_fingerprint("sales_invoice", unaffected_invoice)
            == protected["unaffected_invoice"]
            and int(unaffected_invoice.get("docstatus", 0)) == 1
            and _decimal(unaffected_invoice.get("outstanding_amount")) == 0
        ),
        "shared_customer_payment_preserved": (
            _payment_fingerprint(payment) == protected["shared_payment"]
            and int(payment.get("docstatus", 0)) == 1
        ),
    }
    goal_checks = {
        "customer_rejection_is_authoritative": (
            int(inspection.get("docstatus", 0)) == 1
            and inspection.get("status") == "Rejected"
            and inspection.get("item_code") == affected
        ),
        "exact_partial_sales_return_submitted": (
            len(submitted_returns) == 1
            and _item_quantity(submitted_returns[0], affected) == -defective
            and len(submitted_returns[0].get("items", [])) == 1
        ),
        "replacement_delivery_submitted": (
            len(submitted_deliveries) == 1
            and _item_quantity(submitted_deliveries[0], replacement) == defective
        ),
        "replacement_invoice_submitted_and_settled": (
            len(submitted_invoices) == 1
            and _item_quantity(submitted_invoices[0], replacement) == defective
            and _decimal(submitted_invoices[0].get("outstanding_amount")) == 0
        ),
    }
    repair_checks = {
        "partial_credit_note_submitted_and_reconciled": (
            len(submitted_credits) == 1
            and _item_quantity(submitted_credits[0], affected) == -defective
            and _decimal(submitted_credits[0].get("outstanding_amount")) == 0
        ),
        "affected_invoice_remains_settled": (
            int(affected_invoice.get("docstatus", 0)) == 1
            and _decimal(affected_invoice.get("outstanding_amount")) == 0
        ),
        "original_delivery_and_return_stock_are_consistent": (
            _ledger_quantity(
                evidence["stock_ledger_entries"],
                voucher_no=str(prefix["original_delivery_note"]),
                item_code=affected,
            )
            == -original_quantities[affected]
            and _ledger_quantity(
                evidence["stock_ledger_entries"],
                voucher_no=str(prefix["original_delivery_note"]),
                item_code=unaffected,
            )
            == -original_quantities[unaffected]
            and _ledger_quantity(
                evidence["stock_ledger_entries"],
                voucher_no=str(prefix["sales_return"]),
                item_code=affected,
            )
            == defective
        ),
        "replacement_delivery_stock_is_consistent": (
            _ledger_quantity(
                evidence["stock_ledger_entries"],
                voucher_no=str(prefix["replacement_delivery_note"]),
                item_code=replacement,
            )
            == -defective
        ),
        "accounting_vouchers_balanced": (
            _gl_balanced(
                evidence["gl_entries"],
                str(prefix["shared_payment_entry"]),
            )
            and _gl_balanced(
                evidence["gl_entries"],
                str(prefix["credit_note"]),
            )
        ),
    }
    jobs = [
        job
        for job in evidence.get("rq_jobs", [])
        if str(prefix["sales_return"])
        in json.dumps(
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
        "no_duplicate_sales_return": len(returns) == 1,
        "no_duplicate_credit_note": len(credit_notes) == 1,
        "no_duplicate_replacement_delivery": len(replacement_deliveries) == 1,
        "no_duplicate_replacement_invoice": len(replacement_invoices) == 1,
        "customer_pickup_effect_applied_exactly_once": (
            delivery is not None
            and delivery.get("key") == prefix["sales_return"]
        ),
        "no_unfinished_customer_pickup_job": not unfinished,
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
    return SalesReturnEvaluation(
        passed=all(components.values()),
        components=components,
        checks=checks,
        diagnostics={
            "active_sales_return_count": len(returns),
            "active_credit_note_count": len(credit_notes),
            "replacement_delivery_count": len(replacement_deliveries),
            "replacement_invoice_count": len(replacement_invoices),
            "pickup_attempt_count": (
                int(delivery.get("attempt_count", 0)) if delivery else 0
            ),
            "redundant_pickup_attempt_count": (
                max(int(delivery.get("attempt_count", 0)) - 1, 0)
                if delivery
                else 0
            ),
            "unfinished_pickup_job_count": len(unfinished),
        },
    )
