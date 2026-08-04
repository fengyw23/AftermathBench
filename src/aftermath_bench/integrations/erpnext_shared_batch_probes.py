from __future__ import annotations

from typing import Any

from .erpnext_shared_batch_agent import (
    ERPNextSharedBatchEnvironment,
    reference_shared_batch_recovery,
)

SHARED_BATCH_INTERACTION_PROBE = "repair_then_cancel_customer_reservation"


def run_shared_batch_interaction_probe(
    environment: ERPNextSharedBatchEnvironment,
    *,
    prefix: dict[str, Any],
) -> tuple[dict[str, Any], ...]:
    """Replay a plausible over-repair that violates a shared obligation.

    The probe first performs the ordinary reference recovery and then cancels
    the already-valid stock reservation supporting the secondary production
    branch.  It is intentionally wrong, but every event uses a model-visible
    public tool.  Admission uses its native before/after evaluations as a
    witness that repairing the failed branch can conflict with preservation.
    """

    trace = list(reference_shared_batch_recovery(environment))
    arguments = {
        "doctype": "Stock Reservation Entry",
        "name": prefix["stock_reservation_entry"],
    }
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
            "native interaction probe could not cancel the protected reservation: "
            f"{result}"
        )
    return tuple(trace)


__all__ = [
    "SHARED_BATCH_INTERACTION_PROBE",
    "run_shared_batch_interaction_probe",
]
