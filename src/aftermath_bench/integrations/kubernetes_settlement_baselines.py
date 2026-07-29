from __future__ import annotations

import json
from typing import Any

from .kubernetes_settlement_prefix import (
    NAMESPACE,
    PRIOR_BATCH,
    SETTLEMENT_TAINT_KEY,
    TARGET_AMOUNT,
    TARGET_BATCH,
    TARGET_RECEIPT_SHA,
    settlement_job_manifest,
)
from .kubernetes_settlement_recovery import (
    KubernetesSettlementEnvironment,
    reference_kubernetes_settlement_recovery,
)


SETTLEMENT_BASELINES = (
    "no_op",
    "blind_retry",
    "assume_committed",
    "repair_failed_record_only",
    "all_rollback",
    "deliver_immediately",
    "compact_state_tree",
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


def _job_only(
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
    nodes = _call(
        environment,
        "list_objects",
        resource="nodes",
        cluster_scoped=True,
    )
    if blindly_create:
        job = _call(
            environment,
            "create_object",
            manifest=settlement_job_manifest(),
        )
    elif not jobs:
        if assume_present:
            return None
        job = _call(
            environment,
            "create_object",
            manifest=settlement_job_manifest(),
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
    for node in nodes:
        if any(
            taint.get("key") == SETTLEMENT_TAINT_KEY
            for taint in node.get("spec", {}).get("taints", [])
        ):
            _call(
                environment,
                "remove_node_taint",
                node=str(node["metadata"]["name"]),
                key=SETTLEMENT_TAINT_KEY,
            )
    _call(environment, "wait_for_job", job=name, timeout="180s")
    return job


def _fixed_downstream(
    environment: KubernetesSettlementEnvironment,
    job: dict[str, Any],
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
            "data": {
                "batch": TARGET_BATCH,
                "amount": TARGET_AMOUNT,
                "receipt_sha256": receipt["receipt_sha256"],
                "status": "approved",
            },
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


def run_kubernetes_settlement_baseline(
    environment: KubernetesSettlementEnvironment,
    baseline: str,
) -> tuple[dict[str, Any], ...]:
    if baseline not in SETTLEMENT_BASELINES:
        raise ValueError(f"unknown settlement baseline: {baseline}")
    if baseline == "no_op":
        return environment.event_log()
    if baseline == "compact_state_tree":
        return reference_kubernetes_settlement_recovery(environment)
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
        _call(
            environment,
            "delete_object",
            resource="job",
            name=PRIOR_BATCH,
        )
        return environment.event_log()
    if baseline == "deliver_immediately":
        _call(
            environment,
            "post_external_event",
            idempotency_key=TARGET_BATCH,
            payload={
                "batch": TARGET_BATCH,
                "amount": TARGET_AMOUNT,
                "receipt_sha256": TARGET_RECEIPT_SHA,
            },
        )
        return reference_kubernetes_settlement_recovery(environment)

    job = _job_only(
        environment,
        blindly_create=baseline == "blind_retry",
        assume_present=baseline == "assume_committed",
    )
    if baseline == "repair_failed_record_only" or job is None:
        return environment.event_log()
    _fixed_downstream(environment, job)
    return environment.event_log()
