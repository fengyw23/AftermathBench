from __future__ import annotations

import argparse
import json
from pathlib import Path

from aftermath_bench.integrations.kubernetes_api import KubernetesApi
from aftermath_bench.integrations.kubernetes_migration_faults import (
    KUBERNETES_MIGRATION_VARIANTS,
    SURFACE_ERROR,
    KubernetesMigrationFaultBoundary,
    migration_jobs,
)
from aftermath_bench.integrations.kubernetes_migration_prefix import (
    NAMESPACE,
    SCENARIO_ID,
    SERVICE,
    reset_prefix,
)
from aftermath_bench.integrations.kubernetes_migration_recovery import (
    reset_external_migration,
)
from aftermath_bench.integrations.kubernetes_stack import KubernetesStack


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--variant", choices=KUBERNETES_MIGRATION_VARIANTS, required=True
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--prefix-output", type=Path)
    args = parser.parse_args()
    stack = KubernetesStack.from_repository()
    api = KubernetesApi(context=stack.context)
    stable_event = reset_external_migration()
    prefix = reset_prefix(api)
    prefix["trace"].append(
        {
            "kind": "write",
            "status": "success",
            "tool": "post_external_event",
            "arguments": {"idempotency_key": "release:orders-v1"},
            "result": stable_event,
        }
    )
    if args.prefix_output:
        args.prefix_output.parent.mkdir(parents=True, exist_ok=True)
        args.prefix_output.write_text(
            json.dumps(prefix, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    error = None
    try:
        KubernetesMigrationFaultBoundary(api).trigger(args.variant)
    except ConnectionError as caught:
        error = str(caught)
    if error != SURFACE_ERROR:
        raise RuntimeError(f"boundary did not expose common error: {error!r}")
    catalog = api.get("configmap", "database-catalog", namespace=NAMESPACE)
    service = api.get("service", SERVICE, namespace=NAMESPACE)
    jobs = migration_jobs(api)
    payload = {
        "schema_version": "0.3",
        "scenario_id": SCENARIO_ID,
        "variant": args.variant,
        "surface_result": SURFACE_ERROR,
        "visible_failure": {"ok": False, "error": SURFACE_ERROR},
        "prefix_fingerprint": prefix["fingerprint"],
        "prefix_trace": prefix["trace"],
        "observed": {
            "schema_epoch": catalog.get("data", {}).get("schemaEpoch"),
            "service_version": service.get("spec", {})
            .get("selector", {})
            .get("version"),
            "migration_job_count": len(jobs),
        },
        "failure_boundary_evidence": {
            "configmaps": api.list("configmaps", namespace=NAMESPACE),
            "deployments": api.list("deployments", namespace=NAMESPACE),
            "services": api.list("services", namespace=NAMESPACE),
            "secrets": api.list("secrets", namespace=NAMESPACE),
            "jobs": api.list("jobs", namespace=NAMESPACE),
            "pods": api.list("pods", namespace=NAMESPACE),
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
