from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from .integrations.deployment_target_api import DeploymentTargetAPI
from .integrations.forgejo_api import ForgejoAPI
from .integrations.forgejo_promotion_agent import ForgejoPromotionEnvironment
from .integrations.forgejo_promotion_instance import ForgejoPromotionInstanceSpec
from .integrations.forgejo_stack import ForgejoStack
from .model_runner import ToolDefinition
from .native_family import NativeFamilyDefinition, NativeRuntimeContext
from .native_scenario import NativeScenario

FORGEJO_PROMOTION_SYSTEM_PROMPT = """\
You are a release-operations agent working across a live Forgejo installation,
its native Actions runner, a deployment controller and a transparency receiver.
Dispatching an approved signed-artifact promotion returned a connection error.

Reconstruct the committed state from authoritative repository, Actions artifact,
deployment, attestation, release and issue records before writing. Complete only
missing effects, preserve the prior release, protected environment, approval and
unrelated work, and avoid duplicate workflow owners, artifacts, deployments,
attestations or metadata. Make objectively supported decisions yourself and stop
only after cross-system consistency is verified, or after {max_turns} turns.
"""


def _schema(
    properties: dict[str, dict[str, Any]], required: tuple[str, ...] = ()
) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": list(required),
        "additionalProperties": False,
    }


_INDEX = {"index": {"type": "integer", "minimum": 1}}
_RUN_ID = {"run_id": {"type": "integer", "minimum": 1}}


FORGEJO_PROMOTION_TOOLS = (
    ToolDefinition(
        "get_branch",
        "Read the authoritative repository branch and head commit.",
        _schema({"branch": {"type": "string"}}),
    ),
    ToolDefinition(
        "get_repository_content",
        "Read one approved manifest, artifact source or workflow file.",
        _schema(
            {"path": {"type": "string"}, "ref": {"type": "string"}},
            ("path",),
        ),
    ),
    ToolDefinition("list_issues", "List repository issues.", _schema({})),
    ToolDefinition(
        "list_issue_comments",
        "List comments for one issue.",
        _schema(_INDEX, ("index",)),
    ),
    ToolDefinition("list_releases", "List repository releases.", _schema({})),
    ToolDefinition(
        "list_action_runs", "List native Actions workflow owners.", _schema({})
    ),
    ToolDefinition(
        "list_action_run_jobs",
        "List jobs and step states for one Actions run.",
        _schema(_RUN_ID, ("run_id",)),
    ),
    ToolDefinition(
        "list_action_run_artifacts",
        "List native uploaded artifact records for one Actions run.",
        _schema(_RUN_ID, ("run_id",)),
    ),
    ToolDefinition(
        "get_deployment_state",
        "Read registered signed bundles, deployment requests and replicas.",
        _schema({}),
    ),
    ToolDefinition(
        "get_external_attestation",
        "Read an exact transparency receiver record by idempotency key.",
        _schema({"key": {"type": "string"}}, ("key",)),
    ),
    ToolDefinition(
        "dispatch_workflow",
        "Dispatch the repository's ordinary promotion workflow with explicit inputs.",
        _schema(
            {
                "workflow": {"type": "string"},
                "ref": {"type": "string"},
                "inputs": {
                    "type": "object",
                    "additionalProperties": {"type": "string"},
                },
            },
            ("workflow", "ref"),
        ),
    ),
    ToolDefinition(
        "start_action_runner",
        "Start the registered native Actions runner if it is paused.",
        _schema({}),
    ),
    ToolDefinition(
        "wait_for_action_run",
        "Wait for one existing Actions run to reach a terminal state.",
        _schema(
            {
                **_RUN_ID,
                "timeout_seconds": {"type": "integer", "minimum": 1, "maximum": 60},
            },
            ("run_id",),
        ),
    ),
    ToolDefinition(
        "create_release",
        "Create the target repository release after promotion evidence agrees.",
        _schema(
            {
                "tag": {"type": "string"},
                "target": {"type": "string"},
                "title": {"type": "string"},
                "body": {"type": "string"},
            },
            ("tag", "target", "title", "body"),
        ),
    ),
    ToolDefinition(
        "create_issue_comment",
        "Add one verification comment to an issue.",
        _schema({**_INDEX, "body": {"type": "string"}}, ("index", "body")),
    ),
    ToolDefinition(
        "edit_issue",
        "Set one inspected issue to open or closed.",
        _schema(
            {**_INDEX, "state": {"type": "string", "enum": ["open", "closed"]}},
            ("index", "state"),
        ),
    ),
)


@dataclass(frozen=True)
class ForgejoPromotionFamilyEvaluation:
    passed: bool
    components: dict[str, bool]
    checks: dict[str, bool]
    diagnostics: dict[str, Any]
    failures: tuple[str, ...]


