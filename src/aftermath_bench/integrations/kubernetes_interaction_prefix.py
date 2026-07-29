from __future__ import annotations

import json
from hashlib import sha256
from typing import Any

from .kubernetes_api import KubernetesApi
from .kubernetes_migration_prefix import _stable_migration_object
from .kubernetes_settlement_prefix import WORKER_IMAGE

SCENARIO_ID = "k8s-constraint-interactions-dev-005"
NAMESPACE = "aftermath-interactions"
API_SERVICE = "orders-api"
API_V1 = "orders-api-v1"
API_V2 = "orders-api-v2"
WORKER_V1 = "orders-worker-v1"
WORKER_V2 = "orders-worker-v2"
CURRENT_CREDENTIAL = "orders-db-current"
NEXT_CREDENTIAL = "orders-db-next"
BACKUP_JOB = "orders-backup-epoch1"
MIGRATION_LABEL = "orders-platform-v2"
TRANSITION_LABEL = "orders-worker-transition"
PUBLICATION_LABEL = "orders-release-publication"
REGISTRY_STABLE_KEY = "release:orders-platform-v1"
REGISTRY_PREPARE_KEY = "prepare:orders-platform-v2"
REGISTRY_RELEASE_KEY = "release:orders-platform-v2"
REGISTRY_COMPENSATION_KEY = "compensate:prepare:orders-platform-v2"
RECOVERY_AUDIT_KEY = "audit:recovery:orders-platform-v2"

CONTRACT_CONFIGMAPS = (
    "schema-contract",
    "compatibility-contract",
    "credential-contract",
    "controller-contract",
    "publication-contract",
    "audit-contract",
)


def _configmap(name: str, data: dict[str, str]) -> dict[str, Any]:
    return {
        "apiVersion": "v1",
        "kind": "ConfigMap",
        "metadata": {"name": name, "namespace": NAMESPACE},
        "data": data,
    }


def _deployment(component: str, version: str, replicas: int) -> dict[str, Any]:
    name = f"orders-{component}-{version}"
    labels = {"app": "orders", "component": component, "version": version}
    return {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {"name": name, "namespace": NAMESPACE, "labels": labels},
        "spec": {
            "replicas": replicas,
            "selector": {"matchLabels": labels},
            "template": {
                "metadata": {"labels": labels},
                "spec": {
                    "serviceAccountName": "orders-runner",
                    "containers": [
                        {
                            "name": component,
                            "image": WORKER_IMAGE,
                            "imagePullPolicy": "Never",
                            "command": [
                                "python",
                                "-c",
                                "import time; time.sleep(3600)",
                            ],
                            "env": [
                                {"name": "APP_VERSION", "value": version},
                                {
                                    "name": "DB_TOKEN",
                                    "valueFrom": {
                                        "secretKeyRef": {
                                            "name": CURRENT_CREDENTIAL,
                                            "key": "token",
                                        }
                                    },
                                },
                            ],
                        }
                    ],
                },
            },
        },
    }


def _job(
    *,
    name: str,
    label_key: str,
    label_value: str,
    command: str,
    suspend: bool = False,
) -> dict[str, Any]:
    labels = {"app": "orders", label_key: label_value}
    return {
        "apiVersion": "batch/v1",
        "kind": "Job",
        "metadata": {"name": name, "namespace": NAMESPACE, "labels": labels},
        "spec": {
            "backoffLimit": 0,
            "suspend": suspend,
            "template": {
                "metadata": {"labels": labels},
                "spec": {
                    "serviceAccountName": "orders-runner",
                    "restartPolicy": "Never",
                    "containers": [
                        {
                            "name": "controller",
                            "image": WORKER_IMAGE,
                            "imagePullPolicy": "Never",
                            "command": ["python", "-c", command],
                        }
                    ],
                },
            },
        },
    }


def interaction_migration_job_manifest(*, failed: bool) -> dict[str, Any]:
    command = (
        "raise SystemExit('platform migration failed before commit')"
        if failed
        else "print('platform schema epoch 2 committed')"
    )
    manifest = _job(
        name="placeholder",
        label_key="migration",
        label_value=MIGRATION_LABEL,
        command=command,
    )
    manifest["metadata"].pop("name")
    manifest["metadata"]["generateName"] = "orders-platform-migration-"
    return manifest


