from __future__ import annotations

import argparse
import json
from pathlib import Path

from aftermath_bench.integrations.kubernetes_api import KubernetesApi
from aftermath_bench.integrations.kubernetes_settlement_recovery import (
    KubernetesSettlementEnvironment,
)
from aftermath_bench.integrations.kubernetes_settlement_v2_baselines import (
    SETTLEMENT_V2_BASELINES,
    run_kubernetes_settlement_v2_baseline,
)
from aftermath_bench.integrations.kubernetes_settlement_v2_prefix import (
    SCENARIO_ID,
)
from aftermath_bench.integrations.kubernetes_settlement_v2_recovery import (
    evaluate_kubernetes_settlement_v2_recovery,
)
from aftermath_bench.integrations.kubernetes_stack import KubernetesStack


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--baseline", choices=SETTLEMENT_V2_BASELINES, required=True
    )
    parser.add_argument("--variant", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    stack = KubernetesStack.from_repository()
    environment = KubernetesSettlementEnvironment(
        KubernetesApi(context=stack.context)
    )
    error = None
    try:
        trace = run_kubernetes_settlement_v2_baseline(
            environment, args.baseline
        )
    except Exception as caught:  # noqa: BLE001
        trace = environment.event_log()
        error = {"exception_type": type(caught).__name__, "error": str(caught)}
    evidence = environment.snapshot()
    evaluation = evaluate_kubernetes_settlement_v2_recovery(evidence)
    report = {
        "schema_version": "0.2",
        "scenario_id": SCENARIO_ID,
        "variant": args.variant,
        "baseline": args.baseline,
        "trace": list(trace),
        "baseline_error": error,
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
                "baseline": args.baseline,
                "passed": evaluation.passed,
                "error": error,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
