from __future__ import annotations

import hashlib
import json
import time
from decimal import Decimal
from typing import Any

from .erpnext_inventory_cost_evidence import ERPNextInventoryCostEvidenceCollector
from .erpnext_shared_batch_evaluator import shared_batch_document_fingerprint
from .erpnext_stack import ERPNextStack
from .frappe import FrappeHTTPAdapter

INVENTORY_COST_VARIANTS = (
    "request_not_reached",
    "voucher_committed_repost_queued_attested_response_lost",
    "voucher_committed_repost_queued_attestation_pending",
    "voucher_committed_repost_completed_attestation_pending",
)


def _canonical_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), default=str
        ).encode("utf-8")
    ).hexdigest()


_STOCK_LEDGER_SEMANTIC_FIELDS = (
    "voucher_type",
    "voucher_no",
    "actual_qty",
    "qty_after_transaction",
    "valuation_rate",
    "stock_value",
    "stock_value_difference",
    "is_cancelled",
    "item_code",
    "warehouse",
)
_GENERAL_LEDGER_SEMANTIC_FIELDS = (
    "voucher_type",
    "voucher_no",
    "debit",
    "credit",
    "is_cancelled",
    "account",
    "against",
)


def _semantic_rows(
    rows: list[dict[str, Any]], fields: tuple[str, ...]
) -> list[dict[str, Any]]:
    """Remove runtime identities and timestamps from a ledger projection."""

    projected = [{field: row.get(field) for field in fields} for row in rows]
    return sorted(
        projected,
        key=lambda row: json.dumps(row, sort_keys=True, default=str),
    )


