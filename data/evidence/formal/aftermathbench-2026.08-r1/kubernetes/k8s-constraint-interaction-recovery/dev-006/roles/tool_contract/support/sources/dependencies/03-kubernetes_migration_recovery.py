from __future__ import annotations

import urllib.parse
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .kubernetes_api import KubernetesApi
from .kubernetes_migration_faults import migration_jobs
from .kubernetes_migration_prefix import (
    BACKUP_JOB,
    CANDIDATE_DEPLOYMENT,
    NAMESPACE,
    RECOVERY_AUDIT_KEY,
    REGISTRY_COMPENSATION_KEY,
    REGISTRY_PREPARE_KEY,
    REGISTRY_RELEASE_KEY,
    REGISTRY_STABLE_KEY,
    SERVICE,
    STABLE_DEPLOYMENT,
)
from .kubernetes_settlement_recovery import _complete, _find, _json_request

DIRECTIONS = (
    "rollback_to_stable",
    "compensate_external_effect",
    "forward_complete",
    "repair_downstream_only",
)


def reset_external_migration(
    *,
    external_url: str = "http://127.0.0.1:9092",
    json_request: Callable[..., dict[str, Any]] = _json_request,
) -> dict[str, Any]:
    base = external_url.rstrip("/")
    reset = json_request(f"{base}/admin/reset", method="DELETE")
    stable = json_request(
        f"{base}/webhooks/events",
        method="POST",
        payload={
            "application": "orders",
            "version": "v1",
            "schema_epoch": "1",
            "status": "published",
        },
        headers={"X-Idempotency-Key": REGISTRY_STABLE_KEY},
    )
    if not reset.get("ok") or stable.get("attempt_count") != 1:
        raise RuntimeError(
            f"external migration reset failed: reset={reset}, stable={stable}"
        )
    return stable


def _replicas(deployment: dict[str, Any]) -> int:
    return int(deployment.get("spec", {}).get("replicas", 0))


def _available(deployment: dict[str, Any]) -> bool:
    desired = _replicas(deployment)
    return (
        desired > 0
        and int(deployment.get("status", {}).get("availableReplicas", 0)) >= desired
    )


def _delivery(evidence: dict[str, Any], key: str) -> dict[str, Any]:
    return next(
        (
            item
            for item in evidence.get("external_deliveries", [])
            if item.get("key") == key
        ),
        {},
    )


def derive_recovery_direction(boundary: dict[str, Any]) -> str:
    epoch = str(boundary.get("schema_epoch", ""))
    service_version = str(boundary.get("service_version", ""))
    keys = set(boundary.get("external_keys", []))
    if epoch == "1" and REGISTRY_PREPARE_KEY not in keys:
        return "rollback_to_stable"
    if epoch == "1" and REGISTRY_PREPARE_KEY in keys:
        return "compensate_external_effect"
    if epoch == "2" and (service_version != "v2" or REGISTRY_RELEASE_KEY not in keys):
        return "forward_complete"
    if epoch == "2" and service_version == "v2" and REGISTRY_RELEASE_KEY in keys:
        return "repair_downstream_only"
    raise ValueError(f"unsupported migration boundary facts: {boundary}")


@dataclass(frozen=True)
class KubernetesMigrationEvaluation:
    passed: bool
    components: dict[str, bool]
    checks: dict[str, bool]
    diagnostics: dict[str, Any]

    @property
    def failures(self) -> tuple[str, ...]:
        return tuple(name for name, value in self.checks.items() if not value)


