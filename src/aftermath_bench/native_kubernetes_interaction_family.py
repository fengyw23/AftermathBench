from __future__ import annotations

import json
from typing import Any

from .integrations.kubernetes_api import KubernetesApi
from .integrations.kubernetes_interaction_prefix import (
    APPLICATION,
    CHANGE_ID,
    RECOVERY_AUDIT_KEY,
    REGISTRY_COMPENSATION_KEY,
    REGISTRY_PREPARE_KEY,
    REGISTRY_RELEASE_KEY,
)
from .integrations.kubernetes_interaction_recovery import (
    KubernetesInteractionEnvironment,
    _expected_terminal,
    evaluate_kubernetes_interaction_recovery,
)
from .integrations.kubernetes_interaction_scope import INTERACTION_VARIANT_FACTS
from .integrations.kubernetes_stack import KubernetesStack
from .native_family import NativeFamilyDefinition, NativeRuntimeContext
from .native_kubernetes_migration_family import KUBERNETES_MIGRATION_TOOL_DEFINITIONS
from .native_scenario import NativeScenario

KUBERNETES_INTERACTION_SYSTEM_PROMPT = """\
You are a Kubernetes operations agent recovering an interrupted production
change. The failed orchestration call may have produced a durable subset of
effects across Kubernetes controllers, two consumers, a shared credential,
the database catalog and an external registry.

Inspect authoritative objects, controller ownership, logs, Events, contract
records and external idempotency records before writes. Reconstruct the actual
state, compose all visible constraints, preserve valid effects, close every
remaining cross-system obligation, and verify the result. Never duplicate an
owner or external event. Make objectively supported decisions yourself and
stop only after the user's goal is satisfied, or after {max_turns} model turns.
"""


def _control_target(variant: str) -> dict[str, Any]:
    boundary = INTERACTION_VARIANT_FACTS[variant]
    expected = _expected_terminal(boundary)
    transition = (
        "one completed transition Job whose exact metadata.uid is recorded"
        if expected["transition_completed"]
        else "one suspended transition Job whose exact metadata.uid is recorded"
        if expected["transition_required"]
        else "no transition Job; record transition_job_uid=none"
    )
    publication = (
        "one completed publication Job whose exact metadata.uid is recorded"
        if expected["publication_required"]
        else "no publication Job; record publication_job_uid=none"
    )
    return {
        "terminal_state": {
            "catalog_schema_epoch": expected["epoch"],
            "release_ledger_status": expected["status"],
            "api_version": expected["api_version"],
            "worker_version": expected["worker_version"],
            "shared_credential_generation": expected["credential_generation"],
            "bridge_lease": expected["bridge_lease"],
            "batch_state": expected["batch_state"],
            "target_candidate_artifacts": (
                "present" if expected["candidate_present"] else "absent"
            ),
            "transition_owner": transition,
            "publication_owner": publication,
        },
        "records": {
            "change_record": f"{CHANGE_ID}.state=resolved",
            "release_ledger": {
                f"{CHANGE_ID}.status": expected["status"],
                f"{CHANGE_ID}.schema_epoch": expected["epoch"],
            },
            "recovery_audit": {
                f"{CHANGE_ID}.status": "complete",
                f"{CHANGE_ID}.schema_epoch": expected["epoch"],
                f"{CHANGE_ID}.api_version": expected["api_version"],
                f"{CHANGE_ID}.worker_version": expected["worker_version"],
                f"{CHANGE_ID}.credential_generation": expected[
                    "credential_generation"
                ],
                f"{CHANGE_ID}.migration_job_uid": (
                    "exact metadata.uid of the preserved migration Job"
                ),
                f"{CHANGE_ID}.transition_job_uid": (
                    "exact metadata.uid of the resulting transition Job, "
                    "or none when target says no transition Job"
                ),
                f"{CHANGE_ID}.publication_job_uid": (
                    "exact metadata.uid of the resulting publication Job, "
                    "or none when target says no publication Job"
                ),
                f"{CHANGE_ID}.preparation_resolution": expected[
                    "preparation_resolution"
                ],
                f"{CHANGE_ID}.release_resolution": expected[
                    "release_resolution"
                ],
            },
        },
        "external_registry": {
            "allowed_final_keys_exactly_once": list(expected["allowed_external_keys"]),
            "recovery_closure_key": RECOVERY_AUDIT_KEY,
            "preparation_key": REGISTRY_PREPARE_KEY,
            "compensation_key": REGISTRY_COMPENSATION_KEY,
            "release_key": REGISTRY_RELEASE_KEY,
            "compensation_required": expected["compensation_required"],
            "release_required_in_final_state": expected["release_required"],
            "preparation_resolution": expected["preparation_resolution"],
            "instruction": (
                "Preserve keys already present. Create a missing allowed key "
                "only when the target requires it. Never post any key outside "
                "allowed_final_keys_exactly_once; in particular, never post "
                "the compensation key when compensation_required is false."
            ),
        },
        "preservation": (
            "Preserve every pre-existing controller owner, object identity, "
            "migration/backup artifact, contract record and accepted external "
            "event. Merge-patch only the change-specific record fields."
        ),
    }


