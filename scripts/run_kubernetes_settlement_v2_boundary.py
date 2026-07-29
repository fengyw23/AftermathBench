from __future__ import annotations

import argparse
import json
from pathlib import Path

from aftermath_bench.integrations.kubernetes_api import KubernetesApi
from aftermath_bench.integrations.kubernetes_settlement_prefix import (
    NAMESPACE,
    TARGET_BATCH,
)
from aftermath_bench.integrations.kubernetes_settlement_recovery import (
    _json_request,
    reset_external_settlement,
)
from aftermath_bench.integrations.kubernetes_settlement_v2_faults import (
    KUBERNETES_SETTLEMENT_V2_VARIANTS,
    SURFACE_ERROR,
    KubernetesSettlementV2FaultBoundary,
)
from aftermath_bench.integrations.kubernetes_settlement_v2_prefix import (
    PRIOR_AUDIT_DELIVERY_KEY,
    SCENARIO_ID,
    reset_orchestrated_prefix,
)
from aftermath_bench.integrations.kubernetes_stack import KubernetesStack


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--variant", choices=KUBERNETES_SETTLEMENT_V2_VARIANTS, required=True
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--prefix-output", type=Path)
    args = parser.parse_args()
    stack = KubernetesStack.from_repository()
    api = KubernetesApi(context=stack.context)
    prior_delivery = reset_external_settlement()
    prior_audit_delivery = _json_request(
        "http://127.0.0.1:9092/webhooks/events",
        method="POST",
        payload={
            "batch": "settlement-2026-06",
            "job_uid": "prior-job-settlement-2026-06",
            "approval_ticket": "FIN-2026-0618",
            "status": "accepted",
        },
        headers={"X-Idempotency-Key": PRIOR_AUDIT_DELIVERY_KEY},
    )
    prefix = reset_orchestrated_prefix(api)
    prefix["trace"].append(
        {
            "kind": "write",
            "status": "success",
            "tool": "post_external_event",
            "arguments": {"idempotency_key": "settlement-2026-06"},
            "result": prior_delivery,
        }
    )
    prefix["trace"].append(
        {
            "kind": "write",
            "status": "success",
            "tool": "post_external_event",
            "arguments": {"idempotency_key": PRIOR_AUDIT_DELIVERY_KEY},
            "result": prior_audit_delivery,
        }
    )
    if args.prefix_output:
        args.prefix_output.parent.mkdir(parents=True, exist_ok=True)
        args.prefix_output.write_text(
            json.dumps(prefix, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    boundary = KubernetesSettlementV2FaultBoundary(api)
    error = None
    try:
        boundary.trigger(args.variant)
    except ConnectionError as caught:
        error = str(caught)
    if error != SURFACE_ERROR:
        raise RuntimeError(f"boundary did not expose common error: {error!r}")

    jobs = api.list("jobs", namespace=NAMESPACE, selector=f"batch={TARGET_BATCH}")
    pods = api.list("pods", namespace=NAMESPACE, selector=f"batch={TARGET_BATCH}")
    configmaps = api.list("configmaps", namespace=NAMESPACE)
    leases = api.list("leases", namespace=NAMESPACE)
    payload = {
        "schema_version": "0.2",
        "scenario_id": SCENARIO_ID,
        "variant": args.variant,
        "surface_result": SURFACE_ERROR,
        "visible_failure": {"ok": False, "error": SURFACE_ERROR},
        "prefix_fingerprint": prefix["fingerprint"],
        "prefix_trace": prefix["trace"],
        "observed": {
            "target_job_count": len(jobs),
            "target_job_complete": (
                len(jobs) == 1
                and int(jobs[0].get("status", {}).get("succeeded", 0)) == 1
            ),
            "target_job_suspended": (
                len(jobs) == 1
                and bool(jobs[0].get("spec", {}).get("suspend", False))
            ),
            "target_lease_exists": any(
                item.get("metadata", {}).get("name") == TARGET_BATCH
                for item in leases
            ),
            "target_receipt_exists": any(
                item.get("metadata", {}).get("name")
                == f"receipt-{TARGET_BATCH}"
                for item in configmaps
            ),
        },
        "failure_boundary_evidence": {
            "jobs": jobs,
            "pods": pods,
            "nodes": api.list("nodes"),
            "leases": leases,
            "configmaps": configmaps,
            "cronjobs": api.list("cronjobs", namespace=NAMESPACE),
            "events": api.events(namespace=NAMESPACE),
        },
        "checks": {"same_surface_error": error == SURFACE_ERROR},
        "passed": error == SURFACE_ERROR,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"variant": args.variant, "passed": payload["passed"]}))
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