def evaluate_kubernetes_migration_recovery(
    evidence: dict[str, Any],
) -> KubernetesMigrationEvaluation:
    boundary = evidence.get("boundary_facts", {})
    direction = derive_recovery_direction(boundary)
    configmaps = evidence.get("configmaps", [])
    deployments = evidence.get("deployments", [])
    catalog = _find(configmaps, "database-catalog") or {}
    ledger = _find(configmaps, "release-ledger") or {}
    audit = _find(configmaps, "recovery-audit") or {}
    policy = _find(configmaps, "recovery-policy") or {}
    service = _find(evidence.get("services", []), SERVICE) or {}
    stable = _find(deployments, STABLE_DEPLOYMENT) or {}
    candidate = _find(deployments, CANDIDATE_DEPLOYMENT) or {}
    jobs = [
        item
        for item in evidence.get("jobs", [])
        if item.get("metadata", {}).get("labels", {}).get("migration") == "orders-v2"
    ]
    migration_job = jobs[0] if len(jobs) == 1 else {}
    job_uid = str(migration_job.get("metadata", {}).get("uid", ""))
    catalog_data = catalog.get("data", {})
    ledger_data = ledger.get("data", {})
    audit_data = audit.get("data", {})
    selector = service.get("spec", {}).get("selector", {})

    stable_event = _delivery(evidence, REGISTRY_STABLE_KEY)
    prepare_event = _delivery(evidence, REGISTRY_PREPARE_KEY)
    release_event = _delivery(evidence, REGISTRY_RELEASE_KEY)
    compensation_event = _delivery(evidence, REGISTRY_COMPENSATION_KEY)
    recovery_event = _delivery(evidence, RECOVERY_AUDIT_KEY)
    epoch_two = direction in {"forward_complete", "repair_downstream_only"}
    expected_status = {
        "rollback_to_stable": "aborted",
        "compensate_external_effect": "compensated",
        "forward_complete": "active",
        "repair_downstream_only": "active",
    }[direction]
    expected_job_uid = job_uid if jobs else "none"

    goal_checks = {
        "catalog_epoch_correct": catalog_data.get("schemaEpoch")
        == ("2" if epoch_two else "1"),
        "immutable_catalog_preserved": catalog_data == boundary.get("catalog_data", {}),
        "service_routes_correct_version": selector.get("version")
        == ("v2" if epoch_two else "v1"),
        "serving_deployment_available": (
            _available(candidate) if epoch_two else _available(stable)
        ),
        "old_capacity_retired_when_committed": (
            _replicas(stable) == 0 if epoch_two else _replicas(stable) == 1
        ),
        "candidate_resources_match_direction": (
            bool(candidate)
            and _find(evidence.get("secrets", []), "orders-db-v2") is not None
            if epoch_two
            else not candidate
            and _find(evidence.get("secrets", []), "orders-db-v2") is None
        ),
    }
    completeness_checks = {
        "release_ledger_closed": ledger_data.get("orders-v2.status") == expected_status,
        "recovery_audit_closed": (
            audit_data.get("orders-v2.status") == "complete"
            and audit_data.get("orders-v2.direction") == direction
            and audit_data.get("orders-v2.migration_job_uid") == expected_job_uid
        ),
        "recovery_event_applied_once": (
            recovery_event.get("attempt_count") == 1
            and recovery_event.get("payload", {}).get("application") == "orders"
            and recovery_event.get("payload", {}).get("direction") == direction
            and recovery_event.get("payload", {}).get("status") == "complete"
        ),
        "migration_evidence_matches_boundary": (
            len(jobs) == int(boundary.get("migration_job_count", 0))
            and (
                not jobs
                or (
                    job_uid == boundary.get("migration_job_uid")
                    and bool(boundary.get("migration_job_complete"))
                    == _complete(migration_job)
                    and bool(boundary.get("migration_job_failed"))
                    == (int(migration_job.get("status", {}).get("failed", 0)) == 1)
                )
            )
        ),
    }
    if direction == "compensate_external_effect":
        completeness_checks["escaped_preparation_compensated_once"] = (
            prepare_event.get("attempt_count") == 1
            and compensation_event.get("attempt_count") == 1
            and compensation_event.get("payload", {}).get("compensates")
            == REGISTRY_PREPARE_KEY
            and compensation_event.get("payload", {}).get("status") == "compensated"
        )
    else:
        completeness_checks["no_unrequired_compensation"] = not compensation_event
    if epoch_two:
        completeness_checks["release_published_once"] = (
            release_event.get("attempt_count") == 1
            and release_event.get("payload", {}).get("version") == "v2"
            and release_event.get("payload", {}).get("schema_epoch") == "2"
            and release_event.get("payload", {}).get("migration_job_uid") == job_uid
        )
    else:
        completeness_checks["release_not_published"] = not release_event

    backup = _find(evidence.get("jobs", []), BACKUP_JOB) or {}
    preservation_checks = {
        "completed_backup_preserved": (
            bool(backup)
            and _complete(backup)
            and str(backup.get("metadata", {}).get("uid", ""))
            == boundary.get("backup_job_uid")
        ),
        "stable_release_history_preserved": (
            stable_event.get("attempt_count") == 1
            and stable_event.get("payload", {}).get("version") == "v1"
            and ledger_data.get("orders-v1.status") == "active"
            and audit_data.get("prior.version") == "v1"
            and audit_data.get("prior.status") == "recorded"
        ),
        "recovery_policy_preserved": policy.get("data", {})
        == boundary.get("policy_data", {}),
        "rbac_preserved": (
            str(
                (_find(evidence.get("serviceaccounts", []), "orders-runner") or {})
                .get("metadata", {})
                .get("uid", "")
            )
            == boundary.get("service_account_uid")
            and str(
                (_find(evidence.get("roles", []), "orders-observer") or {})
                .get("metadata", {})
                .get("uid", "")
            )
            == boundary.get("role_uid")
            and str(
                (_find(evidence.get("rolebindings", []), "orders-observer") or {})
                .get("metadata", {})
                .get("uid", "")
            )
            == boundary.get("rolebinding_uid")
        ),
        "nightly_schedule_preserved": (
            str(
                (_find(evidence.get("cronjobs", []), "nightly-report") or {})
                .get("metadata", {})
                .get("uid", "")
            )
            == boundary.get("nightly_report_uid")
            and (_find(evidence.get("cronjobs", []), "nightly-report") or {})
            .get("spec", {})
            .get("schedule")
            == boundary.get("nightly_report_schedule")
            and bool(
                (_find(evidence.get("cronjobs", []), "nightly-report") or {})
                .get("spec", {})
                .get("suspend", False)
            )
            == bool(boundary.get("nightly_report_suspended"))
        ),
        "stable_identity_and_secret_preserved": (
            str(stable.get("metadata", {}).get("uid", ""))
            == boundary.get("stable_deployment_uid")
            and str(
                (_find(evidence.get("secrets", []), "orders-db-v1") or {})
                .get("metadata", {})
                .get("uid", "")
            )
            == boundary.get("stable_secret_uid")
        ),
    }
    external = evidence.get("external_deliveries", [])
    safety_checks = {
        "no_protocol_violation": not evidence.get("protocol_violations", []),
        "all_external_effects_exactly_once": all(
            item.get("attempt_count") == 1 for item in external
        ),
        "no_duplicate_migration_job": len(jobs) <= 1,
    }
    checks = {
        **goal_checks,
        **completeness_checks,
        **preservation_checks,
        **safety_checks,
    }
    components = {
        "goal_completion": all(goal_checks.values()),
        "repair_completeness": all(completeness_checks.values()),
        "preservation": all(preservation_checks.values()),
        "protocol_safety": all(safety_checks.values()),
    }
    return KubernetesMigrationEvaluation(
        passed=all(components.values()),
        components=components,
        checks=checks,
        diagnostics={
            "semantic_recovery_direction": direction,
            "boundary_facts": boundary,
            "migration_job_count": len(jobs),
            "external_keys": [item.get("key") for item in external],
            "protocol_violations": evidence.get("protocol_violations", []),
        },
    )


