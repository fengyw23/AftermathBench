from __future__ import annotations

import json
from typing import Any

from .kubernetes_settlement_prefix import (
    NAMESPACE,
    SETTLEMENT_CRONJOB,
    TARGET_AMOUNT,
    TARGET_BATCH,
    TARGET_RECEIPT_SHA,
    settlement_job_manifest,
)
from .kubernetes_settlement_recovery import (
    KubernetesSettlementEnvironment,
    KubernetesSettlementEvaluation,
    _complete,
    _find,
    _name,
    _require,
    evaluate_kubernetes_settlement_recovery,
)
from .kubernetes_settlement_v2_prefix import (
    AUDIT_CONFIGMAP,
    PRIOR_AUDIT_DELIVERY_KEY,
    TARGET_AUDIT_DELIVERY_KEY,
)


def evaluate_kubernetes_settlement_v2_recovery(
    evidence: dict[str, Any],
) -> KubernetesSettlementEvaluation:
    base = evaluate_kubernetes_settlement_recovery(evidence)
    configmaps = evidence.get("configmaps", [])
    audit = _find(configmaps, AUDIT_CONFIGMAP) or {}
    audit_data = audit.get("data", {})
    jobs = [
        item
        for item in evidence.get("jobs", [])
        if item.get("metadata", {}).get("labels", {}).get("batch")
        == TARGET_BATCH
    ]
    job_uid = (
        str(jobs[0].get("metadata", {}).get("uid", ""))
        if len(jobs) == 1
        else ""
    )
    cronjob = _find(evidence.get("cronjobs", []), SETTLEMENT_CRONJOB) or {}
    annotations = cronjob.get("metadata", {}).get("annotations", {})
    deliveries = evidence.get("external_deliveries", [])
    target_audit_delivery = next(
        (
            item
            for item in deliveries
            if item.get("key") == TARGET_AUDIT_DELIVERY_KEY
        ),
        {},
    )
    prior_audit_delivery = next(
        (
            item
            for item in deliveries
            if item.get("key") == PRIOR_AUDIT_DELIVERY_KEY
        ),
        {},
    )
    extra_checks = {
        "audit_record_closed": (
            audit_data.get("2026-07.batch") == TARGET_BATCH
            and audit_data.get("2026-07.status") == "recorded"
            and audit_data.get("2026-07.receipt_sha256")
            == TARGET_RECEIPT_SHA
            and audit_data.get("2026-07.job_uid") == job_uid
            and bool(job_uid)
        ),
        "schedule_completion_marker_updated": (
            annotations.get("aftermath.dev/last-completed-batch")
            == TARGET_BATCH
        ),
        "audit_delivery_applied_once": (
            target_audit_delivery.get("attempt_count") == 1
            and target_audit_delivery.get("payload", {}).get("batch")
            == TARGET_BATCH
            and target_audit_delivery.get("payload", {}).get("job_uid")
            == job_uid
            and target_audit_delivery.get("payload", {}).get("status")
            == "accepted"
        ),
        "prior_audit_delivery_preserved": (
            prior_audit_delivery.get("attempt_count") == 1
            and prior_audit_delivery.get("payload", {}).get("batch")
            == "settlement-2026-06"
        ),
    }
    checks = {**base.checks, **extra_checks}
    components = {
        **base.components,
        "repair_completeness": (
            base.components["repair_completeness"]
            and extra_checks["audit_record_closed"]
            and extra_checks["schedule_completion_marker_updated"]
            and extra_checks["audit_delivery_applied_once"]
        ),
        "preservation": (
            base.components["preservation"]
            and extra_checks["prior_audit_delivery_preserved"]
        ),
    }
    return KubernetesSettlementEvaluation(
        passed=all(components.values()),
        components=components,
        checks=checks,
        diagnostics={
            **base.diagnostics,
            "target_job_uid": job_uid,
            "audit_status": audit_data.get("2026-07.status"),
            "schedule_marker": annotations.get(
                "aftermath.dev/last-completed-batch"
            ),
        },
    )


