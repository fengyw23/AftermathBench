from __future__ import annotations

from typing import Any

from ..obligation_interaction_audit import (
    ObligationInteractionAudit,
    analyze_obligation_interactions,
)
from .erpnext_shared_batch_evaluator import evaluate_shared_batch_terminal
from .erpnext_shared_batch_probes import SHARED_BATCH_INTERACTION_PROBES
from .erpnext_shared_batch_projection import project_shared_batch_terminal
from .erpnext_shared_batch_scope import SHARED_BATCH_RECOVERY_SIGNATURES

PROTECTED_SHARED_BATCH_OBLIGATIONS = {
    "accepted_primary_quantity_preserved",
    "secondary_output_preserved",
    "customer_reservation_preserved",
    "shared_supplier_batch_identity_preserved",
    "landed_cost_allocations_preserved",
    "protected_native_documents_unchanged",
}

SHARED_BATCH_ACTIONS = (
    "submit_missing_corrective_job_card",
    "preserve_committed_corrective_job_card",
    "preserve_delivered_certificate",
    "enqueue_missing_certificate",
    "resume_pending_certificate_job",
    "complete_corrective_manufacture",
    *SHARED_BATCH_INTERACTION_PROBES,
)

SHARED_BATCH_GOLD_ACTIONS = {
    "request_not_reached": (
        "submit_missing_corrective_job_card",
        "enqueue_missing_certificate",
        "complete_corrective_manufacture",
    ),
    "job_card_committed_certificate_delivered_response_lost": (
        "preserve_committed_corrective_job_card",
        "preserve_delivered_certificate",
        "complete_corrective_manufacture",
    ),
    "job_card_committed_certificate_enqueue_failed": (
        "preserve_committed_corrective_job_card",
        "enqueue_missing_certificate",
        "complete_corrective_manufacture",
    ),
    "job_card_committed_certificate_job_pending": (
        "preserve_committed_corrective_job_card",
        "resume_pending_certificate_job",
        "complete_corrective_manufacture",
    ),
}


def _boundary_checks(
    failure: dict[str, Any], prefix: dict[str, Any]
) -> dict[str, bool]:
    raw = failure["boundary_evidence"]
    projected = project_shared_batch_terminal(
        raw, prefix=prefix, fixture=prefix["evaluation_fixture"]
    )
    evaluation = evaluate_shared_batch_terminal(
        projected,
        fixture=prefix["evaluation_fixture"],
        protected_fingerprints=prefix["protected_fingerprints"],
    )
    return {str(key): bool(value) for key, value in evaluation["checks"].items()}


def build_shared_batch_obligation_interactions(
    *,
    scenario_id: str,
    prefix: dict[str, Any],
    failures: dict[str, dict[str, Any]],
    probes: dict[str, list[dict[str, Any]]],
) -> tuple[dict[str, Any], ObligationInteractionAudit]:
    expected = set(SHARED_BATCH_RECOVERY_SIGNATURES)
    if set(failures) != expected or set(probes) != expected:
        raise ValueError("obligation evidence does not cover the matched group")

    first_checks = _boundary_checks(failures[next(iter(expected))], prefix)
    obligations = [
        {
            "id": obligation,
            "protected": obligation in PROTECTED_SHARED_BATCH_OBLIGATIONS,
        }
        for obligation in sorted(first_checks)
    ]
    rows = []
    for variant in SHARED_BATCH_RECOVERY_SIGNATURES:
        failure = failures[variant]
        boundary = _boundary_checks(failure, prefix)
        variant_probes = []
        observed_actions = set()
        for probe in probes[variant]:
            result_evaluation = probe.get("result_evaluation", {}).get("checks")
            if not isinstance(result_evaluation, dict):
                raise TypeError(f"probe {variant} has no deterministic result checks")
            if set(result_evaluation) != set(boundary):
                raise ValueError(f"probe {variant} evaluates different obligations")
            action_id = str(probe.get("action_id"))
            if action_id not in SHARED_BATCH_INTERACTION_PROBES:
                raise ValueError(f"probe {variant} has an unexpected action")
            if action_id in observed_actions:
                raise ValueError(f"probe {variant} duplicates action {action_id}")
            observed_actions.add(action_id)
            variant_probes.append(
                {
                    "action_id": action_id,
                    "tool_events": probe["tool_events"],
                    "result_state_sha256": probe["result_state_sha256"],
                    "result_evaluation": {
                        str(key): bool(value)
                        for key, value in result_evaluation.items()
                    },
                }
            )
        if observed_actions != set(SHARED_BATCH_INTERACTION_PROBES):
            raise ValueError(f"probe {variant} does not cover every conflict action")
        rows.append(
            {
                "variant": variant,
                "recovery_signature": SHARED_BATCH_RECOVERY_SIGNATURES[variant],
                "boundary_evaluation": boundary,
                "gold_action_ids": list(SHARED_BATCH_GOLD_ACTIONS[variant]),
                "probes": variant_probes,
            }
        )
    payload = {
        "schema_version": "1.0",
        "scenario_id": scenario_id,
        "source": (
            "native ERPNext before/after evaluator results from public-tool replays"
        ),
        "obligations": obligations,
        "actions": [{"id": action} for action in SHARED_BATCH_ACTIONS],
        "rows": rows,
    }
    return payload, analyze_obligation_interactions(payload)


__all__ = [
    "PROTECTED_SHARED_BATCH_OBLIGATIONS",
    "SHARED_BATCH_ACTIONS",
    "SHARED_BATCH_GOLD_ACTIONS",
    "build_shared_batch_obligation_interactions",
]
