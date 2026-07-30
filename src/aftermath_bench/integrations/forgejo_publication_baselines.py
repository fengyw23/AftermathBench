from __future__ import annotations

from typing import Any

from .forgejo_publication_recovery import ForgejoPublicationEnvironment


PUBLICATION_BASELINE_NAMES = (
    "no_op",
    "blind_publish",
    "assume_release_exists",
    "repair_assets_only",
    "replay_all_failed",
    "compact_release_tree",
)


def _call(
    environment: ForgejoPublicationEnvironment,
    trace: list[dict[str, Any]],
    tool: str,
    **arguments: Any,
) -> dict[str, Any]:
    result = environment.invoke(tool, **arguments)
    trace.append({"tool": tool, "arguments": arguments, "result": result})
    return result


def _publish(
    environment: ForgejoPublicationEnvironment,
    trace: list[dict[str, Any]],
) -> dict[str, Any]:
    prefix = environment.prefix
    return _call(
        environment,
        trace,
        "create_release",
        tag=prefix["release_tag"],
        target=prefix["base_branch"],
        title=prefix["release_title"],
        body=prefix["release_body"],
    )


def _release(
    environment: ForgejoPublicationEnvironment,
    trace: list[dict[str, Any]],
) -> dict[str, Any] | None:
    prefix = environment.prefix
    result = _call(environment, trace, "list_releases").get("result", [])
    return next(
        (
            item
            for item in result
            if item.get("tag_name") == prefix["release_tag"]
        ),
        None,
    )


def _upload_missing(
    environment: ForgejoPublicationEnvironment,
    trace: list[dict[str, Any]],
    release: dict[str, Any],
) -> None:
    prefix = environment.prefix
    assets = _call(
        environment,
        trace,
        "list_release_assets",
        release_id=int(release["id"]),
    ).get("result", [])
    existing = {str(item.get("name")) for item in assets}
    for asset in prefix["expected_assets"]:
        if asset["name"] not in existing:
            _call(
                environment,
                trace,
                "upload_release_asset_from_repository",
                release_id=int(release["id"]),
                source_path=asset["source_path"],
                asset_name=asset["name"],
                ref=prefix["base_branch"],
            )


def run_fixed_forgejo_publication_baseline(
    name: str,
    *,
    environment: ForgejoPublicationEnvironment,
) -> tuple[dict[str, Any], ...]:
    if name not in PUBLICATION_BASELINE_NAMES:
        raise ValueError(f"unknown publication baseline: {name}")
    trace: list[dict[str, Any]] = []
    prefix = environment.prefix
    if name == "no_op":
        return ()
    if name == "blind_publish":
        _publish(environment, trace)
        return tuple(trace)
    release = _release(environment, trace)
    if name == "assume_release_exists":
        if release is not None:
            for asset in prefix["expected_assets"]:
                _call(
                    environment,
                    trace,
                    "upload_release_asset_from_repository",
                    release_id=int(release["id"]),
                    source_path=asset["source_path"],
                    asset_name=asset["name"],
                    ref=prefix["base_branch"],
                )
        return tuple(trace)
    if name == "repair_assets_only":
        if release is not None:
            _upload_missing(environment, trace, release)
        return tuple(trace)
    if name == "compact_release_tree":
        if release is None:
            created = _publish(environment, trace)
            release = created.get("result")
        if isinstance(release, dict):
            _upload_missing(environment, trace, release)
        _call(
            environment,
            trace,
            "close_milestone",
            milestone_id=int(prefix["milestone_id"]),
        )
        return tuple(trace)

    external = _call(
        environment, trace, "list_external_deliveries"
    ).get("result", [])
    external_keys = {str(item.get("key")) for item in external}
    for field in ("coordinator_hook_id", "provenance_hook_id"):
        history = _call(
            environment,
            trace,
            "get_webhook_history",
            hook_id=int(prefix[field]),
        ).get("result", [])
        for delivery in history:
            if (
                delivery.get("status") == "failed"
                and str(delivery.get("uuid")) not in external_keys
            ):
                _call(
                    environment,
                    trace,
                    "replay_webhook",
                    hook_id=int(prefix[field]),
                    delivery_uuid=str(delivery["uuid"]),
                )
    return tuple(trace)
