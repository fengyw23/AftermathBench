from __future__ import annotations

import argparse
import json
from pathlib import Path

from aftermath_bench.integrations.kubernetes_api import KubernetesApi
from aftermath_bench.integrations.kubernetes_settlement_recovery import (
    KubernetesSettlementEnvironment,
    evaluate_kubernetes_settlement_recovery,
    reference_kubernetes_settlement_recovery,
)
from aftermath_bench.integrations.kubernetes_stack import KubernetesStack


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--variant", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    stack = KubernetesStack.from_repository()
    environment = KubernetesSettlementEnvironment(
        KubernetesApi(context=stack.context)
    )
    error = None
    try:
        trace = reference_kubernetes_settlement_recovery(environment)
    except Exception as caught:  # noqa: BLE001 - preserve diagnostic evidence
        trace = environment.event_log()
        error = {"exception_type": type(caught).__name__, "error": str(caught)}
    evidence = environment.snapshot()
    evaluation = evaluate_kubernetes_settlement_recovery(evidence)
    mutations = [
        item["tool"]
        for item in trace
        if item["tool"] in environment.MUTATION_TOOLS
    ]
    queries = [
        item["tool"]
        for item in trace
        if item["tool"] not in environment.MUTATION_TOOLS
    ]
    report = {
        "schema_version": "0.1",
        "scenario_id": "k8s-cronjob-settlement-dev-001",
        "variant": args.variant,
        "control": "state_driven_reference_using_agent_visible_tools",
        "reference_trace": list(trace),
        "query_tools": queries,
        "mutation_tools": mutations,
        "downstream_repairs": sum(
            (
                evaluation.checks["target_lease_claimed"],
                evaluation.checks["target_delivery_applied_once"],
                evaluation.checks["receipt_recorded"],
                evaluation.checks["monthly_ledger_closed"],
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
                "error": error,
            },
            indent=2,
        )
    )
    return 0 if evaluation.passed and error is None else 1


if __name__ == "__main__":
    raise SystemExit(main())
