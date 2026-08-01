from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .kubernetes_api import KubernetesApi
from .kubernetes_interaction_prefix import (
    APPLICATION,
    API_SERVICE,
    API_V1,
    API_V2,
    COMPATIBILITY_BRIDGE,
    CURRENT_EPOCH,
    CURRENT_VERSION,
    CURRENT_CREDENTIAL,
    DATABASE_CATALOG,
    MIGRATION_LABEL,
    NAMESPACE,
    PUBLICATION_LABEL,
    REGISTRY_PREPARE_KEY,
    REGISTRY_RELEASE_KEY,
    TRANSITION_LABEL,
    TARGET_EPOCH,
    TARGET_VERSION,
    BATCH_STATE,
    WORKER_V1,
    WORKER_V2,
    interaction_migration_job_manifest,
    publication_job_manifest,
    transition_job_manifest,
)
from .kubernetes_interaction_scope import (
    INTERACTION_VARIANT_FACTS,
    KUBERNETES_INTERACTION_VARIANTS,
)
from .kubernetes_settlement_recovery import _complete, _json_request

SURFACE_ERROR = "HTTP connection lost before the change orchestration response"


def _replicas(document: dict[str, Any]) -> int:
    return int(document.get("spec", {}).get("replicas", 0))


def interaction_jobs(
    api: KubernetesApi,
    *,
    label_key: str,
    label_value: str,
) -> list[dict[str, Any]]:
    return api.list(
        "jobs",
        namespace=NAMESPACE,
        selector=f"{label_key}={label_value}",
    )


def _consumer_version(api: KubernetesApi, component: str) -> str:
    versions = []
    names = {
        "api": {CURRENT_VERSION: API_V1, TARGET_VERSION: API_V2},
        "worker": {CURRENT_VERSION: WORKER_V1, TARGET_VERSION: WORKER_V2},
    }[component]
    for version, name in names.items():
        document = api.get("deployment", name, namespace=NAMESPACE)
        if _replicas(document) > 0:
            versions.append(version)
    return versions[0] if len(versions) == 1 else "invalid"


def _job_state(jobs: list[dict[str, Any]]) -> str:
    if not jobs:
        return "absent"
    if len(jobs) != 1:
        return "duplicate"
    job = jobs[0]
    if _complete(job):
        return "completed"
    if bool(job.get("spec", {}).get("suspend", False)):
        return "suspended"
    return "pending"


def _publication_state(jobs: list[dict[str, Any]]) -> str:
    state = _job_state(jobs)
    return "pending" if state == "suspended" else state


def capture_interaction_facts(
    api: KubernetesApi,
    *,
    external_keys: set[str],
) -> dict[str, Any]:
    catalog = api.get("configmap", DATABASE_CATALOG, namespace=NAMESPACE)
    bridge = api.get(
        "configmap", COMPATIBILITY_BRIDGE, namespace=NAMESPACE
    )
    batch = api.get("configmap", BATCH_STATE, namespace=NAMESPACE)
    credential = api.get("secret", CURRENT_CREDENTIAL, namespace=NAMESPACE)
    migration = interaction_jobs(
        api, label_key="migration", label_value=MIGRATION_LABEL
    )
    transition = interaction_jobs(
        api, label_key="transition-owner", label_value=TRANSITION_LABEL
    )
    publication = interaction_jobs(
        api, label_key="publication-owner", label_value=PUBLICATION_LABEL
    )
    migration_state = "missing"
    if len(migration) == 1:
        migration_state = (
            "committed"
            if _complete(migration[0])
            else "failed"
            if int(migration[0].get("status", {}).get("failed", 0)) == 1
            else "pending"
        )
    return {
        "schema_epoch": str(catalog.get("data", {}).get("schemaEpoch", "")),
        "migration_state": migration_state,
        "api_version": _consumer_version(api, "api"),
        "worker_version": _consumer_version(api, "worker"),
        "credential_generation": str(
            credential.get("metadata", {})
            .get("labels", {})
            .get("credential-generation", "")
        ),
        "bridge_lease": str(bridge.get("data", {}).get("lease", "")),
        "batch_state": str(batch.get("data", {}).get("state", "")),
        "transition_controller": _job_state(transition),
        "publication_task": _publication_state(publication),
        "preparation_present": REGISTRY_PREPARE_KEY in external_keys,
        "release_accepted": REGISTRY_RELEASE_KEY in external_keys,
    }


