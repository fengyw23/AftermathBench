from __future__ import annotations

import argparse
import json
from pathlib import Path

from aftermath_bench.integrations.kubernetes_api import KubernetesApi
from aftermath_bench.integrations.kubernetes_migration_prefix import SCENARIO_ID
from aftermath_bench.integrations.kubernetes_migration_recovery import (
    KubernetesMigrationEnvironment,
    evaluate_kubernetes_migration_recovery,
    reference_kubernetes_migration_recovery,
)
from aftermath_bench.integrations.kubernetes_stack import KubernetesStack


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--variant", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    stack = KubernetesStack.from_repository()
    environment = KubernetesMigrationEnvironment(KubernetesApi(context=stack.context))
    error = None
    try:
        trace = reference_kubernetes_migration_recovery(environment)
    except Exception as caught:  # noqa: BLE001
        trace = environment.event_log()
        error = {"exception_type": type(caught).__name__, "error": str(caught)}
    evidence = environment.snapshot()
    evaluation = evaluate_kubernetes_migration_recovery(evidence)
    mutations = [
        item["tool"] for item in trace if item["tool"] in environment.MUTATION_TOOLS
    ]
    report = {
        "schema_version": "0.3",
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
                "release_ledger_closed",
                "recovery_audit_closed",
                "recovery_event_applied_once",
                "escaped_preparation_compensated_once",
                "release_published_once",
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