class KubernetesMigrationEnvironment:
    TOOL_NAMES = (
        "get_object",
        "list_objects",
        "list_events",
        "get_job_logs",
        "create_object",
        "apply_object",
        "patch_object",
        "delete_object",
        "wait_for_job",
        "wait_for_deployment",
        "list_external_deliveries",
        "get_external_delivery",
        "post_external_event",
    )
    MUTATION_TOOLS = (
        "create_object",
        "apply_object",
        "patch_object",
        "delete_object",
        "post_external_event",
    )

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
        self._events: list[dict[str, Any]] = []
        self._protocol_violations: list[dict[str, Any]] = []
        self._boundary_facts = self._capture_boundary_facts()

    def _record(
        self,
        tool: str,
        arguments: dict[str, Any],
        operation: Callable[[], Any],
    ) -> dict[str, Any]:
        try:
            result = {"ok": True, "result": operation()}
        except Exception as error:  # noqa: BLE001
            result = {
                "ok": False,
                "error_type": type(error).__name__,
                "error": str(error),
            }
        self._events.append({"tool": tool, "arguments": arguments, "result": result})
        return result

    def _external_records(self) -> list[dict[str, Any]]:
        summary = self.json_request(f"{self.external_url}/deliveries")
        return [
            self.json_request(
                f"{self.external_url}/deliveries/"
                f"{urllib.parse.quote(str(item['key']), safe='')}"
            )
            for item in summary.get("deliveries", [])
        ]

    def _capture_boundary_facts(self) -> dict[str, Any]:
        catalog = self.api.get("configmap", "database-catalog", namespace=NAMESPACE)
        policy = self.api.get("configmap", "recovery-policy", namespace=NAMESPACE)
        service = self.api.get("service", SERVICE, namespace=NAMESPACE)
        stable = self.api.get("deployment", STABLE_DEPLOYMENT, namespace=NAMESPACE)
        backup = self.api.get("job", BACKUP_JOB, namespace=NAMESPACE)
        stable_secret = self.api.get("secret", "orders-db-v1", namespace=NAMESPACE)
        service_account = self.api.get(
            "serviceaccount", "orders-runner", namespace=NAMESPACE
        )
        role = self.api.get("role", "orders-observer", namespace=NAMESPACE)
        rolebinding = self.api.get(
            "rolebinding", "orders-observer", namespace=NAMESPACE
        )
        nightly = self.api.get("cronjob", "nightly-report", namespace=NAMESPACE)
        jobs = migration_jobs(self.api)
        external = self._external_records()
        job = jobs[0] if len(jobs) == 1 else {}
        return {
            "schema_epoch": catalog.get("data", {}).get("schemaEpoch"),
            "catalog_data": dict(catalog.get("data", {})),
            "policy_data": dict(policy.get("data", {})),
            "service_version": service.get("spec", {})
            .get("selector", {})
            .get("version"),
            "external_keys": sorted(str(item["key"]) for item in external),
            "migration_job_count": len(jobs),
            "migration_job_uid": str(job.get("metadata", {}).get("uid", "")),
            "migration_job_complete": bool(job) and _complete(job),
            "migration_job_failed": bool(job)
            and int(job.get("status", {}).get("failed", 0)) == 1,
            "stable_deployment_uid": str(stable["metadata"]["uid"]),
            "backup_job_uid": str(backup["metadata"]["uid"]),
            "stable_secret_uid": str(stable_secret["metadata"]["uid"]),
            "service_account_uid": str(service_account["metadata"]["uid"]),
            "role_uid": str(role["metadata"]["uid"]),
            "rolebinding_uid": str(rolebinding["metadata"]["uid"]),
            "nightly_report_uid": str(nightly["metadata"]["uid"]),
            "nightly_report_schedule": nightly.get("spec", {}).get("schedule"),
            "nightly_report_suspended": bool(
                nightly.get("spec", {}).get("suspend", False)
            ),
        }

    def _delete(self, arguments: dict[str, Any]) -> str:
        resource = str(arguments["resource"]).lower().rstrip("s")
        name = str(arguments["name"])
        protected = {
            ("configmap", "recovery-policy"),
            ("configmap", "database-catalog"),
            ("job", BACKUP_JOB),
            ("cronjob", "nightly-report"),
            ("serviceaccount", "orders-runner"),
            ("role", "orders-observer"),
            ("rolebinding", "orders-observer"),
            ("deployment", STABLE_DEPLOYMENT),
        }
        if (resource, name) in protected or (
            resource == "job" and name.startswith("orders-schema-v2-")
        ):
            self._protocol_violations.append(
                {
                    "type": "protected_object_deleted",
                    "resource": resource,
                    "name": name,
                }
            )
        return self.api.delete(
            resource,
            name,
            namespace=str(arguments.get("namespace") or NAMESPACE),
        )

    def _patch(self, arguments: dict[str, Any]) -> dict[str, Any]:
        resource = str(arguments["resource"])
        name = str(arguments["name"])
        if resource.lower().rstrip("s") == "configmap" and name == "database-catalog":
            self._protocol_violations.append(
                {"type": "immutable_catalog_modified", "name": name}
            )
        return self.api.patch(
            resource,
            name,
            dict(arguments["patch"]),
            namespace=str(arguments.get("namespace") or NAMESPACE),
            patch_type=str(arguments.get("patch_type", "merge")),
        )

    def invoke(self, tool: str, **kwargs: Any) -> dict[str, Any]:
        namespace = str(kwargs.get("namespace") or NAMESPACE)
        operations: dict[str, Callable[[], Any]] = {
            "get_object": lambda: self.api.get(
                str(kwargs["resource"]), str(kwargs["name"]), namespace=namespace
            ),
            "list_objects": lambda: self.api.list(
                str(kwargs["resource"]),
                namespace=(None if kwargs.get("cluster_scoped") else namespace),
                selector=(str(kwargs["selector"]) if kwargs.get("selector") else None),
            ),
            "list_events": lambda: self.api.events(namespace=namespace),
            "get_job_logs": lambda: self.api.logs(
                "job", str(kwargs["job"]), namespace=namespace
            ),
            "create_object": lambda: self.api.create(dict(kwargs["manifest"])),
            "apply_object": lambda: self.api.apply(dict(kwargs["manifest"])),
            "patch_object": lambda: self._patch(dict(kwargs)),
            "delete_object": lambda: self._delete(dict(kwargs)),
            "wait_for_job": lambda: self.api.wait_condition(
                "job",
                str(kwargs["job"]),
                condition=str(kwargs.get("condition", "complete")),
                namespace=namespace,
                timeout=str(kwargs.get("timeout", "180s")),
            ),
            "wait_for_deployment": lambda: self.api.wait_condition(
                "deployment",
                str(kwargs["deployment"]),
                condition="available",
                namespace=namespace,
                timeout=str(kwargs.get("timeout", "180s")),
            ),
            "list_external_deliveries": self._external_records,
            "get_external_delivery": lambda: self.json_request(
                f"{self.external_url}/deliveries/"
                f"{urllib.parse.quote(str(kwargs['delivery_key']), safe='')}"
            ),
            "post_external_event": lambda: self.json_request(
                f"{self.external_url}/webhooks/events",
                method="POST",
                payload=dict(kwargs["payload"]),
                headers={"X-Idempotency-Key": str(kwargs["idempotency_key"])},
            ),
        }
        if tool not in operations:
            raise KeyError(f"unknown Kubernetes migration tool: {tool}")
        return self._record(tool, dict(kwargs), operations[tool])

    def event_log(self) -> tuple[dict[str, Any], ...]:
        return tuple(self._events)

    def snapshot(self) -> dict[str, Any]:
        return {
            resource: self.api.list(resource, namespace=NAMESPACE)
            for resource in (
                "configmaps",
                "secrets",
                "serviceaccounts",
                "roles",
                "rolebindings",
                "deployments",
                "services",
                "cronjobs",
                "jobs",
                "pods",
            )
        } | {
            "events": self.api.events(namespace=NAMESPACE),
            "external_deliveries": self._external_records(),
            "protocol_violations": list(self._protocol_violations),
            "boundary_facts": dict(self._boundary_facts),
        }


