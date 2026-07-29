from __future__ import annotations

from typing import Any

from .kubernetes_recovery import KubernetesRolloutEnvironment, _release
from .kubernetes_rollout_prefix import (
    NAMESPACE,
    PRIMARY_DEPLOYMENT,
    ROLLOUT_TAINT_KEY,
    target_deployment_patch,
)


BASELINE_NAMES = (
    "no_op",
    "blind_retry",
    "assume_committed",
    "repair_failed_record_only",
    "all_rollback",
    "switch_traffic_immediately",
    "compact_boundary_tree",
)


def _call(
    environment: KubernetesRolloutEnvironment,
    trace: list[dict[str, Any]],
    tool: str,
    **arguments: Any,
) -> dict[str, Any]:
    result = environment.invoke(tool, **arguments)
    trace.append({"tool": tool, "arguments": arguments, "result": result})
    return result


def _target_service_patch() -> dict[str, Any]:
    return {
        "spec": {
            "selector": {
                "app": PRIMARY_DEPLOYMENT,
                "track": "stable",
                "release": "v2",
            }
        }
    }


def _complete_fixed_downstream(
    environment: KubernetesRolloutEnvironment,
    trace: list[dict[str, Any]],
) -> None:
    _call(
        environment,
        trace,
        "wait_for_rollout",
        deployment=PRIMARY_DEPLOYMENT,
        namespace=NAMESPACE,
        timeout="180s",
    )
    _call(
        environment,
        trace,
        "patch_object",
        resource="configmap",
        name="checkout-release",
        namespace=NAMESPACE,
        patch={"data": {"release": "v2"}},
    )
    _call(
        environment,
        trace,
        "patch_object",
        resource="service",
        name=PRIMARY_DEPLOYMENT,
        namespace=NAMESPACE,
        patch=_target_service_patch(),
    )


def run_fixed_kubernetes_baseline(
    name: str,
    *,
    environment: KubernetesRolloutEnvironment,
) -> tuple[dict[str, Any], ...]:
    """Execute one fixed policy against the native rollout boundary.

    These policies intentionally span common retry/rollback heuristics plus
    one compact state tree.  If the compact tree solves every matched state,
    the family is useful as a recovery case but is not admitted as hard.
    """

    if name not in BASELINE_NAMES:
        raise ValueError(f"unknown Kubernetes baseline: {name}")
    trace: list[dict[str, Any]] = []
    if name == "no_op":
        return ()
    if name == "blind_retry":
        _call(
            environment,
            trace,
            "patch_object",
            resource="deployment",
            name=PRIMARY_DEPLOYMENT,
            namespace=NAMESPACE,
            patch=target_deployment_patch(),
        )
        return tuple(trace)
    if name == "assume_committed":
        _complete_fixed_downstream(environment, trace)
        return tuple(trace)
    if name == "repair_failed_record_only":
        deployment = _call(
            environment,
            trace,
            "get_object",
            resource="deployment",
            name=PRIMARY_DEPLOYMENT,
            namespace=NAMESPACE,
        ).get("result", {})
        if _release(deployment) != "v2":
            _call(
                environment,
                trace,
                "patch_object",
                resource="deployment",
                name=PRIMARY_DEPLOYMENT,
                namespace=NAMESPACE,
                patch=target_deployment_patch(),
            )
        return tuple(trace)
    if name == "all_rollback":
        _call(
            environment,
            trace,
            "patch_object",
            resource="deployment",
            name=PRIMARY_DEPLOYMENT,
            namespace=NAMESPACE,
            patch={
                "spec": {
                    "paused": False,
                    "template": {
                        "metadata": {
                            "labels": {"release": "v1"},
                            "annotations": {
                                "aftermath.dev/config-revision": "v1"
                            },
                        },
                        "spec": {
                            "containers": [
                                {
                                    "name": "checkout-api",
                                    "image": "nginx:1.27.5-alpine",
                                }
                            ]
                        },
                    },
                }
            },
        )
        return tuple(trace)
    if name == "switch_traffic_immediately":
        _call(
            environment,
            trace,
            "patch_object",
            resource="service",
            name=PRIMARY_DEPLOYMENT,
            namespace=NAMESPACE,
            patch=_target_service_patch(),
        )
        return tuple(trace)

    deployment = _call(
        environment,
        trace,
        "get_object",
        resource="deployment",
        name=PRIMARY_DEPLOYMENT,
        namespace=NAMESPACE,
    ).get("result", {})
    nodes = _call(
        environment,
        trace,
        "list_objects",
        resource="nodes",
    ).get("result", [])
    if _release(deployment) != "v2":
        _call(
            environment,
            trace,
            "patch_object",
            resource="deployment",
            name=PRIMARY_DEPLOYMENT,
            namespace=NAMESPACE,
            patch=target_deployment_patch(),
        )
    elif bool(deployment.get("spec", {}).get("paused", False)):
        _call(
            environment,
            trace,
            "patch_object",
            resource="deployment",
            name=PRIMARY_DEPLOYMENT,
            namespace=NAMESPACE,
            patch={"spec": {"paused": False}},
        )
    for node in nodes:
        if any(
            taint.get("key") == ROLLOUT_TAINT_KEY
            for taint in node.get("spec", {}).get("taints", [])
        ):
            _call(
                environment,
                trace,
                "remove_node_taint",
                node=str(node["metadata"]["name"]),
                key=ROLLOUT_TAINT_KEY,
            )
    _complete_fixed_downstream(environment, trace)
    return tuple(trace)
