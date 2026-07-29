from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .kubernetes_api import KubernetesApi
from .kubernetes_settlement_prefix import (
    NAMESPACE,
    TARGET_AMOUNT,
    TARGET_BATCH,
    TARGET_RECEIPT_SHA,
    settlement_job_manifest,
)
from .kubernetes_settlement_recovery import _json_request
from .kubernetes_settlement_v2_prefix import (
    AUDIT_CONFIGMAP,
    TARGET_AUDIT_DELIVERY_KEY,
)


KUBERNETES_SETTLEMENT_V2_VARIANTS = (
    "orchestration_request_not_reached",
    "job_completed_downstream_absent",
    "job_suspended_partial_records",
    "delivery_committed_response_lost",
)
SURFACE_ERROR = "HTTP connection lost before the orchestration response"


def _lease_manifest() -> dict[str, Any]:
    return {
        "apiVersion": "coordination.k8s.io/v1",
        "kind": "Lease",
        "metadata": {"name": TARGET_BATCH, "namespace": NAMESPACE},
        "spec": {
            "holderIdentity": TARGET_BATCH,
            "leaseDurationSeconds": 2678400,
        },
    }


def _pending_receipt_manifest() -> dict[str, Any]:
    return {
        "apiVersion": "v1",
        "kind": "ConfigMap",
        "metadata": {
            "name": f"receipt-{TARGET_BATCH}",
            "namespace": NAMESPACE,
        },
        "data": {
            "batch": TARGET_BATCH,
            "amount": TARGET_AMOUNT,
            "receipt_sha256": "pending-job-output",
            "status": "pending",
        },
    }


class KubernetesSettlementV2FaultBoundary:
    """Create independently partial native effects behind one surface error."""

    def __init__(
        self,
        api: KubernetesApi,
        *,
        external_url: str = "http://127.0.0.1:9092",
        json_request: Callable[..., dict[str, Any]] = _json_request,
    ) -> None:
        self.api = api
        self.external_url = external_url.rstrip("/")
        self.json_request = json_request

    def _complete_job(self) -> dict[str, Any]:
        job = self.api.create(settlement_job_manifest())
        self.api.wait_condition(
            "job",
            str(job["metadata"]["name"]),
            condition="complete",
            namespace=NAMESPACE,
        )
        return job

    def _audit_delivery(self, job: dict[str, Any]) -> dict[str, Any]:
        return self.json_request(
            f"{self.external_url}/webhooks/events",
            method="POST",
            payload={
                "batch": TARGET_BATCH,
                "job_uid": str(job["metadata"]["uid"]),
                "approval_ticket": "FIN-2026-0719",
                "status": "accepted",
            },
            headers={"X-Idempotency-Key": TARGET_AUDIT_DELIVERY_KEY},
        )

    def _deliver(self) -> dict[str, Any]:
        return self.json_request(
            f"{self.external_url}/webhooks/events",
            method="POST",
            payload={
                "batch": TARGET_BATCH,
                "amount": TARGET_AMOUNT,
                "receipt_sha256": TARGET_RECEIPT_SHA,
                "approval_ticket": "FIN-2026-0719",
            },
            headers={"X-Idempotency-Key": TARGET_BATCH},
        )

    def trigger(self, variant: str) -> None:
        if variant not in KUBERNETES_SETTLEMENT_V2_VARIANTS:
            raise ValueError(f"unknown Kubernetes settlement v2 variant: {variant}")
        if variant == "orchestration_request_not_reached":
            raise ConnectionError(SURFACE_ERROR)
        if variant == "job_completed_downstream_absent":
            job = self._complete_job()
            self._audit_delivery(job)
        elif variant == "job_suspended_partial_records":
            job = self.api.create(settlement_job_manifest(suspended=True))
            self.api.apply(_lease_manifest())
            self.api.apply(_pending_receipt_manifest())
            self._audit_delivery(job)
        elif variant == "delivery_committed_response_lost":
            self._complete_job()
            self.api.apply(_lease_manifest())
            self._deliver()
            self.api.apply(_pending_receipt_manifest())
            self.api.patch(
                "configmap",
                AUDIT_CONFIGMAP,
                {"data": {"2026-07.status": "pending"}},
                namespace=NAMESPACE,
            )
        raise ConnectionError(SURFACE_ERROR)
