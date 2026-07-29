from __future__ import annotations

import json
from copy import deepcopy
from hashlib import sha256
from typing import Any

from .kubernetes_api import KubernetesApi
from .kubernetes_migration_prefix import (
    BACKUP_JOB,
    CANDIDATE_DEPLOYMENT,
    MIGRATION_LABEL,
    NAMESPACE,
    RECOVERY_AUDIT_KEY,
    REGISTRY_COMPENSATION_KEY,
    REGISTRY_PREPARE_KEY,
    REGISTRY_RELEASE_KEY,
    REGISTRY_STABLE_KEY,
    SERVICE,
    STABLE_DEPLOYMENT,
    _stable_migration_object,
    migration_job_manifest,
)
from .kubernetes_migration_prefix import (
    prefix_manifests as migration_prefix_manifests,
)

SCENARIO_ID = "k8s-constraint-scope-dev-004"
CONTRACT_CONFIGMAPS = (
    "recovery-policy",
    "schema-contract",
    "serving-contract",
    "registry-contract",
    "audit-contract",
)


def _configmap(name: str, data: dict[str, str]) -> dict[str, Any]:
    return {
        "apiVersion": "v1",
        "kind": "ConfigMap",
        "metadata": {"name": name, "namespace": NAMESPACE},
        "data": data,
    }


def constraint_prefix_manifests() -> tuple[dict[str, Any], ...]:
    """Create the same native rollout, but expose constraints instead of answers."""
    manifests = [deepcopy(item) for item in migration_prefix_manifests()]
    manifests = [
        item
        for item in manifests
        if item.get("metadata", {}).get("name")
        not in {"recovery-policy", "release-ledger", "recovery-audit"}
    ]
    contracts = (
        _configmap(
            "recovery-policy",
            {
                "window": "closed",
                "newSchemaMutation": "forbidden",
                "failedCandidateCleanup": "allowed",
                "committedStateConvergence": "allowed",
                "evidenceRetention": "all migration and backup Jobs",
            },
        ),
        _configmap(
            "schema-contract",
            {
                "epochMonotonic": "true",
                "v1CompatibleEpochs": "1",
                "v2CompatibleEpochs": "2",
                "servingEpochMustEqualCatalog": "true",
                "downMigration": "forbidden",
            },
        ),
        _configmap(
            "serving-contract",
            {
                "activeService": SERVICE,
                "exactlyOneServingVersion": "true",
                "candidateSecret": "orders-db-v2",
                "removeUnusedCandidateResourcesBeforeCommit": "true",
                "retireV1CapacityAfterEpoch2Cutover": "true",
            },
        ),
        _configmap(
            "registry-contract",
            {
                "idempotency": "exactly-once-attempt",
                "preparationKey": REGISTRY_PREPARE_KEY,
                "preparationLifecycle": (
                    "pre-orchestration historical evidence; recovery must never "
                    "create preparationKey when it is absent at the failure boundary"
                ),
                "preparationResolution": "release publication or compensation",
                "preparationResolutionRule": (
                    "not-created iff preparationKey is absent; compensated iff "
                    "preparationKey and compensationKey are present; released iff "
                    "preparationKey and releaseKey are present"
                ),
                "compensationKey": REGISTRY_COMPENSATION_KEY,
                "compensationPayloadFields": (
                    "application,status,compensates,migration_job_uid"
                ),
                "releaseKey": REGISTRY_RELEASE_KEY,
                "releaseRequires": "catalog epoch 2 and Service version v2",
                "releasePayloadFields": (
                    "application,status,version,schema_epoch,migration_job_uid"
                ),
                "closureKey": RECOVERY_AUDIT_KEY,
                "newExternalEffectRule": (
                    "after the failure boundary create only a missing required "
                    "releaseKey, a required compensationKey, and closureKey; "
                    "all other new external keys are forbidden"
                ),
            },
        ),
        _configmap(
            "audit-contract",
            {
                "record": "recovery-audit/orders-v2",
                "requiredFields": (
                    "status,schema_epoch,serving_version,migration_job_uid,"
                    "preparation_resolution,release_publication"
                ),
                "statusValue": "complete",
                "missingJobUidValue": "none",
                "migrationJobUidRule": (
                    "if any orders-v2 migration Job object exists, record its "
                    "exact metadata.uid regardless of whether the Job succeeded "
                    "or failed; use missingJobUidValue only when no such Job "
                    "object exists"
                ),
                "preparationResolutionValues": "not-created,compensated,released",
                "releasePublicationValues": "not-applicable,present",
                "releasePublicationRule": (
                    "present iff releaseKey exists; otherwise not-applicable"
                ),
                "ledgerRecord": "release-ledger/orders-v2",
                "ledgerRequiredFields": "status,schema_epoch,serving_version",
                "ledgerStatusValue": "closed",
                "recordUpdateRule": (
                    "merge-patch only the named orders-v2 fields and preserve every "
                    "pre-existing field not named by this contract"
                ),
                "closurePayloadFields": (
                    "application,status,schema_epoch,serving_version,"
                    "migration_job_uid"
                ),
                "changeRecord": "change-record/orders-v2.state=resolved",
            },
        ),
        _configmap(
            "change-record",
            {
                "orders-v2.state": "interrupted",
                "orders-v2.failure": (
                    "HTTP connection lost before the change orchestration response"
                ),
            },
        ),
        _configmap(
            "release-ledger",
            {
                "orders-v1.status": "active",
                "orders-v2.status": "open",
                "orders-v2.schema_epoch": "unknown",
                "orders-v2.serving_version": "unknown",
            },
        ),
        _configmap(
            "recovery-audit",
            {
                "prior.version": "v1",
                "prior.status": "recorded",
                "orders-v2.status": "pending",
                "orders-v2.schema_epoch": "unknown",
                "orders-v2.serving_version": "unknown",
                "orders-v2.migration_job_uid": "unknown",
                "orders-v2.preparation_resolution": "unknown",
                "orders-v2.release_publication": "unknown",
            },
        ),
    )
    # Keep contracts next to the catalog so their provenance is ordinary K8s state.
    insertion = next(
        index
        for index, item in enumerate(manifests)
        if item.get("metadata", {}).get("name") == "database-catalog"
    )
    manifests[insertion:insertion] = contracts
    return tuple(manifests)


def capture_constraint_prefix(api: KubernetesApi) -> dict[str, Any]:
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


def reset_constraint_prefix(api: KubernetesApi) -> dict[str, Any]:
    deletion = api.delete("namespace", NAMESPACE)
    if deletion:
        api.wait_deleted("namespace", NAMESPACE)
    manifests = constraint_prefix_manifests()
    writes = [api.apply(item) for item in manifests]
    api.wait_condition(
        "deployment", STABLE_DEPLOYMENT, condition="available", namespace=NAMESPACE
    )
    api.wait_condition("job", BACKUP_JOB, condition="complete", namespace=NAMESPACE)
    state = capture_constraint_prefix(api)
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
    "BACKUP_JOB",
    "CANDIDATE_DEPLOYMENT",
    "CONTRACT_CONFIGMAPS",
    "MIGRATION_LABEL",
    "NAMESPACE",
    "RECOVERY_AUDIT_KEY",
    "REGISTRY_COMPENSATION_KEY",
    "REGISTRY_PREPARE_KEY",
    "REGISTRY_RELEASE_KEY",
    "REGISTRY_STABLE_KEY",
    "SCENARIO_ID",
    "SERVICE",
    "STABLE_DEPLOYMENT",
    "capture_constraint_prefix",
    "constraint_prefix_manifests",
    "migration_job_manifest",
    "reset_constraint_prefix",
]