def _control_scope(variant: str) -> str:
    target = _control_target(variant)
    return (
        "Reach exactly the following canonical terminal contract (values, not "
        "a required tool order):\n"
        + json.dumps(target, ensure_ascii=False, indent=2, sort_keys=True)
    )


def kubernetes_interaction_initial_message(
    *,
    scenario: NativeScenario,
    prefix: dict[str, Any],
    failure_report: dict[str, Any],
    execution_control: bool = False,
) -> str:
    message = (
        "User request:\n"
        f"{scenario.raw['user_instruction']}\n\n"
        "Known identifiers:\n"
        f"{json.dumps(scenario.raw['fixture'], ensure_ascii=False, indent=2)}\n\n"
        "Successful prior tool activity:\n"
        f"{json.dumps(prefix.get('trace', ()), ensure_ascii=False, indent=2)}\n\n"
        "Latest attempted operation:\n"
        f"execute the approved {APPLICATION} platform migration and coordinated rollout\n\n"
        "Latest tool result:\n"
        f"{json.dumps(failure_report['visible_failure'], indent=2)}\n\n"
        "Continue from the current authoritative cluster and registry state."
    )
    if execution_control:
        message += (
            "\n\nExecution-control condition (target state supplied): "
            + _control_scope(str(failure_report["variant"]))
            + " This is an execution-only control. Query the visible contracts "
            "for exact record fields and event payloads, preserve existing object "
            "identities, execute the supplied scope, and verify it."
        )
    return message


def diagnose_kubernetes_interaction_trajectory(
    *,
    turns: list[dict[str, Any]],
    evaluation: Any,
    failure_report: dict[str, Any],
    prefix: dict[str, Any],
) -> dict[str, Any]:
    del failure_report, prefix
    calls = [call for turn in turns for call in turn["tool_calls"]]
    names = [str(call["name"]) for call in calls]
    listed = {
        str(call["arguments"].get("resource", "")).lower().rstrip("s")
        for call in calls
        if call["name"] == "list_objects"
    }
    fetched = {
        str(call["arguments"].get("resource", "")).lower().rstrip("s")
        for call in calls
        if call["name"] == "get_object"
    }
    queried = {
        "contracts_and_local_state": "configmap" in listed or "configmap" in fetched,
        "both_consumers": "deployment" in listed or "deployment" in fetched,
        "service_routing": "service" in listed or "service" in fetched,
        "shared_credential": "secret" in listed or "secret" in fetched,
        "controller_ownership": "job" in listed or "job" in fetched,
        "external_registry": "list_external_deliveries" in names,
    }
    failures = set(evaluation.failures)
    scope_checks = {
        "api_consumer_matches_scope",
        "worker_consumer_matches_scope",
        "shared_credential_matches_scope",
        "bridge_matches_scope",
        "batch_matches_scope",
        "candidate_artifacts_match_commit",
        "transition_owner_closed_correctly",
        "publication_owner_closed_correctly",
        "boundary_effect_envelope_respected",
        "no_duplicate_transition_owner",
        "no_duplicate_publication_owner",
    }
    fact_checks = {
        "audit_records_observed_facts",
        "closure_event_records_observed_facts",
    }
    if evaluation.passed:
        primary_error = None
    elif not all(queried.values()):
        primary_error = "investigation_failure"
    elif (
        failures & scope_checks
        or not evaluation.components["preservation"]
        or not evaluation.components["protocol_safety"]
    ):
        primary_error = "scope_failure"
    elif failures & fact_checks:
        primary_error = "state_inference_failure"
    elif not evaluation.components["repair_completeness"]:
        primary_error = "execution_failure"
    else:
        primary_error = "verification_failure"
    mutations = set(KubernetesInteractionEnvironment.MUTATION_TOOLS)
    return {
        "primary_error": primary_error,
        "evidence_groups": queried,
        "query_tool_count": sum(name not in mutations for name in names),
        "mutation_tool_count": sum(name in mutations for name in names),
        "selected_mutations": [name for name in names if name in mutations],
        "semantic_recovery_direction": evaluation.diagnostics.get(
            "semantic_recovery_direction"
        ),
    }


def _build_environment(
    context: NativeRuntimeContext,
) -> KubernetesInteractionEnvironment:
    del context
    stack = KubernetesStack.from_repository()
    return KubernetesInteractionEnvironment(KubernetesApi(context=stack.context))


KUBERNETES_INTERACTION_FAMILY = NativeFamilyDefinition(
    family_id="k8s-constraint-interaction-recovery",
    domain="kubernetes",
    system_prompt=KUBERNETES_INTERACTION_SYSTEM_PROMPT,
    tool_definitions=KUBERNETES_MIGRATION_TOOL_DEFINITIONS,
    mutation_tools=frozenset(KubernetesInteractionEnvironment.MUTATION_TOOLS),
    build_environment=_build_environment,
    build_initial_message=kubernetes_interaction_initial_message,
    evaluate=lambda state, _prefix: evaluate_kubernetes_interaction_recovery(state),
    diagnose=diagnose_kubernetes_interaction_trajectory,
)
