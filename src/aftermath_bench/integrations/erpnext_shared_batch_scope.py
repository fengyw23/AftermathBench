from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


SHARED_BATCH_RECOVERY_SIGNATURES = {
    "request_not_reached": "submit_missing_corrective_branch",
    "job_card_committed_certificate_delivered_response_lost": (
        "preserve_job_card_and_certificate_complete_manufacture"
    ),
    "job_card_committed_certificate_enqueue_failed": (
        "requeue_missing_certificate_complete_manufacture"
    ),
    "job_card_committed_certificate_job_pending": (
        "drain_existing_certificate_job_complete_manufacture"
    ),
}

_UNFINISHED_JOB_STATUSES = {
    "queued",
    "started",
    "failed",
    "deferred",
    "scheduled",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _job_observation(evidence: dict[str, Any]) -> dict[str, Any]:
    document = evidence["corrective_job_card"]
    return {
        "docstatus": int(document.get("docstatus", 0)),
        "total_completed_qty": document.get("total_completed_qty"),
    }


def _delivery_observation(evidence: dict[str, Any]) -> dict[str, Any]:
    delivery = evidence.get("certificate_delivery")
    if not isinstance(delivery, dict):
        return {"delivered": False}
    return {
        "delivered": True,
        "idempotency_key": delivery.get("key")
        or delivery.get("idempotency_key"),
        "attempt_count": delivery.get("attempt_count"),
    }


def _queue_observation(evidence: dict[str, Any]) -> dict[str, Any]:
    statuses = sorted(
        str(job.get("status", "")).lower()
        for job in evidence.get("rq_jobs", [])
        if str(job.get("status", "")).lower() in _UNFINISHED_JOB_STATUSES
    )
    return {"unfinished_count": len(statuses), "statuses": statuses}


def build_shared_batch_scope_decision_matrix(
    boundary_reports: dict[str, tuple[Path, dict[str, Any]]],
    *,
    scenario_id: str,
) -> dict[str, Any]:
    """Build a decision matrix only from replayed, model-queryable evidence.

    The three surfaces correspond exactly to ordinary public tools: reading
    the failed Job Card, reading the idempotent external delivery, and listing
    background jobs.  No hidden fault label or author-written state summary is
    used to distinguish the four recovery scopes.
    """

    expected = set(SHARED_BATCH_RECOVERY_SIGNATURES)
    if set(boundary_reports) != expected:
        missing = sorted(expected - set(boundary_reports))
        extra = sorted(set(boundary_reports) - expected)
        raise ValueError(
            f"shared-batch boundaries differ from the matched group: "
            f"missing={missing}, extra={extra}"
        )

    rows: list[dict[str, Any]] = []
    for variant in SHARED_BATCH_RECOVERY_SIGNATURES:
        path, report = boundary_reports[variant]
        if str(report.get("scenario_id", "")) != scenario_id:
            raise ValueError(f"boundary {variant} has a different scenario id")
        if str(report.get("variant", "")) != variant:
            raise ValueError(f"boundary file does not contain variant {variant}")
        if not bool(report.get("boundary_validation", {}).get("passed", False)):
            raise ValueError(f"boundary {variant} did not pass native validation")
        evidence = report.get("boundary_evidence")
        if not isinstance(evidence, dict):
            raise TypeError(f"boundary {variant} has no native evidence")
        rows.append(
            {
                "variant": variant,
                "recovery_signature": SHARED_BATCH_RECOVERY_SIGNATURES[variant],
                "source_boundary_sha256": _sha256(path),
                "observations": {
                    "corrective_job_card": _job_observation(evidence),
                    "certificate_delivery": _delivery_observation(evidence),
                    "background_jobs": _queue_observation(evidence),
                },
            }
        )

    return {
        "schema_version": "1.0",
        "scenario_id": scenario_id,
        "source": "replayed native ERPNext failure boundaries",
        "observation_provenance": {
            "corrective_job_card": "get_document(Job Card) at the failure boundary",
            "certificate_delivery": (
                "get_external_delivery for the idempotency key at the failure boundary"
            ),
            "background_jobs": (
                "find_background_jobs for the corrective Job Card at the failure boundary"
            ),
        },
        "rows": rows,
    }


__all__ = [
    "SHARED_BATCH_RECOVERY_SIGNATURES",
    "build_shared_batch_scope_decision_matrix",
]
