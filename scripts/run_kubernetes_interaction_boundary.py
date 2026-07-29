from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from aftermath_bench.integrations.kubernetes_api import KubernetesApi
from aftermath_bench.integrations.kubernetes_interaction_faults import (
    KUBERNETES_INTERACTION_VARIANTS,
    SURFACE_ERROR,
    KubernetesInteractionFaultBoundary,
    capture_interaction_facts,
)
from aftermath_bench.integrations.kubernetes_interaction_prefix import (
    NAMESPACE,
    REGISTRY_STABLE_KEY,
    SCENARIO_ID,
    reset_interaction_prefix,
)
from aftermath_bench.integrations.kubernetes_interaction_scope import (
    INTERACTION_VARIANT_FACTS,
)
from aftermath_bench.integrations.kubernetes_settlement_recovery import _json_request
from aftermath_bench.integrations.kubernetes_stack import KubernetesStack


def _reset_external(url: str = "http://127.0.0.1:9092") -> dict[str, Any]:
    base = url.rstrip("/")
    reset = _json_request(f"{base}/admin/reset", method="DELETE")
    stable = _json_request(
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
        raise RuntimeError(f"external reset failed: reset={reset}, stable={stable}")
    return stable


def _external_keys(url: str = "http://127.0.0.1:9092") -> set[str]:
    payload = _json_request(f"{url.rstrip('/')}/deliveries")
    return {str(item["key"]) for item in payload.get("deliveries", ())}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--variant", choices=KUBERNETES_INTERACTION_VARIANTS, required=True
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--prefix-output", type=Path)
    args = parser.parse_args()
    stack = KubernetesStack.from_repository()
    api = KubernetesApi(context=stack.context)
    stable = _reset_external()
    prefix = reset_interaction_prefix(api)
    prefix["trace"].append(
        {
            "kind": "write",
            "status": "success",
            "tool": "post_external_event",
            "arguments": {"idempotency_key": REGISTRY_STABLE_KEY},
            "result": stable,
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
        KubernetesInteractionFaultBoundary(api).trigger(args.variant)
    except ConnectionError as caught:
        error = str(caught)
    facts = capture_interaction_facts(api, external_keys=_external_keys())
    declared = INTERACTION_VARIANT_FACTS[args.variant]
    payload = {
        "schema_version": "0.5",
        "scenario_id": SCENARIO_ID,
        "variant": args.variant,
        "surface_result": SURFACE_ERROR,
        "visible_failure": {"ok": False, "error": SURFACE_ERROR},
        "prefix_fingerprint": prefix["fingerprint"],
        "prefix_trace": prefix["trace"],
        "counterfactual_facts": facts,
        "declared_counterfactual_facts": declared,
        "failure_boundary_evidence": {
            "configmaps": api.list("configmaps", namespace=NAMESPACE),
            "deployments": api.list("deployments", namespace=NAMESPACE),
            "services": api.list("services", namespace=NAMESPACE),
            "secrets": api.list("secrets", namespace=NAMESPACE),
            "jobs": api.list("jobs", namespace=NAMESPACE),
            "pods": api.list("pods", namespace=NAMESPACE),
            "events": api.events(namespace=NAMESPACE),
        },
        "checks": {
            "same_surface_error": error == SURFACE_ERROR,
            "native_facts_match_declared_matrix": facts == declared,
        },
    }
    payload["passed"] = all(payload["checks"].values())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "variant": args.variant,
                "passed": payload["passed"],
                "checks": payload["checks"],
            },
            indent=2,
        )
    )
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
