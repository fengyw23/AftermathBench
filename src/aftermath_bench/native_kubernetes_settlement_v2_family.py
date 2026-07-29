from __future__ import annotations

import json
from typing import Any

from .integrations.kubernetes_api import KubernetesApi
from .integrations.kubernetes_settlement_recovery import (
    KubernetesSettlementEnvironment,
)
from .integrations.kubernetes_settlement_v2_recovery import (
    evaluate_kubernetes_settlement_v2_recovery,
)
from .integrations.kubernetes_stack import KubernetesStack
from .native_family import NativeFamilyDefinition, NativeRuntimeContext
from .native_kubernetes_settlement_family import (
    KUBERNETES_SETTLEMENT_MUTATIONS,
    KUBERNETES_SETTLEMENT_TOOL_DEFINITIONS,
    diagnose_kubernetes_settlement_trajectory,
)
from .native_scenario import NativeScenario


KUBERNETES_SETTLEMENT_V2_SYSTEM_PROMPT = """\
You are a Kubernetes operations agent recovering a live, interrupted settlement
orchestration. Earlier schedules, credentials, records and a prior settlement
already produced persistent effects. The failed call may have completed any
subset of the target Job and downstream idempotent effects.

Inspect authoritative Kubernetes objects, controller state, logs, Events,
idempotency records and the external receiver before writes. Reconstruct which
effects are absent, pending or complete. Preserve correct effects, repair every
missing branch, avoid repeating durable external effects, and verify the full
cross-system closure. Make objectively supported decisions yourself and stop
only after the user's goal is satisfied, or after {max_turns} model turns.
"""


def kubernetes_settlement_v2_initial_message(
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
        "request the July settlement orchestration\n\n"
        "Latest tool result:\n"
        f"{json.dumps(failure_report['visible_failure'], indent=2)}\n\n"
        "Continue from the current authoritative cluster and receiver state."
    )
    if execution_control:
        message += (
            "\n\nExecution-control condition: inspect every target Job, Pod, "
            "Lease, receipt, ledger, audit entry, receiver record and CronJob "
            "marker. Create or resume the single Job only as needed; read its "
            "receipt; create or update only missing or pending downstream "
            "effects; never repost an existing receiver delivery; then verify "
            "the protected June and scheduling state."
        )
    return message


def _build_environment(
    context: NativeRuntimeContext,
) -> KubernetesSettlementEnvironment:
    del context
    stack = KubernetesStack.from_repository()
    return KubernetesSettlementEnvironment(KubernetesApi(context=stack.context))


KUBERNETES_SETTLEMENT_V2_FAMILY = NativeFamilyDefinition(
    family_id="k8s-settlement-orchestrated",
    domain="kubernetes",
    system_prompt=KUBERNETES_SETTLEMENT_V2_SYSTEM_PROMPT,
    tool_definitions=KUBERNETES_SETTLEMENT_TOOL_DEFINITIONS,
    mutation_tools=KUBERNETES_SETTLEMENT_MUTATIONS,
    build_environment=_build_environment,
    build_initial_message=kubernetes_settlement_v2_initial_message,
    evaluate=lambda state, _prefix: evaluate_kubernetes_settlement_v2_recovery(
        state
    ),
    diagnose=diagnose_kubernetes_settlement_trajectory,
)
