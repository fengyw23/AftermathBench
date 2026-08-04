from __future__ import annotations

import time
from typing import Any

from .forgejo_promotion_agent import ForgejoPromotionEnvironment

FORGEJO_RECONCILIATION_BASELINES = (
    "no_op",
    "repair_actions_only",
    "repair_registry_only",
    "repair_production_only",
    "repair_attestation_only",
    "repair_metadata_only",
    "replay_everything",
)


def _call(
    environment: ForgejoPromotionEnvironment,
    trace: list[dict[str, Any]],
    tool: str,
    **arguments: Any,
) -> dict[str, Any]:
    result = environment.invoke(tool, **arguments)
    trace.append({"tool": tool, "arguments": arguments, "result": result})
    return result


def _runs(result: dict[str, Any]) -> list[dict[str, Any]]:
    value = result.get("result")
    return value if isinstance(value, list) else []


def _dispatch_and_wait(
    environment: ForgejoPromotionEnvironment,
    trace: list[dict[str, Any]],
    inputs: dict[str, str],
) -> None:
    before = {
        int(row["id"])
        for row in _runs(_call(environment, trace, "list_action_runs"))
    }
    _call(environment, trace, "start_action_runner")
    dispatched = _call(
        environment,
        trace,
        "dispatch_workflow",
        workflow=environment.instance.workflow_path,
        ref="main",
        inputs=inputs,
    )
    if not dispatched.get("ok"):
        return
    created: list[dict[str, Any]] = []
    for attempt in range(40):
        created = [
            row
            for row in _runs(_call(environment, trace, "list_action_runs"))
            if int(row["id"]) not in before
        ]
        if created:
            break
        if attempt + 1 < 40:
            time.sleep(0.25)
    if len(created) == 1:
        _call(
            environment,
            trace,
            "wait_for_action_run",
            run_id=int(created[0]["id"]),
            timeout_seconds=60,
        )


def _finalize_metadata(
    environment: ForgejoPromotionEnvironment,
    trace: list[dict[str, Any]],
) -> None:
    spec = environment.instance
    _call(
        environment,
        trace,
        "create_release",
        tag=spec.release_tag,
        target="main",
        title=f"{spec.repository} {spec.version}",
        body=(
            f"Production digest {spec.artifact_digest}; transparency "
            f"attestation {spec.attestation_key}."
        ),
    )
    _call(
        environment,
        trace,
        "edit_issue",
        index=int(environment.prefix["rollout_issue_index"]),
        state="closed",
    )


def run_fixed_forgejo_reconciliation_baseline(
    name: str,
    *,
    environment: ForgejoPromotionEnvironment,
) -> tuple[dict[str, Any], ...]:
    """Execute one boundary-insensitive policy through ordinary public tools."""

    if name not in FORGEJO_RECONCILIATION_BASELINES:
        raise ValueError(f"unknown Forgejo reconciliation baseline: {name}")
    trace: list[dict[str, Any]] = []
    if name == "repair_actions_only":
        _dispatch_and_wait(
            environment, trace, {"resume_stage": "start", "stop_after": "artifact"}
        )
    elif name == "repair_registry_only":
        _dispatch_and_wait(
            environment,
            trace,
            {"resume_stage": "after_artifact", "stop_after": "bundle"},
        )
    elif name == "repair_production_only":
        _dispatch_and_wait(
            environment,
            trace,
            {"resume_stage": "after_bundle", "stop_after": "deployment"},
        )
    elif name == "repair_attestation_only":
        _dispatch_and_wait(
            environment,
            trace,
            {"resume_stage": "after_deployment", "stop_after": "none"},
        )
    elif name == "repair_metadata_only":
        _finalize_metadata(environment, trace)
    elif name == "replay_everything":
        _dispatch_and_wait(
            environment, trace, {"resume_stage": "start", "stop_after": "none"}
        )
        _finalize_metadata(environment, trace)
    return tuple(trace)


__all__ = [
    "FORGEJO_RECONCILIATION_BASELINES",
    "run_fixed_forgejo_reconciliation_baseline",
]
