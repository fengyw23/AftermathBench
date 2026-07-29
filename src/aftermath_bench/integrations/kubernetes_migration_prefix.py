from __future__ import annotations

import json
from hashlib import sha256
from typing import Any

from .kubernetes_api import KubernetesApi
from .kubernetes_settlement_prefix import WORKER_IMAGE, _stable_object

SCENARIO_ID = "k8s-schema-rollout-dev-003"
NAMESPACE = "aftermath-migration"
STABLE_DEPLOYMENT = "orders-v1"
CANDIDATE_DEPLOYMENT = "orders-v2"
SERVICE = "orders"
BACKUP_JOB = "orders-backup-epoch1"
MIGRATION_LABEL = "orders-v2"
REGISTRY_STABLE_KEY = "release:orders-v1"
REGISTRY_PREPARE_KEY = "prepare:orders-v2"
REGISTRY_RELEASE_KEY = "release:orders-v2"
REGISTRY_COMPENSATION_KEY = "compensate:prepare:orders-v2"
RECOVERY_AUDIT_KEY = "audit:recovery:orders-v2"


def _stable_migration_object(document: dict[str, Any]) -> dict[str, Any]:
    """Project authored state while excluding API-server allocations."""
    projected = _stable_object(document)
    if document.get("kind") == "Service":
        for field in (
            "clusterIP",
            "clusterIPs",
            "healthCheckNodePort",
            "ipFamilies",
            "ipFamilyPolicy",
        ):
            projected.get("spec", {}).pop(field, None)
    return projected