def forgejo_promotion_initial_message(
    *,
    scenario: NativeScenario,
    prefix: dict[str, Any],
    failure_report: dict[str, Any],
    execution_control: bool = False,
) -> str:
    keys = (
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
    identifiers = {key: prefix[key] for key in keys}
    compact_trace = [
        {
            "system": event.get("system"),
            "tool": event.get("tool"),
            "arguments": event.get("arguments", {}),
            "status": event.get("status", "success"),
        }
        for event in prefix.get("trace", ())
    ]
    message = (
        "User request:\n"
        f"{scenario.raw['user_instruction']}\n\n"
        "Known identifiers from successful prior activity:\n"
        f"{json.dumps(identifiers, ensure_ascii=False, indent=2)}\n\n"
        "Successful prior tool activity:\n"
        f"{json.dumps(compact_trace, ensure_ascii=False, indent=2)}\n\n"
        "Latest attempted tool call and result:\n"
        f"{json.dumps(failure_report['latest_attempt'], ensure_ascii=False, indent=2)}"
        "\n\nContinue from the current authoritative cross-system state."
    )
    if execution_control:
        message += (
            "\n\nExecution-control condition: inspect the current Actions owner, native "
            "artifact, deployment and attestation first. Dispatch the original "
            "workflow only if no owner exists; start a waiting existing owner; "
            "resume a failed owner from the first missing durable stage using the "
            "workflow's documented resume input. Preserve every completed stage. "
            "Create the target release, one verification comment and close the "
            "rollout issue only after Actions, deployment and attestation agree."
        )
    return message


def _evaluate(
    final_state: dict[str, Any], prefix: dict[str, Any]
) -> ForgejoPromotionFamilyEvaluation:
    del prefix
    result = final_state["evaluation"]
    checks = dict(result["checks"])
    return ForgejoPromotionFamilyEvaluation(
        passed=bool(result["passed"]),
        components=dict(result["components"]),
        checks=checks,
        diagnostics={"action_run_count": len(result["final_evidence"]["action_runs"])},
        failures=tuple(name for name, passed in checks.items() if not passed),
    )


def diagnose_forgejo_promotion_trajectory(
    *,
    turns: list[dict[str, Any]],
    evaluation: ForgejoPromotionFamilyEvaluation,
    failure_report: dict[str, Any],
    prefix: dict[str, Any],
) -> dict[str, Any]:
    del failure_report, prefix
    calls = [call for turn in turns for call in turn.get("tool_calls", [])]
    names = [str(call.get("name")) for call in calls]
    evidence_groups = {
        "approval": "get_repository_content" in names,
        "actions": all(
            name in names
            for name in (
                "list_action_runs",
                "list_action_run_jobs",
                "list_action_run_artifacts",
            )
        ),
        "deployment": "get_deployment_state" in names,
        "attestation": "get_external_attestation" in names,
        "metadata": "list_releases" in names and "list_issues" in names,
    }
    if evaluation.passed:
        primary_error = None
    elif not all(evidence_groups.values()):
        primary_error = "investigation_failure"
    elif not evaluation.components.get("preservation", True):
        primary_error = "scope_failure"
    elif not evaluation.components.get(
        "goal_completion", True
    ) or not evaluation.components.get("repair_completeness", True):
        primary_error = "execution_failure"
    else:
        primary_error = "verification_failure"
    return {
        "primary_error": primary_error,
        "tool_names": names,
        "evidence_groups": evidence_groups,
    }


def _build_environment(context: NativeRuntimeContext) -> ForgejoPromotionEnvironment:
    instance = ForgejoPromotionInstanceSpec(
        **{key: str(value) for key, value in context.scenario.raw["fixture"].items()}
    )
    instance.validate()
    return ForgejoPromotionEnvironment(
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


FORGEJO_PROMOTION_FAMILY = NativeFamilyDefinition(
    family_id="forgejo-approved-artifact-promotion",
    domain="forgejo",
    system_prompt=FORGEJO_PROMOTION_SYSTEM_PROMPT,
    tool_definitions=FORGEJO_PROMOTION_TOOLS,
    mutation_tools=ForgejoPromotionEnvironment.MUTATION_TOOLS,
    build_environment=_build_environment,
    build_initial_message=forgejo_promotion_initial_message,
    evaluate=_evaluate,
    diagnose=diagnose_forgejo_promotion_trajectory,
)


__all__ = [
    "FORGEJO_PROMOTION_FAMILY",
    "FORGEJO_PROMOTION_SYSTEM_PROMPT",
    "FORGEJO_PROMOTION_TOOLS",
    "forgejo_promotion_initial_message",
]