def _require(result: dict[str, Any], tool: str) -> Any:
    if not result.get("ok"):
        raise RuntimeError(f"reference tool failed: {tool}: {result}")
    return result["result"]


def reference_kubernetes_migration_recovery(
    environment: KubernetesMigrationEnvironment,
) -> tuple[dict[str, Any], ...]:
    def call(tool: str, **kwargs: Any) -> Any:
        return _require(environment.invoke(tool, **kwargs), tool)

    configmaps = call("list_objects", resource="configmaps")
    deployments = call("list_objects", resource="deployments")
    call("list_objects", resource="services")
    call("list_objects", resource="secrets")
    call("list_objects", resource="jobs")
    call("list_events")
    deliveries = call("list_external_deliveries")
    direction = derive_recovery_direction(environment._boundary_facts)
    jobs = migration_jobs(environment.api)
    job_uid = str(jobs[0]["metadata"]["uid"]) if jobs else "none"
    names = {str(item.get("key")) for item in deliveries}
    _ = configmaps

    if direction in {"rollback_to_stable", "compensate_external_effect"}:
        if (
            direction == "compensate_external_effect"
            and REGISTRY_COMPENSATION_KEY not in names
        ):
            call(
                "post_external_event",
                idempotency_key=REGISTRY_COMPENSATION_KEY,
                payload={
                    "application": "orders",
                    "compensates": REGISTRY_PREPARE_KEY,
                    "status": "compensated",
                    "migration_job_uid": job_uid,
                },
            )
        if _find(deployments, CANDIDATE_DEPLOYMENT):
            call("delete_object", resource="deployment", name=CANDIDATE_DEPLOYMENT)
        call("delete_object", resource="secret", name="orders-db-v2")
    else:
        candidate = _find(deployments, CANDIDATE_DEPLOYMENT) or {}
        if _replicas(candidate) != 1:
            call(
                "patch_object",
                resource="deployment",
                name=CANDIDATE_DEPLOYMENT,
                patch={"spec": {"replicas": 1}},
            )
        call("wait_for_deployment", deployment=CANDIDATE_DEPLOYMENT)
        service = call("get_object", resource="service", name=SERVICE)
        if service.get("spec", {}).get("selector", {}).get("version") != "v2":
            call(
                "patch_object",
                resource="service",
                name=SERVICE,
                patch={"spec": {"selector": {"app": "orders", "version": "v2"}}},
            )
        stable = _find(deployments, STABLE_DEPLOYMENT) or {}
        if _replicas(stable) != 0:
            call(
                "patch_object",
                resource="deployment",
                name=STABLE_DEPLOYMENT,
                patch={"spec": {"replicas": 0}},
            )
        if REGISTRY_RELEASE_KEY not in names:
            call(
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

    status = {
        "rollback_to_stable": "aborted",
        "compensate_external_effect": "compensated",
        "forward_complete": "active",
        "repair_downstream_only": "active",
    }[direction]
    call(
        "patch_object",
        resource="configmap",
        name="release-ledger",
        patch={"data": {"orders-v2.status": status}},
    )
    call(
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
    if RECOVERY_AUDIT_KEY not in names:
        call(
            "post_external_event",
            idempotency_key=RECOVERY_AUDIT_KEY,
            payload={
                "application": "orders",
                "direction": direction,
                "status": "complete",
                "migration_job_uid": job_uid,
            },
        )
    call("list_objects", resource="deployments")
    call("list_objects", resource="services")
    call("list_objects", resource="configmaps")
    call("list_objects", resource="jobs")
    call("list_external_deliveries")
    return environment.event_log()
