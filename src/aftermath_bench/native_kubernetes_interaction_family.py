from __future__ import annotations

import json
from typing import Any

from .integrations.kubernetes_api import KubernetesApi
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


def _control_scope(variant: str) -> str:
    expected = _expected_terminal(INTERACTION_VARIANT_FACTS[variant])
    transition = (
        "one completed transition Job"
        if expected["transition_completed"]
        else "one suspended transition owner"
        if expected["transition_required"]
        else "no transition Job"
    )
    publication = (
        "one completed publication Job and one accepted release event"
        if expected["publication_required"]
        else "no publication Job or release event"
    )
    candidate = "retain" if expected["candidate_present"] else "remove"
    return (
        f"Keep the immutable catalog at epoch {expected['epoch']}; leave API "
        f"{expected['api_version']}, worker {expected['worker_version']}, shared "
        f"credential generation {expected['credential_generation']}, bridge "
        f"{expected['bridge_lease']} and batch {expected['batch_state']}. "
        f"Ensure {transition}; ensure {publication}; {candidate} the v2 candidate "
        f"Deployments and next credential. Preserve every pre-existing owner, "
        "migration/backup evidence and accepted external event, then close the "
        "visible ledger, audit and recovery event exactly as their contracts specify."
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
        "execute the approved orders platform migration and coordinated rollout\n\n"
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
    elif failures & scope_checks or not evaluation.components["preservation"] or not evaluation.components["protocol_safety"]:
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
