from __future__ import annotations

import argparse
import json
from pathlib import Path

from aftermath_bench.integrations.kubernetes_api import KubernetesApi
from aftermath_bench.integrations.kubernetes_constraint_prefix import SCENARIO_ID
from aftermath_bench.integrations.kubernetes_constraint_recovery import (
    KubernetesConstraintEnvironment,
    evaluate_kubernetes_constraint_recovery,
    reference_kubernetes_constraint_recovery,
)
from aftermath_bench.integrations.kubernetes_stack import KubernetesStack


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--variant", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    stack = KubernetesStack.from_repository()
    environment = KubernetesConstraintEnvironment(KubernetesApi(context=stack.context))
    error = None
    try:
        trace = reference_kubernetes_constraint_recovery(environment)
    except Exception as caught:  # noqa: BLE001
        trace = environment.event_log()
        error = {"exception_type": type(caught).__name__, "error": str(caught)}
    evidence = environment.snapshot()
    evaluation = evaluate_kubernetes_constraint_recovery(evidence)
    mutations = [
        item["tool"] for item in trace if item["tool"] in environment.MUTATION_TOOLS
    ]
    report = {
        "schema_version": "0.4",
        "scenario_id": SCENARIO_ID,
        "variant": args.variant,
        "control": "state_driven_reference_using_agent_visible_tools",
        "semantic_recovery_direction": evaluation.diagnostics[
            "semantic_recovery_direction"
        ],
        "reference_trace": list(trace),
        "query_tools": [
            item["tool"]
            for item in trace
            if item["tool"] not in environment.MUTATION_TOOLS
        ],
        "mutation_tools": mutations,
        "downstream_repairs": sum(
            bool(evaluation.checks.get(name))
            for name in (
                "change_record_closed",
                "release_ledger_closed",
                "audit_records_observed_facts",
                "closure_event_records_observed_facts",
                "preparation_obligation_closed",
                "publication_obligation_closed",
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
                "direction": report["semantic_recovery_direction"],
                "passed": evaluation.passed,
                "mutations": len(mutations),
                "error": error,
            },
            indent=2,
        )
    )
    return 0 if evaluation.passed and error is None else 1


if __name__ == "__main__":
    raise SystemExit(main())
