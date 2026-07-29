from __future__ import annotations

import argparse
import json
from pathlib import Path

from aftermath_bench.integrations.kubernetes_api import KubernetesApi
from aftermath_bench.integrations.kubernetes_recovery import (
    KubernetesRolloutEnvironment,
    evaluate_kubernetes_rollout_recovery,
    reference_kubernetes_rollout_recovery,
)
from aftermath_bench.integrations.kubernetes_stack import KubernetesStack


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--variant", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    stack = KubernetesStack.from_repository()
    environment = KubernetesRolloutEnvironment(
        KubernetesApi(context=stack.context)
    )
    error = None
    try:
        trace = reference_kubernetes_rollout_recovery(environment)
    except Exception as caught:  # noqa: BLE001 - keep terminal evidence
        trace = environment.event_log()
        error = {
            "exception_type": type(caught).__name__,
            "error": str(caught),
        }
    evidence = environment.snapshot()
    evaluation = evaluate_kubernetes_rollout_recovery(evidence)
    mutations = [
        step["tool"]
        for step in trace
        if step["tool"] in environment.MUTATION_TOOLS
    ]
    queries = [
        step["tool"]
        for step in trace
        if step["tool"] not in environment.MUTATION_TOOLS
    ]
    report = {
        "schema_version": "0.1",
        "scenario_id": "k8s-deployment-rollout-dev-001",
        "variant": args.variant,
        "control": "state_driven_reference_using_agent_visible_tools",
        "reference_trace": list(trace),
        "query_tools": queries,
        "mutation_tools": mutations,
        "downstream_repairs": sum(
            (
                evaluation.checks["deployment_is_approved_v2"],
                evaluation.checks["service_selects_only_v2"],
                evaluation.checks["release_record_updated"],
            )
        ),
        "control_error": error,
        "final_evidence": evidence,
        "evaluation": {
            "passed": evaluation.passed,
            "components": evaluation.components,
            "checks": evaluation.checks,
            "diagnostics": evaluation.diagnostics,
            "failures": evaluation.failures,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "variant": args.variant,
                "passed": evaluation.passed,
                "mutations": mutations,
                "failures": evaluation.failures,
                "control_error": error,
            },
            indent=2,
        )
    )
    return 0 if evaluation.passed and error is None else 1


if __name__ == "__main__":
    raise SystemExit(main())
