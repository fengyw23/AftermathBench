from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from aftermath_bench.integrations.erpnext_faults import default_worker_control
from aftermath_bench.integrations.erpnext_manufacturing_agent import (
    ERPNextManufacturingEnvironment,
)
from aftermath_bench.integrations.erpnext_manufacturing_baselines import (
    BASELINE_NAMES,
    run_fixed_manufacturing_baseline,
)
from aftermath_bench.integrations.erpnext_manufacturing_evaluator import (
    evaluate_manufacturing_rework_recovery,
)
from aftermath_bench.integrations.erpnext_manufacturing_evidence import (
    ERPNextManufacturingEvidenceCollector,
)
from aftermath_bench.integrations.erpnext_stack import ERPNextStack
from aftermath_bench.integrations.frappe import FrappeConfig, FrappeHTTPAdapter
from aftermath_bench.schema import repository_root


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Execute one fixed native manufacturing-recovery baseline."
    )
    parser.add_argument("--baseline", choices=BASELINE_NAMES, required=True)
    parser.add_argument("--variant", required=True)
    parser.add_argument("--prefix", type=Path, required=True)
    parser.add_argument("--credentials", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    parser.add_argument(
        "--container-cli", choices=("docker", "podman"), default="docker"
    )
    args = parser.parse_args()

    root = repository_root()
    prefix = json.loads(args.prefix.read_text(encoding="utf-8"))
    credentials = json.loads(args.credentials.read_text(encoding="utf-8"))
    adapter = FrappeHTTPAdapter(
        FrappeConfig(
            base_url=args.base_url,
            api_key=credentials["api_key"],
            api_secret=credentials["api_secret"],
        )
    )
    stack = ERPNextStack(
        compose_file=root / "runtimes" / "erpnext" / "compose.yaml",
        container_cli=args.container_cli,
        db_root_password=os.environ.get(
            "AFTERMATH_DB_ROOT_PASSWORD", "aftermath-root"
        ),
    )
    environment = ERPNextManufacturingEnvironment(
        adapter=adapter,
        prefix=prefix,
        stack=stack,
        worker_control=default_worker_control(
            root, container_cli=args.container_cli
        ),
        collector=ERPNextManufacturingEvidenceCollector(adapter),
    )
    trace = run_fixed_manufacturing_baseline(
        args.baseline,
        environment=environment,
        prefix=prefix,
    )
    evidence = environment.snapshot()
    evaluation = evaluate_manufacturing_rework_recovery(
        evidence,
        prefix=prefix,
    )
    report = {
        "schema_version": "0.1",
        "scenario_id": prefix["scenario_id"],
        "variant": args.variant,
        "baseline": args.baseline,
        "source": "executed against the native manufacturing failure state",
        "trace": trace,
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
                "scenario_id": prefix["scenario_id"],
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
