from __future__ import annotations

import time
from typing import Any

from .kubernetes_api import KubernetesApi
from .kubernetes_rollout_prefix import (
    NAMESPACE,
    PRIMARY_DEPLOYMENT,
    ROLLOUT_TAINT_KEY,
    target_deployment_patch,
)


KUBERNETES_FAULT_VARIANTS = (
    "patch_request_not_reached",
    "deployment_spec_committed_response_lost",
    "deployment_spec_committed_reconcile_paused",
    "new_replicaset_created_rollout_pending",
)

SURFACE_ERROR = "HTTP connection lost before a success response"


class KubernetesRolloutFaultBoundary:
    """Creates only native Kubernetes states, then exposes one common error."""

    def __init__(self, api: KubernetesApi) -> None:
        self.api = api

    def _nodes(self) -> list[str]:
        return [
            str(node["metadata"]["name"])
            for node in self.api.list("nodes")
        ]

    def _new_release_replicasets(self) -> list[dict[str, Any]]:
        return [
            replica_set
            for replica_set in self.api.list(
                "replicasets",
                namespace=NAMESPACE,
                selector=f"app={PRIMARY_DEPLOYMENT}",
            )
            if replica_set.get("spec", {})
            .get("template", {})
            .get("metadata", {})
            .get("labels", {})
            .get("release")
            == "v2"
        ]

    def _wait_for_pending_replicaset(self) -> None:
        for _ in range(120):
            replica_sets = self._new_release_replicasets()
            if replica_sets and all(
                int(replica_set.get("status", {}).get("readyReplicas", 0))
                == 0
                for replica_set in replica_sets
            ):
                return
            time.sleep(0.25)
        raise RuntimeError("native v2 ReplicaSet did not enter pending state")

    def trigger(self, variant: str) -> None:
        if variant not in KUBERNETES_FAULT_VARIANTS:
            raise ValueError(f"unknown Kubernetes fault variant: {variant}")
        if variant == "patch_request_not_reached":
            raise ConnectionError(SURFACE_ERROR)

        if variant == "deployment_spec_committed_reconcile_paused":
            self.api.patch(
                "deployment",
                PRIMARY_DEPLOYMENT,
                {"spec": {"paused": True}},
                namespace=NAMESPACE,
            )
        elif variant == "new_replicaset_created_rollout_pending":
            for node in self._nodes():
                self.api.taint_node(
                    node,
                    f"{ROLLOUT_TAINT_KEY}=true:NoSchedule",
                )

        self.api.patch(
            "deployment",
            PRIMARY_DEPLOYMENT,
            target_deployment_patch(),
            namespace=NAMESPACE,
        )
        if variant == "deployment_spec_committed_response_lost":
            self.api.wait_rollout(
                PRIMARY_DEPLOYMENT, namespace=NAMESPACE
            )
        elif variant == "new_replicaset_created_rollout_pending":
            self._wait_for_pending_replicaset()
        raise ConnectionError(SURFACE_ERROR)
