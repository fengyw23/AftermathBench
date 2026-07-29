from __future__ import annotations

import json
from typing import Any

from .integrations.kubernetes_api import KubernetesApi
from .integrations.kubernetes_constraint_recovery import (
    KubernetesConstraintEnvironment,
    evaluate_kubernetes_constraint_recovery,
)
from .integrations.kubernetes_stack import KubernetesStack
from .native_family import NativeFamilyDefinition, NativeRuntimeContext
from .native_kubernetes_migration_family import (
    KUBERNETES_MIGRATION_TOOL_DEFINITIONS,
)
from .native_scenario import NativeScenario

KUBERNETES_CONSTRAINT_SYSTEM_PROMPT = """\
You are a Kubernetes operations agent recovering an interrupted production
change. The failed orchestration call may have produced a durable subset of
effects across Kubernetes, a database catalog and an external registry.

Inspect authoritative objects, controller state, logs, Events, contract
records and external idempotency records before writes. Reconstruct the actual
state, compose all visible constraints, preserve valid effects, close every
remaining cross-system obligation, and verify the result. Never repeat an
external event. Make objectively supported decisions yourself and stop only
after the user's goal is satisfied, or after {max_turns} model turns.
"""


_EXECUTION_CONTROL_SCOPES = {
    "failed_migration_without_preparation": (
        "Keep catalog epoch 1 and v1 service capacity. Preserve the failed "
        "migration Job and backup, remove the unused v2 Deployment and Secret, "
        "and close the change, ledger, audit and one recovery event."
    ),
    "failed_migration_with_preparation": (
        "Keep catalog epoch 1 and v1 service capacity. Preserve the failed "
        "migration Job and preparation record, emit its one compensation, "
        "remove the unused v2 Deployment and Secret, and close all records."
    ),
    "committed_cutover_without_publication": (
        "Keep catalog epoch 2, v2 service and candidate resources, with v1 "
        "capacity at zero. Emit the missing release publication once and close "
        "the change, ledger, audit and recovery event."
    ),
    "committed_cutover_with_publication": (
        "Keep catalog epoch 2, v2 service, candidate resources and the existing "
        "release publication without repeating it. Close only the remaining "
        "change, ledger, audit and recovery event records."
    ),
}


def kubernetes_constraint_initial_message(
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
        "execute the approved orders-v2 migration-and-rollout orchestration\n\n"
        "Latest tool result:\n"
        f"{json.dumps(failure_report['visible_failure'], indent=2)}\n\n"
        "Continue from the current authoritative cluster and registry state."
    )
    if execution_control:
        message += (
            "\n\nExecution-control condition (target state supplied): "
            + _EXECUTION_CONTROL_SCOPES[str(failure_report["variant"])]
            + " Query the visible records for exact field and payload schemas, "
            "execute that target state, and verify it."
        )
    return message


def diagnose_kubernetes_constraint_trajectory(
    *,
    turns: list[dict[str, Any]],
    evaluation: Any,
    failure_report: dict[str, Any],
    prefix: dict[str, Any],
) -> dict[str, Any]:
    del failure_report, prefix
    calls = [call for turn in turns for call in turn["tool_calls"]]
    names = [str(call["name"]) for call in calls]
    contract_names = {
        "recovery-policy",
        "schema-contract",
        "serving-contract",
        "registry-contract",
        "audit-contract",
    }
    queried = {
        "constraints": any(
            call["name"] == "list_objects"
            and str(call["arguments"].get("resource", "")).lower().rstrip("s")
            == "configmap"
            or call["name"] == "get_object"
            and call["arguments"].get("name") in contract_names
            for call in calls
        ),
        "catalog_and_jobs": any(
            call["name"] in {"get_object", "list_objects"}
            and (
                call["arguments"].get("name") == "database-catalog"
                or str(call["arguments"].get("resource", "")).lower().rstrip("s")
                == "job"
            )
            for call in calls
        ),
        "serving": any(
            call["name"] in {"get_object", "list_objects"}
            and str(call["arguments"].get("resource", "")).lower().rstrip("s")
            in {"deployment", "service"}
            for call in calls
        ),
        "external_registry": "list_external_deliveries" in names,
    }
    if evaluation.passed:
        primary_error = None
    elif not all(queried.values()):
        primary_error = "investigation_failure"
    elif (
        not evaluation.components["preservation"]
        or not evaluation.components["protocol_safety"]
    ):
        primary_error = "scope_failure"
    elif not evaluation.components["goal_completion"]:
        primary_error = "state_inference_failure"
    elif not evaluation.components["repair_completeness"]:
        primary_error = "execution_failure"
    else:
        primary_error = "verification_failure"
    mutations = set(KubernetesConstraintEnvironment.MUTATION_TOOLS)
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
) -> KubernetesConstraintEnvironment:
    del context
    stack = KubernetesStack.from_repository()
    return KubernetesConstraintEnvironment(KubernetesApi(context=stack.context))


KUBERNETES_CONSTRAINT_FAMILY = NativeFamilyDefinition(
    family_id="k8s-constraint-scope-recovery",
    domain="kubernetes",
    system_prompt=KUBERNETES_CONSTRAINT_SYSTEM_PROMPT,
    tool_definitions=KUBERNETES_MIGRATION_TOOL_DEFINITIONS,
    mutation_tools=frozenset(KubernetesConstraintEnvironment.MUTATION_TOOLS),
    build_environment=_build_environment,
    build_initial_message=kubernetes_constraint_initial_message,
    evaluate=lambda state, _prefix: evaluate_kubernetes_constraint_recovery(state),
    diagnose=diagnose_kubernetes_constraint_trajectory,
)
