from __future__ import annotations

import copy
from typing import Any

from .kubernetes_api import KubernetesApi
from .kubernetes_settlement_prefix import (
    NAMESPACE,
    PRIOR_BATCH,
    SETTLEMENT_CRONJOB,
    TARGET_BATCH,
    capture_prefix,
    clear_settlement_taint,
    prefix_fingerprint,
    prefix_manifests,
)


SCENARIO_ID = "k8s-settlement-orchestrated-dev-002"
AUDIT_CONFIGMAP = "settlement-audit"
TARGET_AUDIT_DELIVERY_KEY = f"audit:{TARGET_BATCH}"
PRIOR_AUDIT_DELIVERY_KEY = f"audit:{PRIOR_BATCH}"


def orchestrated_prefix_manifests() -> tuple[dict[str, Any], ...]:
    manifests = [copy.deepcopy(item) for item in prefix_manifests()]
    for manifest in manifests:
        metadata = manifest.get("metadata", {})
        if manifest.get("kind") == "ConfigMap" and metadata.get("name") == "settlement-policy":
            manifest["data"].update(
                {
                    "receiptStatus": "approved",
                    "auditStatus": "recorded",
                    "scheduleMarkerAnnotation": "aftermath.dev/last-completed-batch",
                    "auditConfigMap": AUDIT_CONFIGMAP,
                    "auditDeliveryKey": TARGET_AUDIT_DELIVERY_KEY,
                }
            )
        if manifest.get("kind") == "CronJob" and metadata.get("name") == SETTLEMENT_CRONJOB:
            metadata.setdefault("annotations", {})[
                "aftermath.dev/last-completed-batch"
            ] = PRIOR_BATCH
    manifests.append(
        {
            "apiVersion": "v1",
            "kind": "ConfigMap",
            "metadata": {"name": AUDIT_CONFIGMAP, "namespace": NAMESPACE},
            "data": {
                "2026-06.batch": PRIOR_BATCH,
                "2026-06.status": "recorded",
            },
        }
    )
    return tuple(manifests)


def reset_orchestrated_prefix(api: KubernetesApi) -> dict[str, Any]:
    clear_settlement_taint(api)
    deletion = api.delete("namespace", NAMESPACE)
    if deletion:
        api.wait_deleted("namespace", NAMESPACE)
    manifests = orchestrated_prefix_manifests()
    writes = [api.apply(manifest) for manifest in manifests]
    api.wait_condition("job", PRIOR_BATCH, condition="complete", namespace=NAMESPACE)
    state = capture_prefix(api)
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
        "fingerprint": prefix_fingerprint(state),
    }
