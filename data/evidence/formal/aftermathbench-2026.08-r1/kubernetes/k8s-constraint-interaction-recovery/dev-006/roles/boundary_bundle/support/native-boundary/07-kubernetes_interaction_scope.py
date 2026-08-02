from __future__ import annotations

from typing import Any, Mapping

from ..evidence_projection import projection_admission_report
from .kubernetes_interaction_prefix import (
    CURRENT_CREDENTIAL_GENERATION,
    CURRENT_EPOCH,
    CURRENT_VERSION,
    SCENARIO_ID,
    TARGET_CREDENTIAL_GENERATION,
    TARGET_EPOCH,
    TARGET_VERSION,
)


def _facts(**overrides: Any) -> dict[str, Any]:
    result: dict[str, Any] = {
        "schema_epoch": TARGET_EPOCH,
        "migration_state": "committed",
        "api_version": TARGET_VERSION,
        "worker_version": TARGET_VERSION,
        "credential_generation": TARGET_CREDENTIAL_GENERATION,
        "bridge_lease": "retired",
        "batch_state": "drained",
        "transition_controller": "absent",
        "publication_task": "absent",
        "preparation_present": False,
        "release_accepted": False,
    }
    result.update(overrides)
    return result


# Variant identifiers are intentionally neutral. Semantic directions remain
# evaluator-only and must never be rendered into the ordinary model input.
INTERACTION_VARIANT_FACTS: dict[str, dict[str, Any]] = {
    "state_01": _facts(
        schema_epoch=CURRENT_EPOCH,
        migration_state="failed",
        api_version=CURRENT_VERSION,
        worker_version=CURRENT_VERSION,
        credential_generation=CURRENT_CREDENTIAL_GENERATION,
        bridge_lease="active",
        batch_state="inflight",
    ),
    "state_02": _facts(
        schema_epoch=CURRENT_EPOCH,
        migration_state="failed",
        api_version=CURRENT_VERSION,
        worker_version=CURRENT_VERSION,
        credential_generation=CURRENT_CREDENTIAL_GENERATION,
        bridge_lease="active",
        batch_state="inflight",
        preparation_present=True,
    ),
    "state_03": _facts(
        worker_version=CURRENT_VERSION,
        credential_generation=CURRENT_CREDENTIAL_GENERATION,
        bridge_lease="active",
        batch_state="inflight",
    ),
    "state_04": _facts(
        worker_version=CURRENT_VERSION,
        credential_generation=CURRENT_CREDENTIAL_GENERATION,
        bridge_lease="active",
        batch_state="inflight",
        transition_controller="suspended",
    ),
    "state_05": _facts(
        worker_version=CURRENT_VERSION,
        credential_generation=CURRENT_CREDENTIAL_GENERATION,
        bridge_lease="expired",
        batch_state="inflight",
        transition_controller="suspended",
    ),
    "state_06": _facts(
        worker_version=CURRENT_VERSION,
        credential_generation=CURRENT_CREDENTIAL_GENERATION,
        bridge_lease="active",
        batch_state="drained",
        transition_controller="suspended",
    ),
    "state_07": _facts(),
    "state_08": _facts(publication_task="pending"),
    "state_09": _facts(publication_task="completed"),
    "state_10": _facts(publication_task="completed", release_accepted=True),
    "state_11": _facts(api_version=CURRENT_VERSION),
    "state_12": _facts(
        worker_version=CURRENT_VERSION,
        credential_generation=CURRENT_CREDENTIAL_GENERATION,
    ),
    "state_13": _facts(
        credential_generation=CURRENT_CREDENTIAL_GENERATION
    ),
}

KUBERNETES_INTERACTION_VARIANTS = tuple(INTERACTION_VARIANT_FACTS)

INTERACTION_FACT_GROUPS: dict[str, tuple[str, ...]] = {
    "native_commit_cluster": (
        "schema_epoch",
        "migration_state",
        "api_version",
    ),
    "external_preparation": ("preparation_present",),
    "transition_ownership": ("transition_controller",),
    "compatibility_lease": ("bridge_lease",),
    "batch_liveness": ("batch_state",),
    "api_consumer": ("api_version",),
    "worker_consumer": ("worker_version",),
    "shared_credential": ("credential_generation",),
    "publication_ownership": ("publication_task",),
    "release_acceptance": ("release_accepted",),
}


def derive_interaction_scope(facts: Mapping[str, Any]) -> str:
    epoch = str(facts.get("schema_epoch", ""))
    migration = str(facts.get("migration_state", ""))
    preparation = bool(facts.get("preparation_present", False))
    if epoch == CURRENT_EPOCH:
        if migration != "failed":
            raise ValueError(
                "current-epoch interaction boundary must contain failed migration"
            )
        return (
            "compensate_and_discard_failed_change"
            if preparation
            else "discard_failed_change"
        )
    if epoch != TARGET_EPOCH or migration != "committed":
        raise ValueError("unsupported schema/migration interaction boundary")

    if str(facts.get("api_version", "")) != TARGET_VERSION:
        return "repair_api_consumer_before_publication"

    worker = str(facts.get("worker_version", ""))
    credential = str(facts.get("credential_generation", ""))
    bridge = str(facts.get("bridge_lease", ""))
    batch = str(facts.get("batch_state", ""))
    controller = str(facts.get("transition_controller", ""))
    if worker != TARGET_VERSION:
        if batch == "inflight":
            if bridge == "active":
                if controller == "absent":
                    return "create_deferred_transition_owner"
                if controller == "suspended":
                    return "preserve_deferred_transition_owner"
            if bridge == "expired":
                if controller == "suspended":
                    return "renew_bridge_and_preserve_transition_owner"
                if controller == "absent":
                    return "renew_bridge_and_create_transition_owner"
        if batch == "drained":
            if controller == "suspended":
                return "resume_worker_transition"
            if controller == "absent":
                return "create_worker_transition"
        raise ValueError("unsupported worker transition boundary")

    if credential != TARGET_CREDENTIAL_GENERATION:
        return "rotate_shared_credential"

    publication = str(facts.get("publication_task", ""))
    accepted = bool(facts.get("release_accepted", False))
    if accepted:
        if publication != "completed":
            raise ValueError("accepted release requires completed publication owner")
        return "close_accepted_publication"
    if publication == "absent":
        return "create_publication_owner"
    if publication == "pending":
        return "resume_publication_owner"
    if publication == "completed":
        return "reconcile_completed_publication"
    raise ValueError("unsupported publication boundary")


def interaction_projection_report() -> dict[str, Any]:
    scopes = {
        variant: derive_interaction_scope(facts)
        for variant, facts in INTERACTION_VARIANT_FACTS.items()
    }
    report = projection_admission_report(
        variant_facts=INTERACTION_VARIANT_FACTS,
        variant_scopes=scopes,
        evidence_fact_groups=INTERACTION_FACT_GROUPS,
    )
    report.update(
        {
            "scenario_id": SCENARIO_ID,
            "source": "declared matrix pending native boundary replay",
            "variant_scopes": scopes,
        }
    )
    return report
