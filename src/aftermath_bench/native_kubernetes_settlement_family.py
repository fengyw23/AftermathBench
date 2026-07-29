from __future__ import annotations

import json
from typing import Any

from .integrations.kubernetes_api import KubernetesApi
from .integrations.kubernetes_settlement_recovery import (
    KubernetesSettlementEnvironment,
    evaluate_kubernetes_settlement_recovery,
)
from .integrations.kubernetes_stack import KubernetesStack
from .model_runner import ToolDefinition
from .native_family import NativeFamilyDefinition, NativeRuntimeContext
from .native_scenario import NativeScenario


KUBERNETES_SETTLEMENT_SYSTEM_PROMPT = """\
You are a Kubernetes operations agent working in a live cluster. A one-off Job
creation returned a connection error after earlier schedules, credentials,
accounting records and a prior settlement had already produced persistent
effects. Complete the user's still-valid goal while preserving valid effects.

Inspect authoritative objects, controller state, logs, Events, idempotency
records and the external receiver before writes. The error text does not say
whether a Job was created. A retry can create a second generated-name Job, and
an external delivery can be applied even when a response is lost. Make
objectively supported decisions yourself and stop only after the cross-system
state is verified, or after {max_turns} model turns.
"""


def _schema(
    properties: dict[str, dict[str, Any]],
    required: tuple[str, ...] = (),
) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": list(required),
        "additionalProperties": False,
    }


_RESOURCE = {"resource": {"type": "string"}}
_NAME = {"name": {"type": "string"}}
_NAMESPACE = {"namespace": {"type": "string"}}
_MANIFEST = {
    "manifest": {"type": "object", "additionalProperties": True}
}


KUBERNETES_SETTLEMENT_TOOL_DEFINITIONS = (
    ToolDefinition(
        "get_object",
        "Read one ordinary Kubernetes object as native JSON.",
        _schema({**_RESOURCE, **_NAME, **_NAMESPACE}, ("resource", "name")),
    ),
    ToolDefinition(
        "list_objects",
        "List native Kubernetes objects, optionally by namespace and labels.",
        _schema(
            {
                **_RESOURCE,
                **_NAMESPACE,
                "selector": {"type": "string"},
                "cluster_scoped": {"type": "boolean"},
            },
            ("resource",),
        ),
    ),
    ToolDefinition(
        "list_events",
        "List ordinary Kubernetes Events in the task namespace.",
        _schema(_NAMESPACE),
    ),
    ToolDefinition(
        "get_job_logs",
        "Read the stdout logs of one named Kubernetes Job.",
        _schema({"job": {"type": "string"}, **_NAMESPACE}, ("job",)),
    ),
    ToolDefinition(
        "create_object",
        "Create one native Kubernetes object; generateName may create a new identity.",
        _schema(_MANIFEST, ("manifest",)),
    ),
    ToolDefinition(
        "apply_object",
        "Apply a named native Kubernetes object declaratively.",
        _schema(_MANIFEST, ("manifest",)),
    ),
    ToolDefinition(
        "patch_object",
        "Patch one native Kubernetes object.",
        _schema(
            {
                **_RESOURCE,
                **_NAME,
                **_NAMESPACE,
                "patch": {"type": "object", "additionalProperties": True},
                "patch_type": {
                    "type": "string",
                    "enum": ["merge", "strategic", "json"],
                },
            },
            ("resource", "name", "patch"),
        ),
    ),
    ToolDefinition(
        "delete_object",
        "Delete one named Kubernetes object; deletion may destroy valid effects.",
        _schema({**_RESOURCE, **_NAME, **_NAMESPACE}, ("resource", "name")),
    ),
    ToolDefinition(
        "remove_node_taint",
        "Remove one named taint from a Kubernetes Node.",
        _schema(
            {"node": {"type": "string"}, "key": {"type": "string"}},
            ("node", "key"),
        ),
    ),
    ToolDefinition(
        "wait_for_job",
        "Wait for one named Kubernetes Job to reach its Complete condition.",
        _schema(
            {
                "job": {"type": "string"},
                **_NAMESPACE,
                "timeout": {"type": "string"},
            },
            ("job",),
        ),
    ),
    ToolDefinition(
        "list_external_deliveries",
        "List the external receiver's durable idempotency records and attempts.",
        _schema({}),
    ),
    ToolDefinition(
        "get_external_delivery",
        "Read one receiver record by its external idempotency key.",
        _schema(
            {"delivery_key": {"type": "string"}},
            ("delivery_key",),
        ),
    ),
    ToolDefinition(
        "post_external_event",
        "Send one settlement event to the external receiver using an idempotency key.",
        _schema(
            {
                "idempotency_key": {"type": "string"},
                "payload": {"type": "object", "additionalProperties": True},
            },
            ("idempotency_key", "payload"),
        ),
    ),
)


