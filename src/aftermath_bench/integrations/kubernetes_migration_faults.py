from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .kubernetes_api import KubernetesApi
from .kubernetes_migration_prefix import (
    CANDIDATE_DEPLOYMENT,
    MIGRATION_LABEL,
    NAMESPACE,
    REGISTRY_PREPARE_KEY,
    REGISTRY_RELEASE_KEY,
    SERVICE,
    migration_job_manifest,
)
from .kubernetes_settlement_recovery import _json_request

KUBERNETES_MIGRATION_VARIANTS = (
    "change_request_not_reached",
    "preparation_escaped_migration_failed",
    "schema_committed_cutover_pending",
    "cutover_and_publication_committed",
)
SURFACE_ERROR = "HTTP connection lost before the change orchestration response"


class KubernetesMigrationFaultBoundary:
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

    def _post(self, key: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self.json_request(
            f"{self.external_url}/webhooks/events",
            method="POST",
            payload=payload,
            headers={"X-Idempotency-Key": key},
        )

    def _migration_job(self, *, failed: bool) -> dict[str, Any]:
        job = self.api.create(migration_job_manifest(failed=failed))
        self.api.wait_condition(
            "job",
            str(job["metadata"]["name"]),
            condition="failed" if failed else "complete",
            namespace=NAMESPACE,
        )
        return self.api.get("job", str(job["metadata"]["name"]), namespace=NAMESPACE)

    def _commit_schema(self, job: dict[str, Any]) -> None:
        self.api.patch(
            "configmap",
            "database-catalog",
            {
                "data": {
                    "schemaEpoch": "2",
                    "migration": str(job["metadata"]["name"]),
                    "history": "epoch1->epoch2:no-down-migration",
                }
            },
            namespace=NAMESPACE,
        )

    def _make_candidate_available(self) -> None:
        self.api.patch(
            "deployment",
            CANDIDATE_DEPLOYMENT,
            {"spec": {"replicas": 1}},
            namespace=NAMESPACE,
        )
        self.api.wait_condition(
            "deployment",
            CANDIDATE_DEPLOYMENT,
            condition="available",
            namespace=NAMESPACE,
        )

    def trigger(self, variant: str) -> None:
        if variant not in KUBERNETES_MIGRATION_VARIANTS:
            raise ValueError(f"unknown Kubernetes migration variant: {variant}")
        if variant == "change_request_not_reached":
            raise ConnectionError(SURFACE_ERROR)
        if variant == "preparation_escaped_migration_failed":
            job = self._migration_job(failed=True)
            self._post(
                REGISTRY_PREPARE_KEY,
                {
                    "application": "orders",
                    "version": "v2",
                    "migration_job_uid": str(job["metadata"]["uid"]),
                    "status": "prepared",
                },
            )
        elif variant == "schema_committed_cutover_pending":
            job = self._migration_job(failed=False)
            self._commit_schema(job)
            self._make_candidate_available()
        elif variant == "cutover_and_publication_committed":
            job = self._migration_job(failed=False)
            self._commit_schema(job)
            self._make_candidate_available()
            self.api.patch(
                "service",
                SERVICE,
                {"spec": {"selector": {"app": "orders", "version": "v2"}}},
                namespace=NAMESPACE,
            )
            self._post(
                REGISTRY_RELEASE_KEY,
                {
                    "application": "orders",
                    "version": "v2",
                    "schema_epoch": "2",
                    "migration_job_uid": str(job["metadata"]["uid"]),
                    "status": "published",
                },
            )
        raise ConnectionError(SURFACE_ERROR)


def migration_jobs(api: KubernetesApi) -> list[dict[str, Any]]:
    return api.list(
        "jobs", namespace=NAMESPACE, selector=f"migration={MIGRATION_LABEL}"
    )
