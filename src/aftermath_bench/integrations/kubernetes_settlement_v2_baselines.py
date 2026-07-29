from __future__ import annotations

import json
from typing import Any

from .kubernetes_settlement_prefix import (
    NAMESPACE,
    PRIOR_BATCH,
    SETTLEMENT_CRONJOB,
    TARGET_AMOUNT,
    TARGET_BATCH,
    TARGET_RECEIPT_SHA,
    settlement_job_manifest,
)
from .kubernetes_settlement_recovery import KubernetesSettlementEnvironment
from .kubernetes_settlement_v2_prefix import (
    AUDIT_CONFIGMAP,
    TARGET_AUDIT_DELIVERY_KEY,
)


SETTLEMENT_V2_BASELINES = (
    "no_op",
    "blind_retry",
    "assume_committed",
    "repair_failed_record_only",
    "all_rollback",
    "primary_record_tree",
    "unconditional_full_suffix",
)


def _call(
    environment: KubernetesSettlementEnvironment,
    tool: str,
    **kwargs: Any,
) -> Any:
    result = environment.invoke(tool, **kwargs)
    if not result.get("ok"):
        raise RuntimeError(f"baseline tool failed: {tool}: {result}")
    return result["result"]


def _recover_job(
    environment: KubernetesSettlementEnvironment,
    *,
    blindly_create: bool = False,
    assume_present: bool = False,
) -> dict[str, Any] | None:
    jobs = _call(
        environment,
        "list_objects",
        resource="jobs",
        selector=f"batch={TARGET_BATCH}",
    )
    if blindly_create:
        job = _call(
            environment, "create_object", manifest=settlement_job_manifest()
        )
    elif not jobs:
        if assume_present:
            return None
        job = _call(
            environment, "create_object", manifest=settlement_job_manifest()
        )
    elif len(jobs) == 1:
        job = jobs[0]
    else:
        return None
    name = str(job["metadata"]["name"])
    if job.get("spec", {}).get("suspend", False):
        _call(
            environment,
            "patch_object",
            resource="job",
            name=name,
            patch={"spec": {"suspend": False}},
        )
    _call(environment, "wait_for_job", job=name, timeout="180s")
    return _call(environment, "get_object", resource="job", name=name)


def _unconditional_suffix(
    environment: KubernetesSettlementEnvironment,
    job: dict[str, Any],
    *,
    include_audit_closure: bool,
) -> None:
    name = str(job["metadata"]["name"])
    receipt = json.loads(
        str(_call(environment, "get_job_logs", job=name)).strip().splitlines()[-1]
    )
    _call(
        environment,
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
    _call(
        environment,
        "post_external_event",
        idempotency_key=TARGET_BATCH,
        payload={
            "batch": TARGET_BATCH,
            "amount": TARGET_AMOUNT,
            "receipt_sha256": receipt["receipt_sha256"],
            "approval_ticket": "FIN-2026-0719",
        },
    )
    _call(
        environment,
        "apply_object",
        manifest={
            "apiVersion": "v1",
            "kind": "ConfigMap",
            "metadata": {
                "name": f"receipt-{TARGET_BATCH}",
                "namespace": NAMESPACE,
            },
            "data": receipt,
        },
    )
    _call(
        environment,
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
    if not include_audit_closure:
        return
    _call(
        environment,
        "post_external_event",
        idempotency_key=TARGET_AUDIT_DELIVERY_KEY,
        payload={
            "batch": TARGET_BATCH,
            "job_uid": str(job["metadata"]["uid"]),
            "approval_ticket": "FIN-2026-0719",
            "status": "accepted",
        },
    )
    _call(
        environment,
        "patch_object",
        resource="configmap",
        name=AUDIT_CONFIGMAP,
        patch={
            "data": {
                "2026-07.batch": TARGET_BATCH,
                "2026-07.status": "recorded",
                "2026-07.receipt_sha256": TARGET_RECEIPT_SHA,
                "2026-07.job_uid": str(job["metadata"]["uid"]),
            }
        },
    )
    _call(
        environment,
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


def run_kubernetes_settlement_v2_baseline(
    environment: KubernetesSettlementEnvironment,
    baseline: str,
) -> tuple[dict[str, Any], ...]:
    if baseline not in SETTLEMENT_V2_BASELINES:
        raise ValueError(f"unknown settlement v2 baseline: {baseline}")
    if baseline == "no_op":
        return environment.event_log()
    if baseline == "all_rollback":
        jobs = _call(
            environment,
            "list_objects",
            resource="jobs",
            selector=f"batch={TARGET_BATCH}",
        )
        for job in jobs:
            _call(
                environment,
                "delete_object",
                resource="job",
                name=str(job["metadata"]["name"]),
            )
        _call(environment, "delete_object", resource="job", name=PRIOR_BATCH)
        return environment.event_log()

    job = _recover_job(
        environment,
        blindly_create=baseline == "blind_retry",
        assume_present=baseline == "assume_committed",
    )
    if baseline == "repair_failed_record_only" or job is None:
        return environment.event_log()
    _unconditional_suffix(
        environment,
        job,
        include_audit_closure=baseline == "unconditional_full_suffix",
    )
    return environment.event_log()
