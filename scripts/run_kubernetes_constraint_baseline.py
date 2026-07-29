from __future__ import annotations

import argparse
import json
from pathlib import Path

from aftermath_bench.integrations.kubernetes_api import KubernetesApi
from aftermath_bench.integrations.kubernetes_constraint_baselines import (
    CONSTRAINT_BASELINES,
    run_kubernetes_constraint_baseline,
)
from aftermath_bench.integrations.kubernetes_constraint_prefix import SCENARIO_ID
from aftermath_bench.integrations.kubernetes_constraint_recovery import (
    KubernetesConstraintEnvironment,
    evaluate_kubernetes_constraint_recovery,
)
from aftermath_bench.integrations.kubernetes_stack import KubernetesStack


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", choices=CONSTRAINT_BASELINES, required=True)
    parser.add_argument("--variant", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    stack = KubernetesStack.from_repository()
    environment = KubernetesConstraintEnvironment(KubernetesApi(context=stack.context))
    error = None
    try:
        trace = run_kubernetes_constraint_baseline(environment, args.baseline)
    except Exception as caught:  # noqa: BLE001
        trace = environment.event_log()
        error = {"exception_type": type(caught).__name__, "error": str(caught)}
    evidence = environment.snapshot()
    evaluation = evaluate_kubernetes_constraint_recovery(evidence)
    report = {
        "schema_version": "0.4",
        "scenario_id": SCENARIO_ID,
        "variant": args.variant,
        "baseline": args.baseline,
        "semantic_recovery_direction": evaluation.diagnostics[
            "semantic_recovery_direction"
        ],
        "trace": list(trace),
        "baseline_error": error,
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
                "baseline": args.baseline,
                "passed": evaluation.passed,
                "error": error,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
