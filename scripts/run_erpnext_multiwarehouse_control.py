from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from aftermath_bench.integrations.erpnext_faults import default_worker_control
from aftermath_bench.integrations.erpnext_multiwarehouse_agent import (
    ERPNextMultiwarehouseEnvironment,
    reference_multiwarehouse_recovery,
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
    parser = argparse.ArgumentParser(
        description="Run the multiwarehouse reference recovery."
    )
    parser.add_argument("--prefix", type=Path, required=True)
    parser.add_argument("--variant", required=True)
    parser.add_argument("--credentials", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--formal-contract",
        action="store_true",
        help="Emit the versioned reference contract required for formal release.",
    )
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
        trace = list(reference_multiwarehouse_recovery(environment))
    except Exception as caught:  # noqa: BLE001 - retain terminal evidence
        trace = [
            {"tool": event.tool, "arguments": event.arguments, "result": event.result}
            for event in environment.event_log()
        ]
        error = {"exception_type": type(caught).__name__, "error": str(caught)}
    evidence = environment.snapshot()
    evaluation = evaluate_multiwarehouse_recovery(evidence, prefix=prefix)
    mutation_tools = [
        step["tool"]
        for step in trace
        if step["tool"] in ERPNextMultiwarehouseEnvironment.MUTATION_TOOLS
    ]
    report = {
        "schema_version": "1.0" if args.formal_contract else "0.1",
        "artifact_type": "erpnext_multiwarehouse_reference_recovery",
        "scenario_id": prefix["scenario_id"],
        "variant": args.variant,
        "phase": "reference",
        "control": "state_driven_reference_using_agent_visible_tools",
        "reference_trace": trace,
        "query_tools": [
            step["tool"]
            for step in trace
            if step["tool"] not in ERPNextMultiwarehouseEnvironment.MUTATION_TOOLS
        ],
        "mutation_tools": mutation_tools,
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
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "variant": args.variant,
                "passed": evaluation.passed,
                "mutations": mutation_tools,
                "failures": evaluation.failures,
                "control_error": error,
            },
            indent=2,
        )
    )
    return 0 if evaluation.passed and error is None else 1


if __name__ == "__main__":
    raise SystemExit(main())