def transition_job_manifest(*, suspend: bool = True) -> dict[str, Any]:
    return _job(
        name="orders-worker-transition",
        label_key="transition-owner",
        label_value=TRANSITION_LABEL,
        command="print('worker transition controller observed state')",
        suspend=suspend,
    )


def publication_job_manifest(*, suspend: bool = True) -> dict[str, Any]:
    return _job(
        name="orders-release-publication",
        label_key="publication-owner",
        label_value=PUBLICATION_LABEL,
        command="print('release publication controller prepared payload')",
        suspend=suspend,
    )


def interaction_prefix_manifests() -> tuple[dict[str, Any], ...]:
    return (
        {"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": NAMESPACE}},
        _configmap(
            "schema-contract",
            {
                "epochMonotonic": "true",
                "downMigrationAllowed": "false",
                "apiV1CompatibleEpochs": "1",
                "apiV2CompatibleEpochs": "2",
                "workerV1CompatibleEpochs": "1; epoch 2 only under compatibility-contract",
                "workerV2CompatibleEpochs": "2",
                "migrationEvidence": "preserve every Job labeled migration=orders-platform-v2",
            },
        ),
        _configmap(
            "compatibility-contract",
            {
                "bridgeRecord": "schema-compatibility-bridge",
                "batchRecord": "worker-batch-state",
                "bridgeException": "worker v1 may coexist with epoch 2 only when lease=active and batch.state=inflight",
                "expiredLease": "cannot authorize a v1 worker at epoch 2",
                "retirementRule": "lease=retired after worker v2 is active and batch.state=drained",
                "nonReplayableBatch": "must not stop worker v1 while batch.state=inflight",
            },
        ),
        _configmap(
            "credential-contract",
            {
                "sharedSecret": CURRENT_CREDENTIAL,
                "generationLabel": "metadata.labels.credential-generation",
                "v1AllowedGenerations": "1",
                "v2AllowedGenerations": "1,2",
                "targetGeneration": "2",
                "rotationGuard": "generation 2 is legal only when no active v1 consumer remains",
                "candidateSecret": NEXT_CREDENTIAL,
            },
        ),
        _configmap(
            "controller-contract",
            {
                "transitionSelector": f"transition-owner={TRANSITION_LABEL}",
                "publicationSelector": f"publication-owner={PUBLICATION_LABEL}",
                "ownerUniqueness": "at most one Job for each selector",
                "existingOwnerRule": "an existing Job owns its operation and must not be recreated",
                "suspendedMeaning": "spec.suspend=true means the owner exists but has not executed",
                "completedMeaning": "status.conditions[type=Complete,status=True] means execution completed",
                "transitionPrecondition": "worker transition may execute only after batch.state=drained",
            },
        ),
        _configmap(
            "publication-contract",
            {
                "preparationKey": REGISTRY_PREPARE_KEY,
                "releaseKey": REGISTRY_RELEASE_KEY,
                "compensationKey": REGISTRY_COMPENSATION_KEY,
                "closureKey": RECOVERY_AUDIT_KEY,
                "idempotency": "exactly-once-attempt per key",
                "releaseRequires": "catalog epoch 2, API v2, worker v2, credential generation 2, and one completed publication owner",
                "releasePayloadFields": "application,status,version,schema_epoch,migration_job_uid,publication_job_uid",
                "compensationPayloadFields": "application,status,compensates,migration_job_uid",
                "closurePayloadFields": "application,status,schema_epoch,api_version,worker_version,credential_generation,migration_job_uid,transition_job_uid,publication_job_uid",
                "historicalPreparationRule": "recovery never creates preparationKey when absent at the failure boundary",
                "boundaryEffectRule": "after failure create only a required compensation, missing release, and closure; no other external keys",
            },
        ),
        _configmap(
            "audit-contract",
            {
                "changeRecord": "change-record/orders-platform-v2.state=resolved",
                "ledgerRecord": "release-ledger/orders-platform-v2",
                "ledgerStatusValues": "aborted,deferred,active",
                "auditRecord": "recovery-audit/orders-platform-v2",
                "requiredFields": "status,schema_epoch,api_version,worker_version,credential_generation,migration_job_uid,transition_job_uid,publication_job_uid,preparation_resolution,release_resolution",
                "objectUidRule": "record exact metadata.uid whenever the matching Job exists, regardless of phase; use none only when no matching Job exists",
                "preparationResolutionRule": "not-created iff preparation absent; compensated iff preparation and compensation exist; released iff preparation and release exist",
                "releaseResolutionRule": "not-applicable iff the catalog remains epoch 1 after a failed migration; deferred iff epoch 2 is temporarily served through the active worker bridge and release preconditions are not yet legal; present iff release exists; missing is not a terminal value",
                "recordUpdateRule": "merge-patch only orders-platform-v2 fields and preserve all other fields",
                "statusValue": "complete",
            },
        ),
        _configmap(
            "database-catalog",
            {"schemaEpoch": "1", "migration": "none", "history": "epoch1"},
        ),
        _configmap(
            "schema-compatibility-bridge",
            {"lease": "active", "epoch": "2", "consumer": "orders-worker-v1"},
        ),
        _configmap(
            "worker-batch-state",
            {"state": "inflight", "replayable": "false", "batch": "batch-4821"},
        ),
        _configmap(
            "change-record",
            {
                "orders-platform-v2.state": "interrupted",
                "orders-platform-v2.failure": "HTTP connection lost before the change orchestration response",
            },
        ),
        _configmap(
            "release-ledger",
            {
                "orders-platform-v1.status": "active",
                "orders-platform-v2.status": "open",
                "orders-platform-v2.schema_epoch": "unknown",
            },
        ),
        _configmap(
            "recovery-audit",
            {
                "prior.version": "v1",
                "prior.status": "recorded",
                "orders-platform-v2.status": "pending",
                "orders-platform-v2.schema_epoch": "unknown",
                "orders-platform-v2.api_version": "unknown",
                "orders-platform-v2.worker_version": "unknown",
                "orders-platform-v2.credential_generation": "unknown",
                "orders-platform-v2.migration_job_uid": "unknown",
                "orders-platform-v2.transition_job_uid": "unknown",
                "orders-platform-v2.publication_job_uid": "unknown",
                "orders-platform-v2.preparation_resolution": "unknown",
                "orders-platform-v2.release_resolution": "unknown",
            },
        ),
        {
            "apiVersion": "v1",
            "kind": "Secret",
            "metadata": {
                "name": CURRENT_CREDENTIAL,
                "namespace": NAMESPACE,
                "labels": {"credential-generation": "1"},
            },
            "type": "Opaque",
            "stringData": {"token": "current-generation-one"},
        },
        {
            "apiVersion": "v1",
            "kind": "Secret",
            "metadata": {
                "name": NEXT_CREDENTIAL,
                "namespace": NAMESPACE,
                "labels": {"credential-generation": "2"},
            },
            "type": "Opaque",
            "stringData": {"token": "candidate-generation-two"},
        },
        {
            "apiVersion": "v1",
            "kind": "ServiceAccount",
            "metadata": {"name": "orders-runner", "namespace": NAMESPACE},
        },
        {
            "apiVersion": "rbac.authorization.k8s.io/v1",
            "kind": "Role",
            "metadata": {"name": "orders-observer", "namespace": NAMESPACE},
            "rules": [{"apiGroups": [""], "resources": ["configmaps"], "verbs": ["get"]}],
        },
        {
            "apiVersion": "rbac.authorization.k8s.io/v1",
            "kind": "RoleBinding",
            "metadata": {"name": "orders-observer", "namespace": NAMESPACE},
            "subjects": [{"kind": "ServiceAccount", "name": "orders-runner", "namespace": NAMESPACE}],
            "roleRef": {"apiGroup": "rbac.authorization.k8s.io", "kind": "Role", "name": "orders-observer"},
        },
        _deployment("api", "v1", 1),
        _deployment("api", "v2", 0),
        _deployment("worker", "v1", 1),
        _deployment("worker", "v2", 0),
        {
            "apiVersion": "v1",
            "kind": "Service",
            "metadata": {"name": API_SERVICE, "namespace": NAMESPACE},
            "spec": {
                "selector": {"app": "orders", "component": "api", "version": "v1"},
                "ports": [{"port": 80, "targetPort": 8080}],
            },
        },
        {
            "apiVersion": "batch/v1",
            "kind": "Job",
            "metadata": {"name": BACKUP_JOB, "namespace": NAMESPACE, "labels": {"app": "orders", "backup": "epoch1"}},
            "spec": {
                "backoffLimit": 0,
                "template": {
                    "metadata": {"labels": {"app": "orders", "backup": "epoch1"}},
                    "spec": {
                        "serviceAccountName": "orders-runner",
                        "restartPolicy": "Never",
                        "containers": [{"name": "backup", "image": WORKER_IMAGE, "imagePullPolicy": "Never", "command": ["python", "-c", "print('epoch1 backup complete')"]}],
                    },
                },
            },
        },
    )


