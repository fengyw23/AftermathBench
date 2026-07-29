from __future__ import annotations

import argparse
import json
from pathlib import Path

from aftermath_bench.integrations.kubernetes_api import KubernetesApi
from aftermath_bench.integrations.kubernetes_recovery import (
    KubernetesRolloutEnvironment,
    evaluate_kubernetes_rollout_recovery,
)
from aftermath_bench.integrations.kubernetes_rollout_baselines import (
    BASELINE_NAMES,
    run_fixed_kubernetes_baseline,
)
from aftermath_bench.integrations.kubernetes_stack import KubernetesStack


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Execute one fixed policy at a native rollout boundary."
    )
    parser.add_argument("--baseline", choices=BASELINE_NAMES, required=True)
    parser.add_argument("--variant", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    stack = KubernetesStack.from_repository()
    environment = KubernetesRolloutEnvironment(
        KubernetesApi(context=stack.context)
    )
    trace = run_fixed_kubernetes_baseline(
        args.baseline,
        environment=environment,
    )
    evaluation = evaluate_kubernetes_rollout_recovery(
        environment.snapshot()
    )
    report = {
        "schema_version": "0.1",
        "scenario_id": "k8s-deployment-rollout-dev-001",
        "variant": args.variant,
        "baseline": args.baseline,
        "source": "executed against the native failure state",
        "trace": list(trace),
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
                "failures": evaluation.failures,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
