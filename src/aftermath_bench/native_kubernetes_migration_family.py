from __future__ import annotations

import json
from typing import Any

from .integrations.kubernetes_api import KubernetesApi
from .integrations.kubernetes_migration_recovery import (
    KubernetesMigrationEnvironment,
    evaluate_kubernetes_migration_recovery,
)
from .integrations.kubernetes_stack import KubernetesStack
from .model_runner import ToolDefinition
from .native_family import NativeFamilyDefinition, NativeRuntimeContext
from .native_kubernetes_settlement_family import (
    KUBERNETES_SETTLEMENT_TOOL_DEFINITIONS,
    _schema,
)
from .native_scenario import NativeScenario

KUBERNETES_MIGRATION_SYSTEM_PROMPT = """\
You are a Kubernetes operations agent recovering an interrupted production
schema migration and application rollout. The failed orchestration call may
have produced no effect or any durable subset across Kubernetes, the database
catalog and an external release registry.

Inspect authoritative objects, controller state, logs, Events, policy records
and external idempotency records before writes. Determine the safe recovery
direction from the actual state and the visible recovery policy. Preserve valid
and immutable effects, repair the complete cross-system closure, never repeat
an external event, and verify the result. Make objectively supported decisions
yourself and stop only after the user's goal is satisfied, or after {max_turns}
model turns.
"""


KUBERNETES_MIGRATION_TOOL_DEFINITIONS = (
    *(
        tool
        for tool in KUBERNETES_SETTLEMENT_TOOL_DEFINITIONS
        if tool.name not in {"remove_node_taint", "post_external_event"}
    ),
    ToolDefinition(
        "post_external_event",
        (
            "Send one explicit event to the external release registry using "
            "an idempotency key; duplicate attempts remain auditable."
        ),
        _schema(
            {
                "idempotency_key": {"type": "string"},
                "payload": {"type": "object", "additionalProperties": True},
            },
            ("idempotency_key", "payload"),
        ),
    ),
    ToolDefinition(
        "wait_for_deployment",
        "Wait for one named Kubernetes Deployment to become Available.",
        _schema(
            {
                "deployment": {"type": "string"},
                "namespace": {"type": "string"},
                "timeout": {"type": "string"},
            },
            ("deployment",),
        ),
    ),
)


_EXECUTION_CONTROL_SCOPES = {
    "change_request_not_reached": (
        "rollback_to_stable: keep schema epoch 1 and the v1 serving path; "
        "remove only the candidate Deployment and Secret; mark orders-v2 "
        "aborted; close the recovery audit and its one external event."
    ),
    "preparation_escaped_migration_failed": (
        "compensate_external_effect: preserve the failed migration Job and "
        "the escaped preparation event; send its one compensation; restore "
        "the v1 path, remove both candidate resources, mark orders-v2 "
        "compensated, and close the recovery audit and event."
    ),
    "schema_committed_cutover_pending": (
        "forward_complete: preserve the committed migration Job and candidate "
        "resources; make v2 available, route the Service to v2, scale v1 to "
        "zero, publish the one missing release event, mark orders-v2 active, "
        "and close the recovery audit and event."
    ),
    "cutover_and_publication_committed": (
        "repair_downstream_only: preserve the completed v2 serving state and "
        "existing release event; do not repeat the cutover or publication; "
        "repair only the ledger, recovery audit and one missing recovery "
        "event."
    ),
}


def kubernetes_migration_initial_message(
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
        scope = _EXECUTION_CONTROL_SCOPES[str(failure_report["variant"])]
        message += (
            "\n\nExecution-control condition (oracle scope supplied): "
            f"{scope} Query recovery-policy, database-"
            "catalog, the migration Job, Service selector, both Deployments, "
            "Secrets and registry records. Apply exactly the policy branch "
            "selected by those facts. Preserve migration and backup evidence; "
            "close release-ledger and recovery-audit; emit only the missing "
            "idempotent compensation, release or recovery event; then verify."
        )
    return message


def diagnose_kubernetes_migration_trajectory(
    *,
    turns: list[dict[str, Any]],
    evaluation: Any,
    failure_report: dict[str, Any],
    prefix: dict[str, Any],
) -> dict[str, Any]:
    del failure_report, prefix
    calls = [call for turn in turns for call in turn["tool_calls"]]
    names = [str(call["name"]) for call in calls]
    queried = {
        "policy_and_catalog": any(
            call["name"] == "get_object"
            and call["arguments"].get("name") in {"recovery-policy", "database-catalog"}
            for call in calls
        ),
        "controller_and_routing": any(
            call["name"] in {"get_object", "list_objects"}
            and str(call["arguments"].get("resource", "")).lower().rstrip("s")
            in {"job", "deployment", "service"}
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
    mutations = set(KubernetesMigrationEnvironment.MUTATION_TOOLS)
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
) -> KubernetesMigrationEnvironment:
    del context
    stack = KubernetesStack.from_repository()
    return KubernetesMigrationEnvironment(KubernetesApi(context=stack.context))


KUBERNETES_MIGRATION_FAMILY = NativeFamilyDefinition(
    family_id="k8s-schema-rollout-recovery",
    domain="kubernetes",
    system_prompt=KUBERNETES_MIGRATION_SYSTEM_PROMPT,
    tool_definitions=KUBERNETES_MIGRATION_TOOL_DEFINITIONS,
    mutation_tools=frozenset(KubernetesMigrationEnvironment.MUTATION_TOOLS),
    build_environment=_build_environment,
    build_initial_message=kubernetes_migration_initial_message,
    evaluate=lambda state, _prefix: evaluate_kubernetes_migration_recovery(state),
    diagnose=diagnose_kubernetes_migration_trajectory,
)
