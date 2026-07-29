from __future__ import annotations

import time
from typing import Any

from .kubernetes_api import KubernetesApi
from .kubernetes_settlement_prefix import (
    NAMESPACE,
    SETTLEMENT_TAINT_KEY,
    TARGET_BATCH,
    settlement_job_manifest,
)


KUBERNETES_SETTLEMENT_VARIANTS = (
    "job_create_request_not_reached",
    "job_created_response_lost",
    "job_created_controller_suspended",
    "job_created_pod_pending",
)
SURFACE_ERROR = "HTTP connection lost before a success response"


class KubernetesSettlementFaultBoundary:
    """Replays four native states behind one failed Job-create result."""

    def __init__(self, api: KubernetesApi) -> None:
        self.api = api

    def _nodes(self) -> list[str]:
        return [
            str(node["metadata"]["name"])
            for node in self.api.list("nodes")
        ]

    def _wait_for_pending_pod(self) -> None:
        for _ in range(120):
            pods = self.api.list(
                "pods",
                namespace=NAMESPACE,
                selector=f"batch={TARGET_BATCH}",
            )
            if pods and any(
                pod.get("status", {}).get("phase") == "Pending"
                for pod in pods
            ):
                return
            time.sleep(0.25)
        raise RuntimeError("settlement Job did not expose a pending Pod")

    def trigger(self, variant: str) -> None:
        if variant not in KUBERNETES_SETTLEMENT_VARIANTS:
            raise ValueError(f"unknown Kubernetes settlement variant: {variant}")
        if variant == "job_create_request_not_reached":
            raise ConnectionError(SURFACE_ERROR)

        if variant == "job_created_controller_suspended":
            self.api.create(settlement_job_manifest(suspended=True))
        elif variant == "job_created_pod_pending":
            for node in self._nodes():
                self.api.taint_node(
                    node,
                    f"{SETTLEMENT_TAINT_KEY}=true:NoSchedule",
                )
            self.api.create(settlement_job_manifest())
            self._wait_for_pending_pod()
        else:
            job = self.api.create(settlement_job_manifest())
            self.api.wait_condition(
                "job",
                str(job["metadata"]["name"]),
                condition="complete",
                namespace=NAMESPACE,
            )
        raise ConnectionError(SURFACE_ERROR)

    def capture(self) -> dict[str, Any]:
        return {
            "jobs": self.api.list("jobs", namespace=NAMESPACE),
            "pods": self.api.list(
                "pods",
                namespace=NAMESPACE,
                selector="app=vendor-settlement",
            ),
            "nodes": self.api.list("nodes"),
            "events": self.api.events(namespace=NAMESPACE),
        }
