from __future__ import annotations

import json
from hashlib import sha256
from typing import Any

from .kubernetes_api import KubernetesApi
from .kubernetes_interaction_instance import (
    ACTIVE_KUBERNETES_INTERACTION_INSTANCE as INSTANCE,
)
from .kubernetes_migration_prefix import _stable_migration_object
from .kubernetes_settlement_prefix import WORKER_IMAGE

SCENARIO_ID = INSTANCE.scenario_id
NAMESPACE = INSTANCE.namespace
APPLICATION = INSTANCE.application
CURRENT_VERSION = INSTANCE.current_version
TARGET_VERSION = INSTANCE.target_version
CURRENT_EPOCH = INSTANCE.current_epoch
TARGET_EPOCH = INSTANCE.target_epoch
CURRENT_CREDENTIAL_GENERATION = INSTANCE.current_credential_generation
TARGET_CREDENTIAL_GENERATION = INSTANCE.target_credential_generation
CHANGE_ID = INSTANCE.target_change_id
PRIOR_CHANGE_ID = INSTANCE.current_change_id
API_SERVICE = INSTANCE.api_service
API_V1 = INSTANCE.current_api_deployment
API_V2 = INSTANCE.target_api_deployment
WORKER_V1 = INSTANCE.current_worker_deployment
WORKER_V2 = INSTANCE.target_worker_deployment
CURRENT_CREDENTIAL = INSTANCE.current_credential
NEXT_CREDENTIAL = INSTANCE.next_credential
BACKUP_JOB = INSTANCE.backup_job
MIGRATION_LABEL = INSTANCE.migration_label
MIGRATION_GENERATE_NAME = INSTANCE.migration_generate_name
TRANSITION_LABEL = INSTANCE.transition_label
PUBLICATION_LABEL = INSTANCE.publication_label
REGISTRY_STABLE_KEY = INSTANCE.registry_stable_key
REGISTRY_PREPARE_KEY = INSTANCE.registry_prepare_key
REGISTRY_RELEASE_KEY = INSTANCE.registry_release_key
REGISTRY_COMPENSATION_KEY = INSTANCE.registry_compensation_key
RECOVERY_AUDIT_KEY = INSTANCE.recovery_audit_key

CONTRACT_CONFIGMAPS = INSTANCE.contract_configmaps
SCHEMA_CONTRACT = INSTANCE.schema_contract
COMPATIBILITY_CONTRACT = INSTANCE.compatibility_contract
CREDENTIAL_CONTRACT = INSTANCE.credential_contract
CONTROLLER_CONTRACT = INSTANCE.controller_contract
PUBLICATION_CONTRACT = INSTANCE.publication_contract
AUDIT_CONTRACT = INSTANCE.audit_contract
DATABASE_CATALOG = INSTANCE.database_catalog
COMPATIBILITY_BRIDGE = INSTANCE.compatibility_bridge
BATCH_STATE = INSTANCE.batch_state
CHANGE_RECORD = INSTANCE.change_record
RELEASE_LEDGER = INSTANCE.release_ledger
RECOVERY_AUDIT = INSTANCE.recovery_audit
SERVICE_ACCOUNT = INSTANCE.service_account
OBSERVER_ROLE = INSTANCE.observer_role
BATCH_ID = INSTANCE.batch_id


def _configmap(name: str, data: dict[str, str]) -> dict[str, Any]:
    return {
        "apiVersion": "v1",
        "kind": "ConfigMap",
        "metadata": {"name": name, "namespace": NAMESPACE},
        "data": data,
    }


def _deployment(component: str, version: str, replicas: int) -> dict[str, Any]:
    names = {
        ("api", CURRENT_VERSION): API_V1,
        ("api", TARGET_VERSION): API_V2,
        ("worker", CURRENT_VERSION): WORKER_V1,
        ("worker", TARGET_VERSION): WORKER_V2,
    }
    name = names[(component, version)]
    labels = {"app": APPLICATION, "component": component, "version": version}
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
                    "serviceAccountName": SERVICE_ACCOUNT,
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
    labels = {"app": APPLICATION, label_key: label_value}
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
                    "serviceAccountName": SERVICE_ACCOUNT,
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
        f"raise SystemExit('{APPLICATION} migration failed before commit')"
        if failed
        else f"print('{APPLICATION} schema epoch {TARGET_EPOCH} committed')"
    )
    manifest = _job(
        name="placeholder",
        label_key="migration",
        label_value=MIGRATION_LABEL,
        command=command,
    )
    manifest["metadata"].pop("name")
    manifest["metadata"]["generateName"] = MIGRATION_GENERATE_NAME
    return manifest


def transition_job_manifest(*, suspend: bool = True) -> dict[str, Any]:
    return _job(
        name=INSTANCE.transition_job,
        label_key="transition-owner",
        label_value=TRANSITION_LABEL,
        command="print('worker transition controller observed state')",
        suspend=suspend,
    )