class KubernetesInteractionFaultBoundary:
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

    def _migration(self, state: str) -> dict[str, Any]:
        failed = state == "failed"
        job = self.api.create(interaction_migration_job_manifest(failed=failed))
        self.api.wait_condition(
            "job",
            str(job["metadata"]["name"]),
            condition="failed" if failed else "complete",
            namespace=NAMESPACE,
        )
        return self.api.get(
            "job", str(job["metadata"]["name"]), namespace=NAMESPACE
        )

    def _set_consumer(self, component: str, version: str) -> None:
        names = {
            "api": {CURRENT_VERSION: API_V1, TARGET_VERSION: API_V2},
            "worker": {CURRENT_VERSION: WORKER_V1, TARGET_VERSION: WORKER_V2},
        }[component]
        target = names[version]
        other = names[
            CURRENT_VERSION if version == TARGET_VERSION else TARGET_VERSION
        ]
        self.api.patch(
            "deployment", target, {"spec": {"replicas": 1}}, namespace=NAMESPACE
        )
        self.api.wait_condition(
            "deployment", target, condition="available", namespace=NAMESPACE
        )
        self.api.patch(
            "deployment", other, {"spec": {"replicas": 0}}, namespace=NAMESPACE
        )
        if component == "api":
            self.api.patch(
                "service",
                API_SERVICE,
                {
                    "spec": {
                        "selector": {
                            "app": APPLICATION,
                            "component": "api",
                            "version": version,
                        }
                    }
                },
                namespace=NAMESPACE,
            )

    def _create_job_state(self, kind: str, state: str) -> dict[str, Any] | None:
        if state == "absent":
            return None
        manifest = (
            transition_job_manifest(suspend=state == "suspended")
            if kind == "transition"
            else publication_job_manifest(suspend=state == "pending")
        )
        job = self.api.create(manifest)
        if state == "completed":
            self.api.wait_condition(
                "job", str(job["metadata"]["name"]), condition="complete", namespace=NAMESPACE
            )
        return self.api.get("job", str(job["metadata"]["name"]), namespace=NAMESPACE)

    def trigger(self, variant: str) -> None:
        if variant not in KUBERNETES_INTERACTION_VARIANTS:
            raise ValueError(f"unknown Kubernetes interaction variant: {variant}")
        facts = INTERACTION_VARIANT_FACTS[variant]
        migration = self._migration(str(facts["migration_state"]))
        if str(facts["schema_epoch"]) == TARGET_EPOCH:
            self.api.patch(
                "configmap",
                DATABASE_CATALOG,
                {
                    "data": {
                        "schemaEpoch": TARGET_EPOCH,
                        "migration": str(migration["metadata"]["name"]),
                        "history": f"epoch{CURRENT_EPOCH}->epoch{TARGET_EPOCH}:no-down-migration",
                    }
                },
                namespace=NAMESPACE,
            )
        self._set_consumer("api", str(facts["api_version"]))
        self._set_consumer("worker", str(facts["worker_version"]))
        self.api.patch(
            "secret",
            CURRENT_CREDENTIAL,
            {
                "metadata": {
                    "labels": {
                        "credential-generation": str(
                            facts["credential_generation"]
                        )
                    }
                }
            },
            namespace=NAMESPACE,
        )
        self.api.patch(
            "configmap",
            COMPATIBILITY_BRIDGE,
            {"data": {"lease": str(facts["bridge_lease"])}},
            namespace=NAMESPACE,
        )
        self.api.patch(
            "configmap",
            BATCH_STATE,
            {"data": {"state": str(facts["batch_state"])}},
            namespace=NAMESPACE,
        )
        transition = self._create_job_state(
            "transition", str(facts["transition_controller"])
        )
        publication = self._create_job_state(
            "publication", str(facts["publication_task"])
        )
        migration_uid = str(migration["metadata"]["uid"])
        if bool(facts["preparation_present"]):
            self._post(
                REGISTRY_PREPARE_KEY,
                {
                    "application": APPLICATION,
                    "version": TARGET_VERSION,
                    "migration_job_uid": migration_uid,
                    "status": "prepared",
                },
            )
        if bool(facts["release_accepted"]):
            if publication is None:
                raise RuntimeError("accepted release requires publication Job")
            self._post(
                REGISTRY_RELEASE_KEY,
                {
                    "application": APPLICATION,
                    "version": TARGET_VERSION,
                    "schema_epoch": TARGET_EPOCH,
                    "migration_job_uid": migration_uid,
                    "publication_job_uid": str(publication["metadata"]["uid"]),
                    "status": "published",
                },
            )
        _ = transition
        raise ConnectionError(SURFACE_ERROR)


__all__ = [
    "KUBERNETES_INTERACTION_VARIANTS",
    "SURFACE_ERROR",
    "KubernetesInteractionFaultBoundary",
    "capture_interaction_facts",
    "interaction_jobs",
]