def _active(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [row for row in rows if int(row.get("is_cancelled", 0)) == 0]


def _repost_state(evidence: dict[str, Any]) -> str:
    owners = evidence.get("repost_item_valuations", [])
    if not owners:
        return "absent"
    return "+".join(sorted(str(owner.get("status", "unknown")) for owner in owners))


def project_inventory_cost_dimensions(evidence: dict[str, Any]) -> dict[str, str]:
    lcv = evidence["landed_cost_voucher"]
    stock_rows = [
        row
        for row in evidence.get("stock_ledger_entries", [])
        if int(row.get("is_cancelled", 0)) == 0
    ]
    gl_rows = [
        row
        for row in evidence.get("gl_entries", [])
        if int(row.get("is_cancelled", 0)) == 0
    ]
    delivery = evidence.get("settlement_attestation")
    unfinished_jobs = [
        str(job.get("status", "unknown"))
        for job in evidence.get("rq_jobs", [])
        if str(job.get("status", "")).lower()
        in {"queued", "started", "failed", "deferred", "scheduled"}
    ]
    attestation = (
        "delivered"
        if isinstance(delivery, dict)
        else "queued:" + "+".join(sorted(unfinished_jobs))
        if unfinished_jobs
        else "absent"
    )
    return {
        "landed_cost_voucher": (
            "submitted" if int(lcv.get("docstatus", 0)) == 1 else "draft"
        ),
        "stock_ledger": _canonical_sha256(
            _semantic_rows(stock_rows, _STOCK_LEDGER_SEMANTIC_FIELDS)
        ),
        "gl_entries": _canonical_sha256(
            _semantic_rows(gl_rows, _GENERAL_LEDGER_SEMANTIC_FIELDS)
        ),
        "reposting_owner": _repost_state(evidence),
        "external_attestation": attestation,
    }


def evaluate_inventory_cost_terminal(
    evidence: dict[str, Any],
    *,
    prefix: dict[str, Any],
    fixture: dict[str, Any],
) -> dict[str, Any]:
    lcv = evidence["landed_cost_voucher"]
    receipt = evidence["shared_purchase_receipt"]
    landed = fixture["landed_cost"]
    shared = fixture["shared_component"]
    primary = fixture["primary_branch"]
    secondary = fixture["secondary_branch"]
    active_receipt_sle = [
        row
        for row in _active(evidence.get("stock_ledger_entries", []))
        if str(row.get("voucher_no")) == str(prefix["shared_purchase_receipt"])
        and str(row.get("item_code")) == str(prefix["shared_component"])
    ]
    active_gl = [
        row
        for row in _active(evidence.get("gl_entries", []))
        if str(row.get("voucher_no")) == str(prefix["shared_purchase_receipt"])
    ]
    receipt_items = receipt.get("items", [])
    allocations = sorted(
        Decimal(str(row.get("landed_cost_voucher_amount", 0)))
        for row in receipt_items
        if str(row.get("item_code")) == str(prefix["shared_component"])
    )
    expected_allocations = sorted(
        (
            Decimal(str(landed["primary_allocation"])),
            Decimal(str(landed["secondary_allocation"])),
        )
    )
    per_unit_charge = Decimal(str(landed["amount"])) / Decimal(
        str(shared["received_quantity"])
    )
    expected_rate = Decimal(str(shared["valuation_rate"])) + per_unit_charge
    valuation_rates = {
        Decimal(str(row.get("valuation_rate", 0))) for row in active_receipt_sle
    }
    reposts = evidence.get("repost_item_valuations", [])
    delivery = evidence.get("settlement_attestation")
    protected_documents = {
        "primary_bom": evidence["primary_bom"],
        "secondary_bom": evidence["secondary_bom"],
        "primary_work_order": evidence["primary_work_order"],
        "secondary_work_order": evidence["secondary_work_order"],
        "customer_reservation": evidence["customer_reservation"],
        "stock_reservation": evidence["stock_reservation_entry"],
        "unrelated_receipt": evidence["unrelated_receipt"],
    }
    actual_fingerprints = {
        key: shared_batch_document_fingerprint(document)
        for key, document in protected_documents.items()
    }
    checks = {
        "landed_cost_voucher_submitted": int(lcv.get("docstatus", 0)) == 1,
        "single_landed_cost_voucher": len(evidence["landed_cost_vouchers"]) == 1,
        "native_allocations_applied": allocations == expected_allocations,
        "receipt_valuation_rate_updated": (
            len(active_receipt_sle) == 2 and valuation_rates == {expected_rate}
        ),
        "one_completed_repost_owner": (
            len(reposts) == 1
            and str(reposts[0].get("status", "")).lower() == "completed"
        ),
        "general_ledger_balanced": (
            bool(active_gl)
            and sum(Decimal(str(row.get("debit", 0))) for row in active_gl)
            == sum(Decimal(str(row.get("credit", 0))) for row in active_gl)
        ),
        "primary_branch_preserved": (
            int(evidence["primary_work_order"].get("docstatus", 0)) == 1
            and Decimal(str(evidence["primary_work_order"].get("produced_qty", 0)))
            == Decimal(str(primary["output_quantity"]))
        ),
        "secondary_branch_preserved": (
            int(evidence["secondary_work_order"].get("docstatus", 0)) == 1
            and Decimal(str(evidence["secondary_work_order"].get("produced_qty", 0)))
            == Decimal(str(secondary["output_quantity"]))
        ),
        "reservation_preserved": (
            int(evidence["stock_reservation_entry"].get("docstatus", 0)) == 1
            and Decimal(
                str(evidence["stock_reservation_entry"].get("reserved_qty", 0))
            )
            == Decimal(str(fixture["customer_reservation"]["quantity"]))
        ),
        "protected_documents_unchanged": (
            actual_fingerprints == prefix["protected_fingerprints"]
        ),
        "attestation_exactly_once": (
            isinstance(delivery, dict)
            and int(delivery.get("attempt_count", 0)) == 1
            and (delivery.get("key") or delivery.get("idempotency_key"))
            == fixture["external_attestation"]["idempotency_key"]
        ),
    }
    components = {
        "goal_completion": all(
            checks[name]
            for name in (
                "landed_cost_voucher_submitted",
                "native_allocations_applied",
                "receipt_valuation_rate_updated",
            )
        ),
        "repair_completeness": all(
            checks[name]
            for name in (
                "one_completed_repost_owner",
                "general_ledger_balanced",
                "attestation_exactly_once",
            )
        ),
        "preservation": all(
            checks[name]
            for name in (
                "primary_branch_preserved",
                "secondary_branch_preserved",
                "reservation_preserved",
                "protected_documents_unchanged",
            )
        ),
        "protocol_safety": all(
            checks[name]
            for name in (
                "single_landed_cost_voucher",
                "one_completed_repost_owner",
                "attestation_exactly_once",
            )
        ),
    }
    return {
        "passed": all(components.values()),
        "components": components,
        "checks": checks,
        "failures": [name for name, passed in checks.items() if not passed],
    }


def wait_for_attestation(
    collector: ERPNextInventoryCostEvidenceCollector,
    prefix: dict[str, Any],
    *,
    timeout_seconds: float = 30,
) -> dict[str, Any] | None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        delivery = collector.get_delivery(str(prefix["attestation_reference"]))
        if delivery is not None:
            return delivery
        time.sleep(0.5)
    return None


def reference_inventory_cost_recovery(
    *,
    adapter: FrappeHTTPAdapter,
    collector: ERPNextInventoryCostEvidenceCollector,
    stack: ERPNextStack,
    worker_control: Any,
    prefix: dict[str, Any],
) -> tuple[dict[str, Any], ...]:
    """State-driven control using the same document and operations surface."""

    trace: list[dict[str, Any]] = []

    def record(tool: str, arguments: dict[str, Any], result: Any) -> None:
        trace.append({"tool": tool, "arguments": arguments, "result": result})

    evidence = collector.collect(prefix)
    record("inspect_inventory_cost_state", {}, project_inventory_cost_dimensions(evidence))
    lcv = evidence["landed_cost_voucher"]
    if int(lcv.get("docstatus", 0)) == 0:
        worker_control.stop()
        result = adapter.submit_document(
            "Landed Cost Voucher", str(prefix["landed_cost_voucher"])
        )
        record(
            "submit_document",
            {"doctype": "Landed Cost Voucher", "name": prefix["landed_cost_voucher"]},
            result,
        )
        evidence = collector.collect(prefix)
    pending_reposts = [
        owner
        for owner in evidence.get("repost_item_valuations", [])
        if str(owner.get("status", "")).lower() in {"queued", "in progress"}
    ]
    if pending_reposts:
        stack.process_repost_item_valuation_queue()
        record(
            "process_repost_item_valuation_queue",
            {"owners": [owner["name"] for owner in pending_reposts]},
            {"processed": True},
        )
    delivery = collector.get_delivery(str(prefix["attestation_reference"]))
    if delivery is None:
        jobs = collector.find_background_jobs(str(prefix["landed_cost_voucher"]))
        unfinished = [
            job
            for job in jobs
            if str(job.get("status", "")).lower()
            in {"queued", "started", "failed", "deferred", "scheduled"}
        ]
        if not unfinished:
            result = stack.enqueue_document_webhook(
                doctype="Landed Cost Voucher",
                document_name=str(prefix["landed_cost_voucher"]),
                webhook_name=str(prefix["settlement_webhook"]),
            )
            record("enqueue_document_webhook", {}, result)
        worker_control.start()
        record("resume_workers", {}, {"started": True})
        delivery = wait_for_attestation(collector, prefix)
        record("wait_for_external_delivery", {}, delivery)
    final = collector.collect(prefix)
    record("verify_inventory_cost_state", {}, project_inventory_cost_dimensions(final))
    return tuple(trace)


__all__ = [
    "INVENTORY_COST_VARIANTS",
    "evaluate_inventory_cost_terminal",
    "project_inventory_cost_dimensions",
    "reference_inventory_cost_recovery",
    "wait_for_attestation",
]
