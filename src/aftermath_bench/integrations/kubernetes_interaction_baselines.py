from __future__ import annotations

from typing import Any

from .kubernetes_interaction_prefix import (
    API_SERVICE,
    API_V1,
    API_V2,
    CURRENT_CREDENTIAL,
    NEXT_CREDENTIAL,
    PUBLICATION_LABEL,
    RECOVERY_AUDIT_KEY,
    REGISTRY_COMPENSATION_KEY,
    REGISTRY_PREPARE_KEY,
    REGISTRY_RELEASE_KEY,
    TRANSITION_LABEL,
    WORKER_V1,
    WORKER_V2,
    interaction_migration_job_manifest,
    publication_job_manifest,
    transition_job_manifest,
)
from .kubernetes_interaction_recovery import KubernetesInteractionEnvironment
from .kubernetes_migration_recovery import _replicas
from .kubernetes_settlement_recovery import _complete, _find

INTERACTION_BASELINES = (
    "no_op",
    "blind_retry",
    "always_abort",
    "always_compensate_abort",
    "always_defer_new_owner",
    "always_forward_new_owners",
    "always_publish_new_owner",
    "close_only",
    "compact_epoch_external_tree",
)


def _call(
    environment: KubernetesInteractionEnvironment,
    tool: str,
    **kwargs: Any,
) -> Any:
    result = environment.invoke(tool, **kwargs)
    if not result.get("ok"):
        raise RuntimeError(f"baseline tool failed: {tool}: {result}")
    return result["result"]


def _job_uid(jobs: list[dict[str, Any]], label: str, value: str) -> str:
    matched = [
        item
        for item in jobs
        if item.get("metadata", {}).get("labels", {}).get(label) == value
    ]
    return (
        str(matched[0].get("metadata", {}).get("uid", ""))
        if len(matched) == 1
        else "none"
    )


def _activate(
    environment: KubernetesInteractionEnvironment,
    deployments: list[dict[str, Any]],
    component: str,
    version: str,
) -> None:
    target = f"orders-{component}-{version}"
    other = f"orders-{component}-{'v1' if version == 'v2' else 'v2'}"
    if _replicas(_find(deployments, target) or {}) != 1:
        _call(
            environment,
            "patch_object",
            resource="deployment",
            name=target,
            patch={"spec": {"replicas": 1}},
        )
        _call(environment, "wait_for_deployment", deployment=target)
    if _replicas(_find(deployments, other) or {}) != 0:
        _call(
            environment,
            "patch_object",
            resource="deployment",
            name=other,
            patch={"spec": {"replicas": 0}},
        )
    if component == "api":
        _call(
            environment,
            "patch_object",
            resource="service",
            name=API_SERVICE,
            patch={
                "spec": {
                    "selector": {
                        "app": "orders",
                        "component": "api",
                        "version": version,
                    }
                }
            },
        )


