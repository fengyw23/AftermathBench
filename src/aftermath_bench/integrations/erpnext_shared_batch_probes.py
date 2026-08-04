from __future__ import annotations

from typing import Any

from .erpnext_shared_batch_agent import (
    ERPNextSharedBatchEnvironment,
    reference_shared_batch_recovery,
)

SHARED_BATCH_INTERACTION_PROBES = (
    "repair_then_cancel_customer_reservation",
    "repair_then_cancel_accepted_quality_inspection",
    "repair_then_cancel_unrelated_receipt",
)
SHARED_BATCH_INTERACTION_PROBE = SHARED_BATCH_INTERACTION_PROBES[0]


def run_shared_batch_interaction_probe(
    environment: ERPNextSharedBatchEnvironment,
    *,
    prefix: dict[str, Any],
    probe: str = SHARED_BATCH_INTERACTION_PROBE,
) -> tuple[dict[str, Any], ...]:
    """Replay a plausible over-repair that violates a shared obligation.

    The probe first performs the ordinary reference recovery and then cancels
    one already-valid native ERPNext document.  The three supported probes
    target independent protected effects: a customer reservation, an accepted
    quality inspection, and an unrelated receipt.  Each action is intentionally
    wrong, but uses a model-visible public tool.  Admission derives conflicts
    from deterministic native before/after evaluations rather than labels.
    """

    trace = list(reference_shared_batch_recovery(environment))
    targets = {
        "repair_then_cancel_customer_reservation": (
            "Stock Reservation Entry",
            "stock_reservation_entry",
        ),
        "repair_then_cancel_accepted_quality_inspection": (
            "Quality Inspection",
            "accepted_primary_quality_inspection",
        ),
        "repair_then_cancel_unrelated_receipt": (
            "Stock Entry",
            "unrelated_receipt",
        ),
    }
    if probe not in targets:
        raise ValueError(f"unknown shared-batch interaction probe: {probe}")
    doctype, prefix_key = targets[probe]
    arguments = {"doctype": doctype, "name": prefix[prefix_key]}
    result = environment.invoke("cancel_document", **arguments)
    trace.append(
        {
            "tool": "cancel_document",
            "arguments": arguments,
            "result": result,
        }
    )
    if not result.get("ok"):
        raise RuntimeError(
            f"native interaction probe {probe} could not cancel its protected target: "
            f"{result}"
        )
    return tuple(trace)


__all__ = [
    "SHARED_BATCH_INTERACTION_PROBE",
    "SHARED_BATCH_INTERACTION_PROBES",
    "run_shared_batch_interaction_probe",
]