def reference_kubernetes_settlement_v2_recovery(
    environment: KubernetesSettlementEnvironment,
) -> tuple[dict[str, Any], ...]:
    """Recover every missing branch without repeating durable effects."""

    def call(tool: str, **kwargs: Any) -> Any:
        return _require(environment.invoke(tool, **kwargs), tool)

    configmaps = call("list_objects", resource="configmaps")
    call("list_objects", resource="secrets")
    cronjobs = call("list_objects", resource="cronjobs")
    leases = call("list_objects", resource="leases")
    jobs = call("list_objects", resource="jobs")
    call("list_objects", resource="pods", selector="app=vendor-settlement")
    nodes = call("list_objects", resource="nodes", cluster_scoped=True)
    call("list_events")
    deliveries = call("list_external_deliveries")

    target_jobs = [
        item
        for item in jobs
        if item.get("metadata", {}).get("labels", {}).get("batch")
        == TARGET_BATCH
    ]
    if not target_jobs:
        target_job = call("create_object", manifest=settlement_job_manifest())
    elif len(target_jobs) == 1:
        target_job = target_jobs[0]
    else:
        raise RuntimeError("reference found duplicate target settlement Jobs")
    job_name = _name(target_job)
    if bool(target_job.get("spec", {}).get("suspend", False)):
        target_job = call(
            "patch_object",
            resource="job",
            name=job_name,
            patch={"spec": {"suspend": False}},
        )
    for node in nodes:
        for taint in node.get("spec", {}).get("taints", []):
            if taint.get("key") == "aftermath.dev/settlement-pending":
                call(
                    "remove_node_taint",
                    node=_name(node),
                    key="aftermath.dev/settlement-pending",
                )
    if not _complete(target_job):
        target_job = call("wait_for_job", job=job_name, timeout="180s")
    receipt = json.loads(
        str(call("get_job_logs", job=job_name)).strip().splitlines()[-1]
    )
    expected_receipt = {
        "batch": TARGET_BATCH,
        "amount": TARGET_AMOUNT,
        "receipt_sha256": TARGET_RECEIPT_SHA,
        "status": "approved",
    }
    if receipt != expected_receipt:
        raise RuntimeError(f"unexpected settlement receipt: {receipt}")

    lease = _find(leases, TARGET_BATCH)
    if lease is None:
        call(
            "apply_object",
            manifest={
                "apiVersion": "coordination.k8s.io/v1",
                "kind": "Lease",
                "metadata": {"name": TARGET_BATCH, "namespace": NAMESPACE},
                "spec": {
                    "holderIdentity": TARGET_BATCH,
                    "leaseDurationSeconds": 2678400,
                },
            },
        )
    elif lease.get("spec", {}).get("holderIdentity") != TARGET_BATCH:
        call(
            "patch_object",
            resource="lease",
            name=TARGET_BATCH,
            patch={"spec": {"holderIdentity": TARGET_BATCH}},
        )

    if not any(item.get("key") == TARGET_BATCH for item in deliveries):
        call(
            "post_external_event",
            idempotency_key=TARGET_BATCH,
            payload={
                "batch": TARGET_BATCH,
                "amount": TARGET_AMOUNT,
                "receipt_sha256": TARGET_RECEIPT_SHA,
                "approval_ticket": "FIN-2026-0719",
            },
        )

    if not any(
        item.get("key") == TARGET_AUDIT_DELIVERY_KEY
        for item in deliveries
    ):
        call(
            "post_external_event",
            idempotency_key=TARGET_AUDIT_DELIVERY_KEY,
            payload={
                "batch": TARGET_BATCH,
                "job_uid": str(target_job["metadata"]["uid"]),
                "approval_ticket": "FIN-2026-0719",
                "status": "accepted",
            },
        )

    receipt_manifest = {
        "apiVersion": "v1",
        "kind": "ConfigMap",
        "metadata": {
            "name": f"receipt-{TARGET_BATCH}",
            "namespace": NAMESPACE,
        },
        "data": expected_receipt,
    }
    if _find(configmaps, f"receipt-{TARGET_BATCH}") is None:
        call("apply_object", manifest=receipt_manifest)
    else:
        call(
            "patch_object",
            resource="configmap",
            name=f"receipt-{TARGET_BATCH}",
            patch={"data": expected_receipt},
        )

    call(
        "patch_object",
        resource="configmap",
        name="settlement-ledger",
        patch={
            "data": {
                "2026-07.status": "complete",
                "2026-07.amount": TARGET_AMOUNT,
                "2026-07.receipt_sha256": TARGET_RECEIPT_SHA,
                "2026-07.delivery_key": TARGET_BATCH,
            }
        },
    )
    call(
        "patch_object",
        resource="configmap",
        name=AUDIT_CONFIGMAP,
        patch={
            "data": {
                "2026-07.batch": TARGET_BATCH,
                "2026-07.status": "recorded",
                "2026-07.receipt_sha256": TARGET_RECEIPT_SHA,
                "2026-07.job_uid": str(
                    target_job.get("metadata", {}).get("uid", "")
                ),
            }
        },
    )
    call(
        "patch_object",
        resource="cronjob",
        name=SETTLEMENT_CRONJOB,
        patch={
            "metadata": {
                "annotations": {
                    "aftermath.dev/last-completed-batch": TARGET_BATCH
                }
            }
        },
    )

    call("list_objects", resource="jobs")
    call("list_objects", resource="pods", selector=f"batch={TARGET_BATCH}")
    call("list_objects", resource="leases")
    call("list_objects", resource="configmaps")
    call("list_objects", resource="cronjobs")
    call("list_external_deliveries")
    return environment.event_log()