def publication_job_manifest(*, suspend: bool = True) -> dict[str, Any]:
    return _job(
        name=INSTANCE.publication_job,
        label_key="publication-owner",
        label_value=PUBLICATION_LABEL,
        command="print('release publication controller prepared payload')",
        suspend=suspend,
    )


def interaction_prefix_manifests() -> tuple[dict[str, Any], ...]:
    return (
        {"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": NAMESPACE}},
        _configmap(
            SCHEMA_CONTRACT,
            {
                "epochMonotonic": "true",
                "downMigrationAllowed": "false",
                "currentApiCompatibleEpochs": CURRENT_EPOCH,
                "targetApiCompatibleEpochs": TARGET_EPOCH,
                "currentWorkerCompatibleEpochs": f"{CURRENT_EPOCH}; epoch {TARGET_EPOCH} only under {COMPATIBILITY_CONTRACT}",
                "targetWorkerCompatibleEpochs": TARGET_EPOCH,
                "migrationEvidence": f"preserve every Job labeled migration={MIGRATION_LABEL}",
            },
        ),
        _configmap(
            COMPATIBILITY_CONTRACT,
            {
                "bridgeRecord": COMPATIBILITY_BRIDGE,
                "batchRecord": BATCH_STATE,
                "bridgeException": f"worker {CURRENT_VERSION} may coexist with epoch {TARGET_EPOCH} only when lease=active and batch.state=inflight",
                "expiredLease": f"cannot authorize a {CURRENT_VERSION} worker at epoch {TARGET_EPOCH}",
                "retirementRule": f"lease=retired after worker {TARGET_VERSION} is active and batch.state=drained",
                "nonReplayableBatch": f"must not stop worker {CURRENT_VERSION} while batch.state=inflight",
            },
        ),
        _configmap(
            CREDENTIAL_CONTRACT,
            {
                "sharedSecret": CURRENT_CREDENTIAL,
                "generationLabel": "metadata.labels.credential-generation",
                "currentVersionAllowedGenerations": CURRENT_CREDENTIAL_GENERATION,
                "targetVersionAllowedGenerations": f"{CURRENT_CREDENTIAL_GENERATION},{TARGET_CREDENTIAL_GENERATION}",
                "targetGeneration": TARGET_CREDENTIAL_GENERATION,
                "rotationGuard": f"generation {TARGET_CREDENTIAL_GENERATION} is legal only when no active {CURRENT_VERSION} consumer remains",
                "candidateSecret": NEXT_CREDENTIAL,
            },
        ),
        _configmap(
            CONTROLLER_CONTRACT,
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
            PUBLICATION_CONTRACT,
            {
                "preparationKey": REGISTRY_PREPARE_KEY,
                "releaseKey": REGISTRY_RELEASE_KEY,
                "compensationKey": REGISTRY_COMPENSATION_KEY,
                "closureKey": RECOVERY_AUDIT_KEY,
                "idempotency": "exactly-once-attempt per key",
                "releaseRequires": f"catalog epoch {TARGET_EPOCH}, API {TARGET_VERSION}, worker {TARGET_VERSION}, credential generation {TARGET_CREDENTIAL_GENERATION}, and one completed publication owner",
                "releasePayloadFields": "application,status,version,schema_epoch,migration_job_uid,publication_job_uid",
                "compensationPayloadFields": "application,status,compensates,migration_job_uid",
                "closurePayloadFields": "application,status,schema_epoch,api_version,worker_version,credential_generation,migration_job_uid,transition_job_uid,publication_job_uid",
                "historicalPreparationRule": "recovery never creates preparationKey when absent at the failure boundary",
                "boundaryEffectRule": "after failure create only a required compensation, missing release, and closure; no other external keys",
            },
        ),
        _configmap(
            AUDIT_CONTRACT,
            {
                "changeRecord": f"{CHANGE_RECORD}/{CHANGE_ID}.state=resolved",
                "ledgerRecord": f"{RELEASE_LEDGER}/{CHANGE_ID}",
                "ledgerStatusValues": "aborted,deferred,active",
                "auditRecord": f"{RECOVERY_AUDIT}/{CHANGE_ID}",
                "requiredFields": "status,schema_epoch,api_version,worker_version,credential_generation,migration_job_uid,transition_job_uid,publication_job_uid,preparation_resolution,release_resolution",
                "objectUidRule": "record exact metadata.uid whenever the matching Job exists, regardless of phase; use none only when no matching Job exists",
                "preparationResolutionRule": "not-created iff preparation absent; compensated iff preparation and compensation exist; released iff preparation and release exist",
                "releaseResolutionRule": f"not-applicable iff the catalog remains epoch {CURRENT_EPOCH} after a failed migration; deferred iff epoch {TARGET_EPOCH} is temporarily served through the active worker bridge and release preconditions are not yet legal; present iff release exists; missing is not a terminal value",
                "recordUpdateRule": f"merge-patch only {CHANGE_ID} fields and preserve all other fields",
                "statusValue": "complete",
            },
        ),
        _configmap(
            DATABASE_CATALOG,
            {"schemaEpoch": CURRENT_EPOCH, "migration": "none", "history": f"epoch{CURRENT_EPOCH}"},
        ),
        _configmap(
            COMPATIBILITY_BRIDGE,
            {"lease": "active", "epoch": TARGET_EPOCH, "consumer": WORKER_V1},
        ),
        _configmap(
            BATCH_STATE,
            {"state": "inflight", "replayable": "false", "batch": BATCH_ID},
        ),
        _configmap(
            CHANGE_RECORD,
            {
                f"{CHANGE_ID}.state": "interrupted",
                f"{CHANGE_ID}.failure": "HTTP connection lost before the change orchestration response",
            },
        ),
        _configmap(
            RELEASE_LEDGER,
            {
                f"{PRIOR_CHANGE_ID}.status": "active",
                f"{CHANGE_ID}.status": "open",
                f"{CHANGE_ID}.schema_epoch": "unknown",
            },
        ),
        _configmap(
            RECOVERY_AUDIT,
            {
                "prior.version": CURRENT_VERSION,
                "prior.status": "recorded",
                f"{CHANGE_ID}.status": "pending",
                f"{CHANGE_ID}.schema_epoch": "unknown",
                f"{CHANGE_ID}.api_version": "unknown",
                f"{CHANGE_ID}.worker_version": "unknown",
                f"{CHANGE_ID}.credential_generation": "unknown",
                f"{CHANGE_ID}.migration_job_uid": "unknown",
                f"{CHANGE_ID}.transition_job_uid": "unknown",
                f"{CHANGE_ID}.publication_job_uid": "unknown",
                f"{CHANGE_ID}.preparation_resolution": "unknown",
                f"{CHANGE_ID}.release_resolution": "unknown",
            },
        ),
        {
            "apiVersion": "v1",
            "kind": "Secret",
            "metadata": {
                "name": CURRENT_CREDENTIAL,
                "namespace": NAMESPACE,
                "labels": {"credential-generation": CURRENT_CREDENTIAL_GENERATION},
            },
            "type": "Opaque",
            "stringData": {"token": f"current-generation-{CURRENT_CREDENTIAL_GENERATION}"},
        },
        {
            "apiVersion": "v1",
            "kind": "Secret",
            "metadata": {
                "name": NEXT_CREDENTIAL,
                "namespace": NAMESPACE,
                "labels": {"credential-generation": TARGET_CREDENTIAL_GENERATION},
            },
            "type": "Opaque",
            "stringData": {"token": f"candidate-generation-{TARGET_CREDENTIAL_GENERATION}"},
        },
        {
            "apiVersion": "v1",
            "kind": "ServiceAccount",
            "metadata": {"name": SERVICE_ACCOUNT, "namespace": NAMESPACE},
        },
        {
            "apiVersion": "rbac.authorization.k8s.io/v1",
            "kind": "Role",
            "metadata": {"name": OBSERVER_ROLE, "namespace": NAMESPACE},
            "rules": [{"apiGroups": [""], "resources": ["configmaps"], "verbs": ["get"]}],
        },
        {
            "apiVersion": "rbac.authorization.k8s.io/v1",
            "kind": "RoleBinding",
            "metadata": {"name": OBSERVER_ROLE, "namespace": NAMESPACE},
            "subjects": [{"kind": "ServiceAccount", "name": SERVICE_ACCOUNT, "namespace": NAMESPACE}],
            "roleRef": {"apiGroup": "rbac.authorization.k8s.io", "kind": "Role", "name": OBSERVER_ROLE},
        },
        _deployment("api", CURRENT_VERSION, 1),
        _deployment("api", TARGET_VERSION, 0),
        _deployment("worker", CURRENT_VERSION, 1),
        _deployment("worker", TARGET_VERSION, 0),
        {
            "apiVersion": "v1",
            "kind": "Service",
            "metadata": {"name": API_SERVICE, "namespace": NAMESPACE},
            "spec": {
                "selector": {"app": APPLICATION, "component": "api", "version": CURRENT_VERSION},
                "ports": [{"port": 80, "targetPort": 8080}],
            },
        },
        {
            "apiVersion": "batch/v1",
            "kind": "Job",
            "metadata": {"name": BACKUP_JOB, "namespace": NAMESPACE, "labels": {"app": APPLICATION, "backup": f"epoch{CURRENT_EPOCH}"}},
            "spec": {
                "backoffLimit": 0,
                "template": {
                    "metadata": {"labels": {"app": APPLICATION, "backup": f"epoch{CURRENT_EPOCH}"}},
                    "spec": {
                        "serviceAccountName": SERVICE_ACCOUNT,
                        "restartPolicy": "Never",
                        "containers": [{"name": "backup", "image": WORKER_IMAGE, "imagePullPolicy": "Never", "command": ["python", "-c", f"print('epoch{CURRENT_EPOCH} backup complete')"]}],
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
