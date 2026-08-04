from __future__ import annotations

from typing import Any

from .forgejo_promotion_agent import ForgejoPromotionEnvironment

FORGEJO_PROMOTION_BASELINES = (
    "no_op",
    "blind_dispatch_start",
    "start_runner_then_finalize",
    "resume_after_bundle",
    "resume_after_deployment",
    "finalize_metadata_only",
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


def _finalize(
    environment: ForgejoPromotionEnvironment,
    trace: list[dict[str, Any]],
) -> None:
    spec = environment.instance
    prefix = environment.prefix
    marker = f"{spec.version} {spec.artifact_digest} {spec.attestation_key}"
    _call(
        environment,
        trace,
        "create_release",
        tag=spec.release_tag,
        target="main",
        title=f"Clinical alert router {spec.version}",
        body=f"Production digest {spec.artifact_digest}; attestation {spec.attestation_key}.",
    )
    _call(
        environment,
        trace,
        "create_issue_comment",
        index=int(prefix["rollout_issue_index"]),
        body=f"Verified promotion: {marker}.",
    )
    _call(
        environment,
        trace,
        "edit_issue",
        index=int(prefix["rollout_issue_index"]),
        state="closed",
    )


def _dispatch_wait_finalize(
    environment: ForgejoPromotionEnvironment,
    trace: list[dict[str, Any]],
    *,
    inputs: dict[str, str],
) -> None:
    dispatched = _call(
        environment,
        trace,
        "dispatch_workflow",
        workflow=environment.instance.workflow_path,
        ref="main",
        inputs=inputs,
    )
    run = dispatched.get("result")
    if isinstance(run, dict) and run.get("id") is not None:
        _call(
            environment,
            trace,
            "wait_for_action_run",
            run_id=int(run["id"]),
            timeout_seconds=60,
        )
    _finalize(environment, trace)


def run_fixed_forgejo_promotion_baseline(
    name: str,
    *,
    environment: ForgejoPromotionEnvironment,
) -> tuple[dict[str, Any], ...]:
    """Run one intentionally state-insensitive promotion policy."""

    if name not in FORGEJO_PROMOTION_BASELINES:
        raise ValueError(f"unknown Forgejo promotion baseline: {name}")
    trace: list[dict[str, Any]] = []
    if name == "no_op":
        return ()
    if name == "blind_dispatch_start":
        _dispatch_wait_finalize(environment, trace, inputs={})
    elif name == "start_runner_then_finalize":
        runs = _call(environment, trace, "list_action_runs").get("result", [])
        _call(environment, trace, "start_action_runner")
        if runs:
            _call(
                environment,
                trace,
                "wait_for_action_run",
                run_id=int(runs[0]["id"]),
                timeout_seconds=60,
            )
        _finalize(environment, trace)
    elif name == "resume_after_bundle":
        _dispatch_wait_finalize(
            environment, trace, inputs={"resume_stage": "after_bundle"}
        )
    elif name == "resume_after_deployment":
        _dispatch_wait_finalize(
            environment, trace, inputs={"resume_stage": "after_deployment"}
        )
    elif name == "finalize_metadata_only":
        _finalize(environment, trace)
    return tuple(trace)


__all__ = [
    "FORGEJO_PROMOTION_BASELINES",
    "run_fixed_forgejo_promotion_baseline",
]