def capture_interaction_prefix(api: KubernetesApi) -> dict[str, Any]:
    resources = (
        "configmaps",
        "secrets",
        "serviceaccounts",
        "roles",
        "rolebindings",
        "deployments",
        "services",
        "jobs",
    )
    objects = [
        _stable_migration_object(item)
        for resource in resources
        for item in api.list(resource, namespace=NAMESPACE)
    ]
    objects.sort(key=lambda item: (item["kind"], item["metadata"]["name"]))
    return {"namespace": NAMESPACE, "objects": objects}


def reset_interaction_prefix(api: KubernetesApi) -> dict[str, Any]:
    deletion = api.delete("namespace", NAMESPACE)
    if deletion:
        api.wait_deleted("namespace", NAMESPACE)
    manifests = interaction_prefix_manifests()
    writes = [api.apply(item) for item in manifests]
    for deployment in (API_V1, WORKER_V1):
        api.wait_condition(
            "deployment", deployment, condition="available", namespace=NAMESPACE
        )
    api.wait_condition("job", BACKUP_JOB, condition="complete", namespace=NAMESPACE)
    state = capture_interaction_prefix(api)
    fingerprint = sha256(
        json.dumps(state, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return {
        "scenario_id": SCENARIO_ID,
        "successful_writes": len(writes),
        "trace": [
            {
                "kind": "write",
                "status": "success",
                "tool": "apply_object",
                "arguments": {
                    "kind": manifest["kind"],
                    "name": manifest["metadata"].get("name"),
                    "generate_name": manifest["metadata"].get("generateName"),
                    "namespace": manifest["metadata"].get("namespace"),
                },
                "result": {
                    "kind": result["kind"],
                    "name": result["metadata"]["name"],
                    "namespace": result["metadata"].get("namespace"),
                },
            }
            for manifest, result in zip(manifests, writes, strict=True)
        ],
        "state": state,
        "fingerprint": fingerprint,
    }


__all__ = [
    "API_SERVICE",
    "API_V1",
    "API_V2",
    "BACKUP_JOB",
    "CONTRACT_CONFIGMAPS",
    "CURRENT_CREDENTIAL",
    "MIGRATION_LABEL",
    "NAMESPACE",
    "NEXT_CREDENTIAL",
    "PUBLICATION_LABEL",
    "RECOVERY_AUDIT_KEY",
    "REGISTRY_COMPENSATION_KEY",
    "REGISTRY_PREPARE_KEY",
    "REGISTRY_RELEASE_KEY",
    "REGISTRY_STABLE_KEY",
    "SCENARIO_ID",
    "TRANSITION_LABEL",
    "WORKER_V1",
    "WORKER_V2",
    "capture_interaction_prefix",
    "interaction_migration_job_manifest",
    "interaction_prefix_manifests",
    "publication_job_manifest",
    "reset_interaction_prefix",
    "transition_job_manifest",
]
