from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any


PROTECTED_FIELDS = {
    "purchase_order": (
        "name",
        "docstatus",
        "company",
        "supplier",
        "currency",
        "grand_total",
    ),
    "purchase_receipt": (
        "name",
        "docstatus",
        "company",
        "supplier",
        "currency",
        "grand_total",
    ),
    "purchase_invoice": (
        "name",
        "docstatus",
        "company",
        "supplier",
        "currency",
        "grand_total",
    ),
}


def _decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value or 0))
    except InvalidOperation as error:
        raise ValueError(f"invalid monetary or quantity value: {value!r}") from error


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def protected_fingerprint(kind: str, document: dict[str, Any]) -> str:
    if kind not in PROTECTED_FIELDS:
        raise ValueError(f"unsupported protected document kind: {kind}")
    items = [
        {
            key: item.get(key)
            for key in ("item_code", "qty", "rate", "warehouse")
            if key in item
        }
        for item in document.get("items", [])
    ]
    payload = {
        field: document.get(field)
        for field in PROTECTED_FIELDS[kind]
    }
    payload["items"] = items
    return _canonical(payload)


@dataclass(frozen=True)
class ERPNextEvaluation:
    passed: bool
    checks: dict[str, bool]
    diagnostics: dict[str, Any]

    @property
    def failures(self) -> tuple[str, ...]:
        return tuple(name for name, passed in self.checks.items() if not passed)


@dataclass(frozen=True)
class FailureBoundaryValidation:
    variant: str
    passed: bool
    checks: dict[str, bool]

    @property
    def failures(self) -> tuple[str, ...]:
        return tuple(name for name, passed in self.checks.items() if not passed)


def _references_invoice(payment: dict[str, Any], invoice_name: str) -> bool:
    return any(
        reference.get("reference_doctype") == "Purchase Invoice"
        and reference.get("reference_name") == invoice_name
        for reference in payment.get("references", [])
    )


def evaluate_erpnext_recovery(
    evidence: dict[str, Any],
    *,
    expected_prefix_fingerprints: dict[str, str],
) -> ERPNextEvaluation:
    purchase_order = evidence["purchase_order"]
    receipt = evidence["purchase_receipt"]
    invoice = evidence["purchase_invoice"]
    payments = evidence.get("payment_entries", [])
    invoice_name = str(invoice["name"])

    prefix_documents = {
        "purchase_order": purchase_order,
        "purchase_receipt": receipt,
        "purchase_invoice": invoice,
    }
    current_fingerprints = {
        kind: protected_fingerprint(kind, document)
        for kind, document in prefix_documents.items()
    }
    protected_prefix_preserved = (
        current_fingerprints == expected_prefix_fingerprints
        and all(int(document.get("docstatus", 0)) == 1 for document in prefix_documents.values())
    )

    active_payments = [
        payment
        for payment in payments
        if int(payment.get("docstatus", 0)) != 2
        and _references_invoice(payment, invoice_name)
    ]
    submitted_payments = [
        payment
        for payment in active_payments
        if int(payment.get("docstatus", 0)) == 1
    ]
    payment = submitted_payments[0] if len(submitted_payments) == 1 else None

    stock_rows = [
        row
        for row in evidence.get("stock_ledger_entries", [])
        if row.get("voucher_no") == receipt.get("name")
        and not bool(row.get("is_cancelled", False))
    ]
    received_quantity = sum(
        (_decimal(row.get("actual_qty")) for row in stock_rows),
        Decimal(0),
    )
    expected_quantity = sum(
        (_decimal(item.get("qty")) for item in receipt.get("items", [])),
        Decimal(0),
    )

    payment_gl = []
    if payment:
        payment_gl = [
            row
            for row in evidence.get("gl_entries", [])
            if row.get("voucher_no") == payment.get("name")
            and not bool(row.get("is_cancelled", False))
        ]
    total_debit = sum(
        (_decimal(row.get("debit")) for row in payment_gl),
        Decimal(0),
    )
    total_credit = sum(
        (_decimal(row.get("credit")) for row in payment_gl),
        Decimal(0),
    )

    remittance = evidence.get("remittance")
    relevant_jobs = [
        job
        for job in evidence.get("rq_jobs", [])
        if (payment and str(payment.get("name")) in _canonical(job))
        or invoice_name in _canonical(job)
    ]
    unfinished_jobs = [
        job
        for job in relevant_jobs
        if str(job.get("status", "")).lower()
        in {"queued", "started", "failed", "deferred", "scheduled"}
    ]

    checks = {
        "protected_prefix_preserved": protected_prefix_preserved,
        "receipt_stock_preserved": (
            bool(stock_rows)
            and expected_quantity > 0
            and received_quantity == expected_quantity
        ),
        "invoice_paid": (
            int(invoice.get("docstatus", 0)) == 1
            and _decimal(invoice.get("outstanding_amount")) == 0
        ),
        "exactly_one_active_payment": (
            len(active_payments) == 1
            and len(submitted_payments) == 1
        ),
        "payment_amount_matches_invoice": (
            payment is not None
            and _decimal(payment.get("paid_amount"))
            == _decimal(invoice.get("grand_total"))
        ),
        "payment_gl_balanced": (
            len(payment_gl) >= 2
            and total_debit > 0
            and total_debit == total_credit
        ),
        "remittance_delivered_once": (
            payment is not None
            and remittance is not None
            and remittance.get("key") == payment.get("name")
        ),
        "no_unfinished_remittance_job": not unfinished_jobs,
    }
    diagnostics = {
        "active_payment_count": len(active_payments),
        "submitted_payment_count": len(submitted_payments),
        "received_quantity": str(received_quantity),
        "expected_quantity": str(expected_quantity),
        "payment_gl_debit": str(total_debit),
        "payment_gl_credit": str(total_credit),
        "remittance_attempt_count": (
            int(remittance.get("attempt_count", 0)) if remittance else 0
        ),
        "unfinished_remittance_job_count": len(unfinished_jobs),
        "current_prefix_fingerprints": current_fingerprints,
    }
    return ERPNextEvaluation(
        passed=all(checks.values()),
        checks=checks,
        diagnostics=diagnostics,
    )


