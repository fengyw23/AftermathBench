from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from .integrations.deployment_target_api import DeploymentTargetAPI
from .integrations.forgejo_api import ForgejoAPI
from .integrations.forgejo_promotion_instance import ForgejoPromotionInstanceSpec
from .integrations.forgejo_reconciliation_agent import (
    ForgejoReconciliationEnvironment,
)
from .integrations.forgejo_stack import ForgejoStack
from .native_family import NativeFamilyDefinition, NativeRuntimeContext
from .native_forgejo_promotion_family import FORGEJO_PROMOTION_TOOLS
from .native_scenario import NativeScenario

FORGEJO_RECONCILIATION_SYSTEM_PROMPT = """\
You are a release-operations agent working across a live Forgejo installation,
its native Actions runner, deployment services and a transparency receiver. A
promotion operation returned a connection error.

Inspect the repository source, downloaded Actions artifact contents, artifact
registry, production replicas, external attestation, releases and issues before
writing. These effects can be independently present or missing. Repair exactly
the missing effects, preserve valid effects and protected records, and avoid
duplicate workflow artifacts, registry attempts, deployments, attestations or
metadata. Stop only after cross-system consistency is verified, or after
{max_turns} turns.
"""


@dataclass(frozen=True)
class ForgejoReconciliationEvaluation:
    passed: bool
    components: dict[str, bool]
    checks: dict[str, bool]
    diagnostics: dict[str, Any]
    failures: tuple[str, ...]


def reconciliation_initial_message(
    *,
    scenario: NativeScenario,
    prefix: dict[str, Any],
    failure_report: dict[str, Any],
    execution_control: bool = False,
) -> str:
    identifiers = {
        key: prefix[key]
        for key in (
            "owner",
            "repository",
            "rollout_issue_index",
            "approval_issue_index",
            "unrelated_issue_index",
            "workflow_path",
            "release_tag",
            "protected_release_tag",
            "repository_head",
        )
    }
    compact_trace = [
        {
            "system": event.get("system"),
            "tool": event.get("tool"),
            "arguments": event.get("arguments", {}),
            "status": event.get("status", "success"),
        }
        for event in prefix.get("trace", ())
    ]
    surface = failure_report.get("surface_result")
    if not isinstance(surface, dict):
        raise TypeError("reconciliation boundary has no visible failure result")
    message = (
        "User request:\n"
        f"{scenario.raw['user_instruction']}\n\n"
        "Known identifiers from successful prior activity:\n"
        f"{json.dumps(identifiers, ensure_ascii=False, indent=2)}\n\n"
        "Successful prior tool activity:\n"
        f"{json.dumps(compact_trace, ensure_ascii=False, indent=2)}\n\n"
        "Latest attempted tool call and result:\n"
        f"{json.dumps({'tool': 'dispatch_workflow', 'result': surface}, ensure_ascii=False, indent=2)}"
        "\n\nContinue from the current authoritative cross-system state."
    )
    if execution_control:
        message += (
            "\n\nExecution-control condition: query and compare every required "
            "cross-system obligation. If only the Actions bundle is missing, "
            "dispatch from start and stop after artifact upload; if only registry "
            "state is missing, resume after artifact and stop after bundle; if "
            "only production is missing, resume after bundle and stop after "
            "deployment; if only attestation is missing, resume after deployment. "
            "If only metadata is missing, create the semantically bound release "
            "and close the rollout issue. Preserve all already valid effects."
        )
    return message


def _evaluate(
    final_state: dict[str, Any], prefix: dict[str, Any]
) -> ForgejoReconciliationEvaluation:
    del prefix
    result = final_state["evaluation"]
    checks = dict(result["checks"])
    return ForgejoReconciliationEvaluation(
        passed=bool(result["passed"]),
        components=dict(result["components"]),
        checks=checks,
        diagnostics={"obligation_projection": result["obligation_projection"]},
        failures=tuple(result["failures"]),
    )


def diagnose_reconciliation_trajectory(
    *,
    turns: list[dict[str, Any]],
    evaluation: ForgejoReconciliationEvaluation,
    failure_report: dict[str, Any],
    prefix: dict[str, Any],
) -> dict[str, Any]:
    del failure_report, prefix
    names = [
        str(call.get("name"))
        for turn in turns
        for call in turn.get("tool_calls", [])
    ]
    evidence = {
        "approval_source": "get_repository_content" in names,
        "actions_artifact": "get_action_artifact_manifest" in names,
        "artifact_and_production": "get_deployment_state" in names,
        "external_attestation": "get_external_attestation" in names,
        "release_metadata": "list_releases" in names and "list_issues" in names,
    }
    if evaluation.passed:
        primary_error = None
    elif not all(evidence.values()):
        primary_error = "investigation_failure"
    elif not evaluation.components.get("preservation", True):
        primary_error = "scope_failure"
    elif not evaluation.components.get("goal_completion", True):
        primary_error = "execution_failure"
    else:
        primary_error = "verification_failure"
    return {
        "primary_error": primary_error,
        "tool_names": names,
        "evidence_groups": evidence,
    }


def _build_environment(
    context: NativeRuntimeContext,
) -> ForgejoReconciliationEnvironment:
    instance = ForgejoPromotionInstanceSpec(
        **{key: str(value) for key, value in context.scenario.raw["fixture"].items()}
    )
    instance.validate()
    return ForgejoReconciliationEnvironment(
        forgejo=ForgejoAPI(
            base_url=str(context.credentials["base_url"]),
            token=str(context.credentials["token"]),
        ),
        deployment=DeploymentTargetAPI("http://127.0.0.1:9095"),
        stack=ForgejoStack(
            compose_file=context.repository_root
            / "runtimes"
            / "forgejo"
            / "compose.yaml",
            container_cli=context.container_cli,
        ),
        instance=instance,
        prefix=context.prefix,
        variant=str(context.failure_report["variant"]),
    )


FORGEJO_RECONCILIATION_FAMILY = NativeFamilyDefinition(
    family_id="forgejo-cross-system-reconciliation",
    domain="forgejo",
    system_prompt=FORGEJO_RECONCILIATION_SYSTEM_PROMPT,
    tool_definitions=FORGEJO_PROMOTION_TOOLS,
    mutation_tools=ForgejoReconciliationEnvironment.MUTATION_TOOLS,
    build_environment=_build_environment,
    build_initial_message=reconciliation_initial_message,
    evaluate=_evaluate,
    diagnose=diagnose_reconciliation_trajectory,
)


__all__ = [
    "FORGEJO_RECONCILIATION_FAMILY",
    "FORGEJO_RECONCILIATION_SYSTEM_PROMPT",
    "reconciliation_initial_message",
]