def _close(
    environment: KubernetesInteractionEnvironment,
    *,
    status: str,
    epoch: str,
    api_version: str,
    worker_version: str,
    credential_generation: str,
    preparation_resolution: str,
    release_resolution: str,
) -> None:
    jobs = _call(environment, "list_objects", resource="jobs")
    migration_uid = _job_uid(jobs, "migration", "orders-platform-v2")
    transition_uid = _job_uid(jobs, "transition-owner", TRANSITION_LABEL)
    publication_uid = _job_uid(jobs, "publication-owner", PUBLICATION_LABEL)
    _call(
        environment,
        "patch_object",
        resource="configmap",
        name="change-record",
        patch={"data": {"orders-platform-v2.state": "resolved"}},
    )
    _call(
        environment,
        "patch_object",
        resource="configmap",
        name="release-ledger",
        patch={
            "data": {
                "orders-platform-v2.status": status,
                "orders-platform-v2.schema_epoch": epoch,
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
                "orders-platform-v2.status": "complete",
                "orders-platform-v2.schema_epoch": epoch,
                "orders-platform-v2.api_version": api_version,
                "orders-platform-v2.worker_version": worker_version,
                "orders-platform-v2.credential_generation": credential_generation,
                "orders-platform-v2.migration_job_uid": migration_uid,
                "orders-platform-v2.transition_job_uid": transition_uid,
                "orders-platform-v2.publication_job_uid": publication_uid,
                "orders-platform-v2.preparation_resolution": preparation_resolution,
                "orders-platform-v2.release_resolution": release_resolution,
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
            "api_version": api_version,
            "worker_version": worker_version,
            "credential_generation": credential_generation,
            "migration_job_uid": migration_uid,
            "transition_job_uid": transition_uid,
            "publication_job_uid": publication_uid,
        },
    )


def _abort(
    environment: KubernetesInteractionEnvironment,
    *,
    compensate: bool,
) -> None:
    deployments = _call(environment, "list_objects", resource="deployments")
    _activate(environment, deployments, "api", "v1")
    deployments = _call(environment, "list_objects", resource="deployments")
    _activate(environment, deployments, "worker", "v1")
    for resource, name in (
        ("deployment", API_V2),
        ("deployment", WORKER_V2),
        ("secret", NEXT_CREDENTIAL),
    ):
        _call(environment, "delete_object", resource=resource, name=name)
    _call(
        environment,
        "patch_object",
        resource="secret",
        name=CURRENT_CREDENTIAL,
        patch={"metadata": {"labels": {"credential-generation": "1"}}},
    )
    if compensate:
        jobs = _call(environment, "list_objects", resource="jobs")
        _call(
            environment,
            "post_external_event",
            idempotency_key=REGISTRY_COMPENSATION_KEY,
            payload={
                "application": "orders",
                "status": "compensated",
                "compensates": REGISTRY_PREPARE_KEY,
                "migration_job_uid": _job_uid(
                    jobs, "migration", "orders-platform-v2"
                ),
            },
        )
    _close(
        environment,
        status="aborted",
        epoch="1",
        api_version="v1",
        worker_version="v1",
        credential_generation="1",
        preparation_resolution="compensated" if compensate else "not-created",
        release_resolution="not-applicable",
    )


def _defer(environment: KubernetesInteractionEnvironment) -> None:
    deployments = _call(environment, "list_objects", resource="deployments")
    _activate(environment, deployments, "api", "v2")
    deployments = _call(environment, "list_objects", resource="deployments")
    _activate(environment, deployments, "worker", "v1")
    _call(
        environment,
        "patch_object",
        resource="secret",
        name=CURRENT_CREDENTIAL,
        patch={"metadata": {"labels": {"credential-generation": "1"}}},
    )
    _call(
        environment,
        "patch_object",
        resource="configmap",
        name="schema-compatibility-bridge",
        patch={"data": {"lease": "active"}},
    )
    _call(
        environment,
        "patch_object",
        resource="configmap",
        name="worker-batch-state",
        patch={"data": {"state": "inflight"}},
    )
    _call(
        environment,
        "create_object",
        manifest=transition_job_manifest(suspend=True),
    )
    _close(
        environment,
        status="deferred",
        epoch="2",
        api_version="v2",
        worker_version="v1",
        credential_generation="1",
        preparation_resolution="not-created",
        release_resolution="deferred",
    )


def _publication(
    environment: KubernetesInteractionEnvironment,
    *,
    create_transition: bool,
) -> None:
    deployments = _call(environment, "list_objects", resource="deployments")
    _activate(environment, deployments, "api", "v2")
    deployments = _call(environment, "list_objects", resource="deployments")
    _activate(environment, deployments, "worker", "v2")
    _call(
        environment,
        "patch_object",
        resource="secret",
        name=CURRENT_CREDENTIAL,
        patch={"metadata": {"labels": {"credential-generation": "2"}}},
    )
    _call(
        environment,
        "patch_object",
        resource="configmap",
        name="schema-compatibility-bridge",
        patch={"data": {"lease": "retired"}},
    )
    _call(
        environment,
        "patch_object",
        resource="configmap",
        name="worker-batch-state",
        patch={"data": {"state": "drained"}},
    )
    if create_transition:
        transition = _call(
            environment,
            "create_object",
            manifest=transition_job_manifest(suspend=False),
        )
        _call(
            environment,
            "wait_for_job",
            job=str(transition["metadata"]["name"]),
            condition="complete",
        )
    publication = _call(
        environment,
        "create_object",
        manifest=publication_job_manifest(suspend=False),
    )
    _call(
        environment,
        "wait_for_job",
        job=str(publication["metadata"]["name"]),
        condition="complete",
    )
    publication = _call(
        environment,
        "get_object",
        resource="job",
        name=str(publication["metadata"]["name"]),
    )
    jobs = _call(environment, "list_objects", resource="jobs")
    _call(
        environment,
        "post_external_event",
        idempotency_key=REGISTRY_RELEASE_KEY,
        payload={
            "application": "orders",
            "status": "published",
            "version": "v2",
            "schema_epoch": "2",
            "migration_job_uid": _job_uid(
                jobs, "migration", "orders-platform-v2"
            ),
            "publication_job_uid": str(publication["metadata"]["uid"]),
        },
    )
    _close(
        environment,
        status="active",
        epoch="2",
        api_version="v2",
        worker_version="v2",
        credential_generation="2",
        preparation_resolution="not-created",
        release_resolution="present",
    )


def _close_actual(environment: KubernetesInteractionEnvironment) -> None:
    facts = environment._boundary_facts
    epoch = str(facts["schema_epoch"])
    release = bool(facts["release_accepted"])
    preparation = bool(facts["preparation_present"])
    _close(
        environment,
        status="active" if release else "deferred" if epoch == "2" else "aborted",
        epoch=epoch,
        api_version=str(facts["api_version"]),
        worker_version=str(facts["worker_version"]),
        credential_generation=str(facts["credential_generation"]),
        preparation_resolution="released" if preparation and release else "not-created",
        release_resolution="present" if release else "deferred" if epoch == "2" else "not-applicable",
    )


def run_kubernetes_interaction_baseline(
    environment: KubernetesInteractionEnvironment,
    baseline: str,
) -> tuple[dict[str, Any], ...]:
    if baseline not in INTERACTION_BASELINES:
        raise ValueError(f"unknown interaction baseline: {baseline}")
    if baseline == "no_op":
        return environment.event_log()
    if baseline == "blind_retry":
        _call(
            environment,
            "create_object",
            manifest=interaction_migration_job_manifest(failed=False),
        )
        return environment.event_log()
    if baseline == "always_abort":
        _abort(environment, compensate=False)
    elif baseline == "always_compensate_abort":
        _abort(environment, compensate=True)
    elif baseline == "always_defer_new_owner":
        _defer(environment)
    elif baseline == "always_forward_new_owners":
        _publication(environment, create_transition=True)
    elif baseline == "always_publish_new_owner":
        _publication(environment, create_transition=False)
    elif baseline == "close_only":
        _close_actual(environment)
    elif baseline == "compact_epoch_external_tree":
        facts = environment._boundary_facts
        if str(facts["schema_epoch"]) == "1":
            _abort(environment, compensate=bool(facts["preparation_present"]))
        elif bool(facts["release_accepted"]):
            _close_actual(environment)
        else:
            _publication(environment, create_transition=False)
    return environment.event_log()


__all__ = [
    "INTERACTION_BASELINES",
    "run_kubernetes_interaction_baseline",
]