def _deployment(name: str, version: str, replicas: int) -> dict[str, Any]:
    return {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {
            "name": name,
            "namespace": NAMESPACE,
            "labels": {"app": "orders", "version": version},
        },
        "spec": {
            "replicas": replicas,
            "selector": {"matchLabels": {"app": "orders", "version": version}},
            "template": {
                "metadata": {"labels": {"app": "orders", "version": version}},
                "spec": {
                    "serviceAccountName": "orders-runner",
                    "containers": [
                        {
                            "name": "orders",
                            "image": WORKER_IMAGE,
                            "imagePullPolicy": "Never",
                            "command": [
                                "python",
                                "-c",
                                "import time; time.sleep(3600)",
                            ],
                            "env": [
                                {
                                    "name": "APP_VERSION",
                                    "value": version,
                                },
                                {
                                    "name": "DB_TOKEN",
                                    "valueFrom": {
                                        "secretKeyRef": {
                                            "name": f"orders-db-{version}",
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


def migration_job_manifest(*, failed: bool = False) -> dict[str, Any]:
    command = (
        "raise SystemExit('migration failed before schema commit')"
        if failed
        else "import json; print(json.dumps({'migration':'orders-v2','schema_epoch':'2','status':'committed'}))"
    )
    return {
        "apiVersion": "batch/v1",
        "kind": "Job",
        "metadata": {
            "generateName": "orders-schema-v2-",
            "namespace": NAMESPACE,
            "labels": {"app": "orders", "migration": MIGRATION_LABEL},
        },
        "spec": {
            "backoffLimit": 0,
            "template": {
                "metadata": {"labels": {"app": "orders", "migration": MIGRATION_LABEL}},
                "spec": {
                    "serviceAccountName": "orders-runner",
                    "restartPolicy": "Never",
                    "containers": [
                        {
                            "name": "migration",
                            "image": WORKER_IMAGE,
                            "imagePullPolicy": "Never",
                            "command": ["python", "-c", command],
                        }
                    ],
                },
            },
        },
    }


def prefix_manifests() -> tuple[dict[str, Any], ...]:
    return (
        {"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": NAMESPACE}},
        {
            "apiVersion": "v1",
            "kind": "ConfigMap",
            "metadata": {"name": "recovery-policy", "namespace": NAMESPACE},
            "data": {
                "changeWindow": "closed",
                "epoch1Action": "rollback_to_stable",
                "epoch1WithEscapedPreparationAction": "compensate_external_effect",
                "epoch2BeforeCutoverAction": "forward_complete",
                "epoch2AfterPublishedCutoverAction": "repair_downstream_only",
                "downMigrationAllowed": "false",
                "abortCandidateResources": ("deployment/orders-v2,secret/orders-db-v2"),
                "failedMigrationEvidence": "preserve",
                "committedMigrationEvidence": "preserve",
                "forwardStableCapacity": "deployment/orders-v1=0",
                "requiredLedger": "release-ledger/orders-v2.status",
                "requiredAudit": "recovery-audit/orders-v2",
                "requiredRecoveryEvent": RECOVERY_AUDIT_KEY,
                "preparationCompensationEvent": REGISTRY_COMPENSATION_KEY,
                "releasePublicationEvent": REGISTRY_RELEASE_KEY,
            },
        },
        {
            "apiVersion": "v1",
            "kind": "ConfigMap",
            "metadata": {"name": "database-catalog", "namespace": NAMESPACE},
            "data": {"schemaEpoch": "1", "migration": "none", "history": "epoch1"},
        },
        {
            "apiVersion": "v1",
            "kind": "ConfigMap",
            "metadata": {"name": "release-ledger", "namespace": NAMESPACE},
            "data": {"orders-v1.status": "active", "orders-v2.status": "pending"},
        },
        {
            "apiVersion": "v1",
            "kind": "ConfigMap",
            "metadata": {"name": "recovery-audit", "namespace": NAMESPACE},
            "data": {"prior.version": "v1", "prior.status": "recorded"},
        },
        {
            "apiVersion": "v1",
            "kind": "Secret",
            "metadata": {"name": "orders-db-v1", "namespace": NAMESPACE},
            "type": "Opaque",
            "stringData": {"token": "stable-token"},
        },
        {
            "apiVersion": "v1",
            "kind": "Secret",
            "metadata": {"name": "orders-db-v2", "namespace": NAMESPACE},
            "type": "Opaque",
            "stringData": {"token": "candidate-token"},
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
            "rules": [
                {"apiGroups": [""], "resources": ["configmaps"], "verbs": ["get"]}
            ],
        },
        {
            "apiVersion": "rbac.authorization.k8s.io/v1",
            "kind": "RoleBinding",
            "metadata": {"name": "orders-observer", "namespace": NAMESPACE},
            "subjects": [
                {
                    "kind": "ServiceAccount",
                    "name": "orders-runner",
                    "namespace": NAMESPACE,
                }
            ],
            "roleRef": {
                "apiGroup": "rbac.authorization.k8s.io",
                "kind": "Role",
                "name": "orders-observer",
            },
        },
        _deployment(STABLE_DEPLOYMENT, "v1", 1),
        _deployment(CANDIDATE_DEPLOYMENT, "v2", 0),
        {
            "apiVersion": "v1",
            "kind": "Service",
            "metadata": {"name": SERVICE, "namespace": NAMESPACE},
            "spec": {
                "selector": {"app": "orders", "version": "v1"},
                "ports": [{"port": 80, "targetPort": 8080}],
            },
        },
        {
            "apiVersion": "batch/v1",
            "kind": "CronJob",
            "metadata": {"name": "nightly-report", "namespace": NAMESPACE},
            "spec": {
                "schedule": "0 1 * * *",
                "suspend": True,
                "jobTemplate": {"spec": migration_job_manifest()["spec"]},
            },
        },
        {
            "apiVersion": "batch/v1",
            "kind": "Job",
            "metadata": {
                "name": BACKUP_JOB,
                "namespace": NAMESPACE,
                "labels": {"app": "orders", "backup": "epoch1"},
            },
            "spec": {
                "backoffLimit": 0,
                "template": {
                    "metadata": {"labels": {"app": "orders", "backup": "epoch1"}},
                    "spec": {
                        "serviceAccountName": "orders-runner",
                        "restartPolicy": "Never",
                        "containers": [
                            {
                                "name": "backup",
                                "image": WORKER_IMAGE,
                                "imagePullPolicy": "Never",
                                "command": [
                                    "python",
                                    "-c",
                                    "print('backup epoch1 complete')",
                                ],
                            }
                        ],
                    },
                },
            },
        },
    )


def capture_prefix(api: KubernetesApi) -> dict[str, Any]:
    resources = (
        "configmaps",
        "secrets",
        "serviceaccounts",
        "roles",
        "rolebindings",
        "deployments",
        "services",
        "cronjobs",
        "jobs",
    )
    objects = [
        _stable_migration_object(item)
        for resource in resources
        for item in api.list(resource, namespace=NAMESPACE)
    ]
    objects.sort(key=lambda item: (item["kind"], item["metadata"]["name"]))
    return {"namespace": NAMESPACE, "objects": objects}


def reset_prefix(api: KubernetesApi) -> dict[str, Any]:
    deletion = api.delete("namespace", NAMESPACE)
    if deletion:
        api.wait_deleted("namespace", NAMESPACE)
    manifests = prefix_manifests()
    writes = [api.apply(item) for item in manifests]
    api.wait_condition(
        "deployment", STABLE_DEPLOYMENT, condition="available", namespace=NAMESPACE
    )
    api.wait_condition("job", BACKUP_JOB, condition="complete", namespace=NAMESPACE)
    state = capture_prefix(api)
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