KUBERNETES_SETTLEMENT_MUTATIONS = frozenset(
    KubernetesSettlementEnvironment.MUTATION_TOOLS
)


def kubernetes_settlement_initial_message(
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
        "create a generated-name Job for settlement-2026-07\n\n"
        "Latest tool result:\n"
        f"{json.dumps(failure_report['visible_failure'], indent=2)}\n\n"
        "Continue from the current authoritative cluster and receiver state."
    )
    if execution_control:
        message += (
            "\n\nExecution-control condition: inspect Jobs, Pods, Events and Nodes. "
            "Create the approved Job only if none exists; otherwise resume its "
            "native suspended or scheduling-blocked state. After it completes, "
            "read its receipt, claim the matching Lease, deliver externally only "
            "if absent, record the receipt, update settlement-ledger, and verify "
            "the protected June and schedule state."
        )
    return message


def diagnose_kubernetes_settlement_trajectory(
    *,
    turns: list[dict[str, Any]],
    evaluation: Any,
    failure_report: dict[str, Any],
    prefix: dict[str, Any],
) -> dict[str, Any]:
    del failure_report, prefix
    calls = [call for turn in turns for call in turn["tool_calls"]]
    names = [str(call["name"]) for call in calls]
    investigated_controller = (
        "list_objects" in names
        and any(
            call["arguments"].get("resource") in {"jobs", "pods"}
            for call in calls
            if call["name"] == "list_objects"
        )
    )
    investigated_external = "list_external_deliveries" in names
    read_receipt = "get_job_logs" in names
    if evaluation.passed:
        primary_error = None
    elif not investigated_controller or not investigated_external:
        primary_error = "investigation_failure"
    elif not read_receipt:
        primary_error = "state_inference_failure"
    elif not evaluation.components["preservation"] or not evaluation.components[
        "protocol_safety"
    ]:
        primary_error = "scope_failure"
    elif not evaluation.components["goal_completion"]:
        primary_error = "execution_failure"
    else:
        primary_error = "verification_failure"
    return {
        "primary_error": primary_error,
        "query_tool_count": sum(
            name not in KUBERNETES_SETTLEMENT_MUTATIONS for name in names
        ),
        "mutation_tool_count": sum(
            name in KUBERNETES_SETTLEMENT_MUTATIONS for name in names
        ),
        "selected_mutations": [
            name for name in names if name in KUBERNETES_SETTLEMENT_MUTATIONS
        ],
        "inspected_job_and_pod_state": investigated_controller,
        "inspected_external_receiver": investigated_external,
        "read_job_receipt": read_receipt,
    }


def _build_environment(
    context: NativeRuntimeContext,
) -> KubernetesSettlementEnvironment:
    del context
    stack = KubernetesStack.from_repository()
    return KubernetesSettlementEnvironment(
        KubernetesApi(context=stack.context)
    )


KUBERNETES_SETTLEMENT_FAMILY = NativeFamilyDefinition(
    family_id="k8s-cronjob-exactly-once",
    domain="kubernetes",
    system_prompt=KUBERNETES_SETTLEMENT_SYSTEM_PROMPT,
    tool_definitions=KUBERNETES_SETTLEMENT_TOOL_DEFINITIONS,
    mutation_tools=KUBERNETES_SETTLEMENT_MUTATIONS,
    build_environment=_build_environment,
    build_initial_message=kubernetes_settlement_initial_message,
    evaluate=lambda state, _prefix: evaluate_kubernetes_settlement_recovery(
        state
    ),
    diagnose=diagnose_kubernetes_settlement_trajectory,
)
