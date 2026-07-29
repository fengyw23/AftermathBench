from __future__ import annotations

from typing import Any

from .kubernetes_migration_prefix import (
    CANDIDATE_DEPLOYMENT,
    RECOVERY_AUDIT_KEY,
    REGISTRY_COMPENSATION_KEY,
    REGISTRY_PREPARE_KEY,
    REGISTRY_RELEASE_KEY,
    SERVICE,
    STABLE_DEPLOYMENT,
    migration_job_manifest,
)
from .kubernetes_migration_recovery import KubernetesMigrationEnvironment

MIGRATION_BASELINES = (
    "no_op",
    "blind_retry",
    "always_rollback",
    "always_compensate",
    "always_forward",
    "always_repair_downstream",
)


def _call(
    environment: KubernetesMigrationEnvironment,
    tool: str,
    **kwargs: Any,
) -> Any:
    result = environment.invoke(tool, **kwargs)
    if not result.get("ok"):
        raise RuntimeError(f"baseline tool failed: {tool}: {result}")
    return result["result"]


def _record(
    environment: KubernetesMigrationEnvironment,
    *,
    direction: str,
    status: str,
    job_uid: str,
) -> None:
    _call(
        environment,
        "patch_object",
        resource="configmap",
        name="release-ledger",
        patch={"data": {"orders-v2.status": status}},
    )
    _call(
        environment,
        "patch_object",
        resource="configmap",
        name="recovery-audit",
        patch={
            "data": {
                "orders-v2.status": "complete",
                "orders-v2.direction": direction,
                "orders-v2.migration_job_uid": job_uid,
            }
        },
    )
    _call(
        environment,
        "post_external_event",
        idempotency_key=RECOVERY_AUDIT_KEY,
        payload={
            "application": "orders",
            "direction": direction,
            "status": "complete",
            "migration_job_uid": job_uid,
        },
    )


def run_kubernetes_migration_baseline(
    environment: KubernetesMigrationEnvironment,
    baseline: str,
) -> tuple[dict[str, Any], ...]:
    if baseline not in MIGRATION_BASELINES:
        raise ValueError(f"unknown migration baseline: {baseline}")
    if baseline == "no_op":
        return environment.event_log()
    if baseline == "blind_retry":
        _call(
            environment,
            "create_object",
            manifest=migration_job_manifest(),
        )
        return environment.event_log()

    jobs = _call(
        environment,
        "list_objects",
        resource="jobs",
        selector="migration=orders-v2",
    )
    job_uid = str(jobs[0]["metadata"]["uid"]) if jobs else "none"
    if baseline in {"always_rollback", "always_compensate"}:
        deployments = _call(environment, "list_objects", resource="deployments")
        if any(
            item.get("metadata", {}).get("name") == CANDIDATE_DEPLOYMENT
            for item in deployments
        ):
            _call(
                environment,
                "delete_object",
                resource="deployment",
                name=CANDIDATE_DEPLOYMENT,
            )
        _call(
            environment,
            "delete_object",
            resource="secret",
            name="orders-db-v2",
        )
        direction = (
            "rollback_to_stable"
            if baseline == "always_rollback"
            else "compensate_external_effect"
        )
        status = "aborted" if baseline == "always_rollback" else "compensated"
        if baseline == "always_compensate":
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
        _record(
            environment,
            direction=direction,
            status=status,
            job_uid=job_uid,
        )
        return environment.event_log()

    if baseline == "always_forward":
        _call(
            environment,
            "patch_object",
            resource="deployment",
            name=CANDIDATE_DEPLOYMENT,
            patch={"spec": {"replicas": 1}},
        )
        _call(environment, "wait_for_deployment", deployment=CANDIDATE_DEPLOYMENT)
        _call(
            environment,
            "patch_object",
            resource="service",
            name=SERVICE,
            patch={"spec": {"selector": {"app": "orders", "version": "v2"}}},
        )
        _call(
            environment,
            "patch_object",
            resource="deployment",
            name=STABLE_DEPLOYMENT,
            patch={"spec": {"replicas": 0}},
        )
        deliveries = _call(environment, "list_external_deliveries")
        if not any(item.get("key") == REGISTRY_RELEASE_KEY for item in deliveries):
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
        _record(
            environment,
            direction="forward_complete",
            status="active",
            job_uid=job_uid,
        )
        return environment.event_log()

    _call(
        environment,
        "patch_object",
        resource="deployment",
        name=STABLE_DEPLOYMENT,
        patch={"spec": {"replicas": 0}},
    )
    _record(
        environment,
        direction="repair_downstream_only",
        status="active",
        job_uid=job_uid,
    )
    return environment.event_log()