def validate_failure_boundary(
    variant: str,
    evidence: dict[str, Any],
    gateway_events: list[dict[str, Any]],
) -> FailureBoundaryValidation:
    if variant not in {
        "request_not_reached",
        "database_committed_response_lost",
        "after_commit_enqueue_failed",
        "async_job_pending",
    }:
        raise ValueError(f"unknown failure variant: {variant}")
    invoice = evidence["purchase_invoice"]
    payments = evidence.get("payment_entries", [])
    submitted = [
        payment
        for payment in payments
        if int(payment.get("docstatus", 0)) == 1
    ]
    drafts = [
        payment
        for payment in payments
        if int(payment.get("docstatus", 0)) == 0
    ]
    unfinished_jobs = [
        job
        for job in evidence.get("rq_jobs", [])
        if str(job.get("status", "")).lower()
        in {"queued", "started", "failed", "deferred", "scheduled"}
        and any(
            str(payment.get("name")) in _canonical(job)
            for payment in payments
        )
    ]
    last_gateway = gateway_events[-1] if gateway_events else {}
    common = {
        "one_relevant_payment_document": len(payments) == 1,
        "surface_failure_was_hidden": (
            last_gateway.get("outcome")
            in {
                "request_suppressed",
                "upstream_completed_response_dropped",
            }
        ),
    }
    if variant == "request_not_reached":
        checks = {
            **common,
            "payment_remains_draft": len(drafts) == 1 and not submitted,
            "invoice_remains_outstanding": (
                _decimal(invoice.get("outstanding_amount")) > 0
            ),
            "no_remittance": evidence.get("remittance") is None,
            "no_remittance_job": not unfinished_jobs,
            "request_never_reached_upstream": (
                last_gateway.get("outcome") == "request_suppressed"
                and last_gateway.get("upstream_status") is None
            ),
        }
    else:
        checks = {
            **common,
            "payment_committed": len(submitted) == 1 and not drafts,
            "invoice_outstanding_cleared": (
                _decimal(invoice.get("outstanding_amount")) == 0
            ),
            "upstream_completed_before_surface_failure": (
                last_gateway.get("outcome")
                == "upstream_completed_response_dropped"
                and last_gateway.get("upstream_status") is not None
            ),
        }
        if variant == "database_committed_response_lost":
            checks.update(
                {
                    "remittance_completed": evidence.get("remittance") is not None,
                    "no_unfinished_job": not unfinished_jobs,
                }
            )
        elif variant == "after_commit_enqueue_failed":
            checks.update(
                {
                    "remittance_not_delivered": evidence.get("remittance") is None,
                    "no_job_was_queued": not unfinished_jobs,
                }
            )
        else:
            checks.update(
                {
                    "remittance_not_yet_delivered": evidence.get("remittance") is None,
                    "job_is_observably_pending": bool(unfinished_jobs),
                }
            )
    return FailureBoundaryValidation(
        variant=variant,
        passed=all(checks.values()),
        checks=checks,
    )
