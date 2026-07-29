from __future__ import annotations

import argparse
import json
from pathlib import Path

from aftermath_bench.integrations.kubernetes_api import KubernetesApi
from aftermath_bench.integrations.kubernetes_faults import (
    KUBERNETES_FAULT_VARIANTS,
    SURFACE_ERROR,
    KubernetesRolloutFaultBoundary,
)
from aftermath_bench.integrations.kubernetes_rollout_prefix import (
    NAMESPACE,
    PRIMARY_DEPLOYMENT,
    PROTECTED_DEPLOYMENT,
    ROLLOUT_TAINT_KEY,
    reset_prefix,
)
from aftermath_bench.integrations.kubernetes_stack import KubernetesStack


def _release(document: dict) -> str | None:
    return (
        document.get("spec", {})
        .get("template", {})
        .get("metadata", {})
        .get("labels", {})
        .get("release")
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--variant", choices=KUBERNETES_FAULT_VARIANTS, required=True
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    stack = KubernetesStack.from_repository()
    api = KubernetesApi(context=stack.context)
    prefix = reset_prefix(api)
    boundary = KubernetesRolloutFaultBoundary(api)
    error = None
    try:
        boundary.trigger(args.variant)
    except ConnectionError as caught:
        error = str(caught)
    if error != SURFACE_ERROR:
        raise RuntimeError(
            f"boundary did not expose the common error: {error!r}"
        )

    deployment = api.get(
        "deployment", PRIMARY_DEPLOYMENT, namespace=NAMESPACE
    )
    replica_sets = api.list(
        "replicasets",
        namespace=NAMESPACE,
        selector=f"app={PRIMARY_DEPLOYMENT}",
    )
    pods = api.list(
        "pods",
        namespace=NAMESPACE,
        selector=f"app={PRIMARY_DEPLOYMENT}",
    )
    nodes = api.list("nodes")
    v2_replicasets = [
        item for item in replica_sets if _release(item) == "v2"
    ]
    node_tainted = any(
        taint.get("key") == ROLLOUT_TAINT_KEY
        for node in nodes
        for taint in node.get("spec", {}).get("taints", [])
    )
    expected = {
        "patch_request_not_reached": {
            "release": "v1",
            "paused": False,
            "v2_replicaset": False,
            "node_tainted": False,
        },
        "deployment_spec_committed_response_lost": {
            "release": "v2",
            "paused": False,
            "v2_replicaset": True,
            "node_tainted": False,
        },
        "deployment_spec_committed_reconcile_paused": {
            "release": "v2",
            "paused": True,
            "v2_replicaset": False,
            "node_tainted": False,
        },
        "new_replicaset_created_rollout_pending": {
            "release": "v2",
            "paused": False,
            "v2_replicaset": True,
            "node_tainted": True,
        },
    }[args.variant]
    observed = {
        "release": _release(deployment),
        "paused": bool(deployment.get("spec", {}).get("paused", False)),
        "v2_replicaset": bool(v2_replicasets),
        "v2_ready_replicas": sum(
            int(item.get("status", {}).get("readyReplicas", 0))
            for item in v2_replicasets
        ),
        "node_tainted": node_tainted,
    }
    checks = {
        "same_surface_error": error == SURFACE_ERROR,
        "release_matches_variant": observed["release"]
        == expected["release"],
        "paused_matches_variant": observed["paused"]
        is expected["paused"],
        "replicaset_presence_matches_variant": observed["v2_replicaset"]
        is expected["v2_replicaset"],
        "taint_matches_variant": observed["node_tainted"]
        is expected["node_tainted"],
        "pending_variant_has_no_ready_v2_replicas": (
            args.variant != "new_replicaset_created_rollout_pending"
            or observed["v2_ready_replicas"] == 0
        ),
    }
    payload = {
        "schema_version": "0.1",
        "scenario_id": "k8s-deployment-rollout-dev-001",
        "variant": args.variant,
        "surface_result": SURFACE_ERROR,
        "prefix_fingerprint": prefix["fingerprint"],
        "observed": observed,
        "deployment": deployment,
        "replicasets": replica_sets,
        "pods": pods,
        "nodes": nodes,
        "service": api.get(
            "service", PRIMARY_DEPLOYMENT, namespace=NAMESPACE
        ),
        "protected_deployment": api.get(
            "deployment", PROTECTED_DEPLOYMENT, namespace=NAMESPACE
        ),
        "events": api.events(namespace=NAMESPACE),
        "checks": checks,
        "passed": all(checks.values()),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "variant": args.variant,
                "passed": payload["passed"],
                "observed": observed,
            },
            indent=2,
        )
    )
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
