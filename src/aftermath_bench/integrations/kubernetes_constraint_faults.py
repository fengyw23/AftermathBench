from __future__ import annotations

from .kubernetes_constraint_prefix import (
    NAMESPACE,
    REGISTRY_PREPARE_KEY,
    REGISTRY_RELEASE_KEY,
    SERVICE,
    STABLE_DEPLOYMENT,
)
from .kubernetes_migration_faults import KubernetesMigrationFaultBoundary

KUBERNETES_CONSTRAINT_VARIANTS = (
    "failed_migration_without_preparation",
    "failed_migration_with_preparation",
    "committed_cutover_without_publication",
    "committed_cutover_with_publication",
)
SURFACE_ERROR = "HTTP connection lost before the change orchestration response"


class KubernetesConstraintFaultBoundary(KubernetesMigrationFaultBoundary):
    """Inject paired boundaries whose only pairwise difference is one event."""

    def _complete_cutover(self) -> dict:
        job = self._migration_job(failed=False)
        self._commit_schema(job)
        self._make_candidate_available()
        self.api.patch(
            "service",
            SERVICE,
            {"spec": {"selector": {"app": "orders", "version": "v2"}}},
            namespace=NAMESPACE,
        )
        self.api.patch(
            "deployment",
            STABLE_DEPLOYMENT,
            {"spec": {"replicas": 0}},
            namespace=NAMESPACE,
        )
        return job

    def trigger(self, variant: str) -> None:
        if variant not in KUBERNETES_CONSTRAINT_VARIANTS:
            raise ValueError(f"unknown Kubernetes constraint variant: {variant}")
        if variant.startswith("failed_migration_"):
            job = self._migration_job(failed=True)
            if variant.endswith("with_preparation"):
                self._post(
                    REGISTRY_PREPARE_KEY,
                    {
                        "application": "orders",
                        "version": "v2",
                        "migration_job_uid": str(job["metadata"]["uid"]),
                        "status": "prepared",
                    },
                )
        else:
            job = self._complete_cutover()
            if variant.endswith("with_publication"):
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


__all__ = [
    "KUBERNETES_CONSTRAINT_VARIANTS",
    "SURFACE_ERROR",
    "KubernetesConstraintFaultBoundary",
]
