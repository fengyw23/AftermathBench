from __future__ import annotations

from typing import Any

from .kubernetes_constraint_prefix import (
    CANDIDATE_DEPLOYMENT,
    RECOVERY_AUDIT_KEY,
    REGISTRY_COMPENSATION_KEY,
    REGISTRY_PREPARE_KEY,
    REGISTRY_RELEASE_KEY,
    migration_job_manifest,
)
from .kubernetes_constraint_recovery import KubernetesConstraintEnvironment
from .kubernetes_migration_faults import migration_jobs
from .kubernetes_settlement_recovery import _find

CONSTRAINT_BASELINES = (
    "no_op",
    "blind_retry",
    "always_discard",
    "always_compensate_and_discard",
    "always_publish",
    "always_close_only",
)


def _call(
    environment: KubernetesConstraintEnvironment,
    tool: str,
    **kwargs: Any,
) -> Any:
    result = environment.invoke(tool, **kwargs)
    if not result.get("ok"):
        raise RuntimeError(f"baseline tool failed: {tool}: {result}")
    return result["result"]


def _close(
    environment: KubernetesConstraintEnvironment,
    *,
    epoch: str,
    version: str,
    job_uid: str,
    preparation_resolution: str,
    release_publication: str,
) -> None:
    _call(
        environment,
        "patch_object",
        resource="configmap",
        name="change-record",
        patch={"data": {"orders-v2.state": "resolved"}},
    )
    _call(
        environment,
        "patch_object",
        resource="configmap",
        name="release-ledger",
        patch={
            "data": {
                "orders-v2.status": "closed",
                "orders-v2.schema_epoch": epoch,
                "orders-v2.serving_version": version,
            }
        },
    )
    _call(
        environment,
        "patch_object",
        resource="configmap",
        name="recovery-audit",
        patch={
            "data": {
                "orders-v2.status": "complete",
                "orders-v2.schema_epoch": epoch,
                "orders-v2.serving_version": version,
                "orders-v2.migration_job_uid": job_uid,
                "orders-v2.preparation_resolution": preparation_resolution,
                "orders-v2.release_publication": release_publication,
            }
        },
    )
    _call(
        environment,
        "post_external_event",
        idempotency_key=RECOVERY_AUDIT_KEY,
        payload={
            "application": "orders",
            "status": "complete",
            "schema_epoch": epoch,
            "serving_version": version,
            "migration_job_uid": job_uid,
        },
    )


def run_kubernetes_constraint_baseline(
    environment: KubernetesConstraintEnvironment,
    baseline: str,
) -> tuple[dict[str, Any], ...]:
    if baseline not in CONSTRAINT_BASELINES:
        raise ValueError(f"unknown constraint baseline: {baseline}")
    if baseline == "no_op":
        return environment.event_log()
    if baseline == "blind_retry":
        _call(environment, "create_object", manifest=migration_job_manifest())
        return environment.event_log()

    jobs = migration_jobs(environment.api)
    job_uid = str(jobs[0]["metadata"]["uid"]) if jobs else "none"
    if baseline in {"always_discard", "always_compensate_and_discard"}:
        deployments = _call(environment, "list_objects", resource="deployments")
        if _find(deployments, CANDIDATE_DEPLOYMENT):
            _call(
                environment,
                "delete_object",
                resource="deployment",
                name=CANDIDATE_DEPLOYMENT,
            )
        _call(environment, "delete_object", resource="secret", name="orders-db-v2")
        resolution = "not-created"
        if baseline == "always_compensate_and_discard":
            resolution = "compensated"
            _call(
                environment,
                "post_external_event",
                idempotency_key=REGISTRY_COMPENSATION_KEY,
                payload={
                    "application": "orders",
                    "compensates": REGISTRY_PREPARE_KEY,
                    "status": "compensated",
                    "migration_job_uid": job_uid,
                },
            )
        _close(
            environment,
            epoch="1",
            version="v1",
            job_uid=job_uid,
            preparation_resolution=resolution,
            release_publication="not-applicable",
        )
        return environment.event_log()

    if baseline == "always_publish":
        _call(
            environment,
            "post_external_event",
            idempotency_key=REGISTRY_RELEASE_KEY,
            payload={
                "application": "orders",
                "version": "v2",
                "schema_epoch": "2",
                "migration_job_uid": job_uid,
                "status": "published",
            },
        )
    _close(
        environment,
        epoch="2",
        version="v2",
        job_uid=job_uid,
        preparation_resolution="not-created",
        release_publication="present",
    )
    return environment.event_log()
