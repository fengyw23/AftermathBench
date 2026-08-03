from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from aftermath_bench.integrations.erpnext_faults import default_worker_control
from aftermath_bench.integrations.erpnext_multiwarehouse_agent import (
    ERPNextMultiwarehouseEnvironment,
)
from aftermath_bench.integrations.erpnext_multiwarehouse_baselines import (
    BASELINE_NAMES,
    run_multiwarehouse_baseline,
)
from aftermath_bench.integrations.erpnext_multiwarehouse_evaluator import (
    evaluate_multiwarehouse_recovery,
)
from aftermath_bench.integrations.erpnext_multiwarehouse_evidence import (
    ERPNextMultiwarehouseEvidenceCollector,
)
from aftermath_bench.integrations.erpnext_stack import ERPNextStack
from aftermath_bench.integrations.frappe import FrappeConfig, FrappeHTTPAdapter
from aftermath_bench.schema import repository_root


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a multiwarehouse baseline.")
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
    environment = ERPNextMultiwarehouseEnvironment(
        adapter=adapter,
        prefix=prefix,
        stack=ERPNextStack(
            compose_file=root / "runtimes" / "erpnext" / "compose.yaml",
            container_cli=args.container_cli,
            db_root_password=os.environ.get(
                "AFTERMATH_DB_ROOT_PASSWORD", "aftermath-root"
            ),
        ),
        worker_control=default_worker_control(root, container_cli=args.container_cli),
        collector=ERPNextMultiwarehouseEvidenceCollector(adapter),
    )
    error = None
    try:
        trace = list(run_multiwarehouse_baseline(args.baseline, environment))
    except Exception as caught:  # noqa: BLE001 - retain baseline failure evidence
        trace = [
            {"tool": event.tool, "arguments": event.arguments, "result": event.result}
            for event in environment.event_log()
        ]
        error = {"exception_type": type(caught).__name__, "error": str(caught)}
    evidence = environment.snapshot()
    evaluation = evaluate_multiwarehouse_recovery(evidence, prefix=prefix)
    report = {
        "schema_version": "0.1",
        "artifact_type": "erpnext_multiwarehouse_baseline",
        "scenario_id": prefix["scenario_id"],
        "variant": args.variant,
        "baseline": args.baseline,
        "trace": trace,
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
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "variant": args.variant,
                "baseline": args.baseline,
                "passed": evaluation.passed,
                "failures": evaluation.failures,
                "baseline_error": error,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
