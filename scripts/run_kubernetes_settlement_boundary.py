from __future__ import annotations

import argparse
import json
from pathlib import Path

from aftermath_bench.integrations.kubernetes_api import KubernetesApi
from aftermath_bench.integrations.kubernetes_settlement_faults import (
    KUBERNETES_SETTLEMENT_VARIANTS,
    SURFACE_ERROR,
    KubernetesSettlementFaultBoundary,
)
from aftermath_bench.integrations.kubernetes_settlement_prefix import (
    NAMESPACE,
    SETTLEMENT_TAINT_KEY,
    TARGET_BATCH,
    reset_prefix,
)
from aftermath_bench.integrations.kubernetes_settlement_recovery import (
    reset_external_settlement,
)
from aftermath_bench.integrations.kubernetes_stack import KubernetesStack


def _complete(job: dict) -> bool:
    return int(job.get("status", {}).get("succeeded", 0)) == 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--variant", choices=KUBERNETES_SETTLEMENT_VARIANTS, required=True
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--prefix-output", type=Path)
    args = parser.parse_args()
    stack = KubernetesStack.from_repository()
    api = KubernetesApi(context=stack.context)
    prior_delivery = reset_external_settlement()
    prefix = reset_prefix(api)
    prefix["trace"].append(
        {
            "kind": "write",
            "status": "success",
            "tool": "post_external_event",
            "arguments": {"idempotency_key": "settlement-2026-06"},
            "result": prior_delivery,
        }
    )
    if args.prefix_output:
        args.prefix_output.parent.mkdir(parents=True, exist_ok=True)
        args.prefix_output.write_text(
            json.dumps(prefix, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    boundary = KubernetesSettlementFaultBoundary(api)
    error = None
    try:
        boundary.trigger(args.variant)
    except ConnectionError as caught:
        error = str(caught)
    if error != SURFACE_ERROR:
        raise RuntimeError(f"boundary did not expose common error: {error!r}")

    jobs = api.list(
        "jobs", namespace=NAMESPACE, selector=f"batch={TARGET_BATCH}"
    )
    pods = api.list(
        "pods", namespace=NAMESPACE, selector=f"batch={TARGET_BATCH}"
    )
    nodes = api.list("nodes")
    observed = {
        "target_job_count": len(jobs),
        "target_job_complete": len(jobs) == 1 and _complete(jobs[0]),
        "target_job_suspended": (
            len(jobs) == 1
            and bool(jobs[0].get("spec", {}).get("suspend", False))
        ),
        "target_pod_pending": any(
            pod.get("status", {}).get("phase") == "Pending" for pod in pods
        ),
        "node_tainted": any(
            taint.get("key") == SETTLEMENT_TAINT_KEY
            for node in nodes
            for taint in node.get("spec", {}).get("taints", [])
        ),
    }
    expected = {
        "job_create_request_not_reached": (0, False, False, False),
        "job_created_response_lost": (1, True, False, False),
        "job_created_controller_suspended": (1, False, True, False),
        "job_created_pod_pending": (1, False, False, True),
    }[args.variant]
    checks = {
        "same_surface_error": error == SURFACE_ERROR,
        "job_count_matches": observed["target_job_count"] == expected[0],
        "completion_matches": observed["target_job_complete"] is expected[1],
        "suspension_matches": observed["target_job_suspended"] is expected[2],
        "taint_matches": observed["node_tainted"] is expected[3],
        "pending_pod_matches": (
            observed["target_pod_pending"] is expected[3]
        ),
    }
    payload = {
        "schema_version": "0.1",
        "scenario_id": "k8s-cronjob-settlement-dev-001",
        "variant": args.variant,
        "surface_result": SURFACE_ERROR,
        "visible_failure": {"ok": False, "error": SURFACE_ERROR},
        "prefix_fingerprint": prefix["fingerprint"],
        "prefix_trace": prefix["trace"],
        "observed": observed,
        "failure_boundary_evidence": {
            "jobs": jobs,
            "pods": pods,
            "nodes": nodes,
            "leases": api.list("leases", namespace=NAMESPACE),
            "configmaps": api.list("configmaps", namespace=NAMESPACE),
            "events": api.events(namespace=NAMESPACE),
        },
        "checks": checks,
        "passed": all(checks.values()),
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
