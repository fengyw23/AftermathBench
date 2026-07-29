from __future__ import annotations

from typing import Any

from .forgejo_recovery import (
    ForgejoReleaseEnvironment,
    relevant_external_deliveries,
)


BASELINE_NAMES = (
    "no_op",
    "blind_retry",
    "assume_committed",
    "repair_failed_record_only",
    "publish_release_only",
    "replay_any_failed_delivery",
    "compact_state_tree",
)


def _call(
    environment: ForgejoReleaseEnvironment,
    trace: list[dict[str, Any]],
    tool: str,
    **arguments: Any,
) -> dict[str, Any]:
    result = environment.invoke(tool, **arguments)
    trace.append({"tool": tool, "arguments": arguments, "result": result})
    return result


def _create_release(
    environment: ForgejoReleaseEnvironment,
    trace: list[dict[str, Any]],
) -> None:
    prefix = environment.prefix
    _call(
        environment,
        trace,
        "create_release",
        tag=prefix["release_tag"],
        target=prefix["base_branch"],
        title="July 2026 maintenance release",
        body="Includes the approved customer export timeout fix.",
    )


def run_fixed_forgejo_baseline(
    name: str,
    *,
    environment: ForgejoReleaseEnvironment,
) -> tuple[dict[str, Any], ...]:
    """Execute a fixed release-recovery policy on the native state."""

    if name not in BASELINE_NAMES:
        raise ValueError(f"unknown Forgejo baseline: {name}")
    prefix = environment.prefix
    trace: list[dict[str, Any]] = []
    if name == "no_op":
        return ()
    if name == "blind_retry":
        _call(
            environment,
            trace,
            "merge_pull_request",
            index=prefix["pull_request_index"],
        )
        return tuple(trace)
    if name in {"assume_committed", "publish_release_only"}:
        _create_release(environment, trace)
        return tuple(trace)
    if name == "repair_failed_record_only":
        pull = _call(
            environment,
            trace,
            "get_pull_request",
            index=prefix["pull_request_index"],
        ).get("result", {})
        if not pull.get("merged"):
            _call(
                environment,
                trace,
                "merge_pull_request",
                index=prefix["pull_request_index"],
            )
        return tuple(trace)
    if name == "replay_any_failed_delivery":
        history = _call(
            environment,
            trace,
            "get_webhook_history",
            hook_id=prefix["webhook_id"],
        ).get("result", [])
        failed = [item for item in history if item.get("status") == "failed"]
        if failed:
            _call(
                environment,
                trace,
                "replay_webhook",
                hook_id=prefix["webhook_id"],
                delivery_uuid=failed[0]["uuid"],
            )
        return tuple(trace)

    pull = _call(
        environment,
        trace,
        "get_pull_request",
        index=prefix["pull_request_index"],
    ).get("result", {})
    history = _call(
        environment,
        trace,
        "get_webhook_history",
        hook_id=prefix["webhook_id"],
    ).get("result", [])
    external = _call(
        environment,
        trace,
        "list_external_deliveries",
    ).get("result", [])
    releases = _call(
        environment,
        trace,
        "list_releases",
    ).get("result", [])
    relevant = relevant_external_deliveries(
        external, int(prefix["pull_request_index"])
    )
    if not pull.get("merged"):
        _call(
            environment,
            trace,
            "merge_pull_request",
            index=prefix["pull_request_index"],
        )
        _call(
            environment,
            trace,
            "wait_for_external_delivery",
            pull_index=prefix["pull_request_index"],
            timeout_seconds=30,
        )
    elif not relevant:
        failed = [item for item in history if item.get("status") == "failed"]
        if failed:
            _call(
                environment,
                trace,
                "replay_webhook",
                hook_id=prefix["webhook_id"],
                delivery_uuid=failed[0]["uuid"],
            )
            _call(
                environment,
                trace,
                "wait_for_external_delivery",
                pull_index=prefix["pull_request_index"],
                timeout_seconds=30,
            )
    if not any(
        item.get("tag_name") == prefix["release_tag"]
        for item in releases
    ):
        _create_release(environment, trace)
    return tuple(trace)
