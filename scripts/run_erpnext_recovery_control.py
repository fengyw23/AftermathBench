from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from aftermath_bench.integrations.erpnext_agent import (
    ERPNextRecoveryEnvironment,
    reference_erpnext_recovery,
)
from aftermath_bench.integrations.erpnext_evaluator import (
    evaluate_erpnext_recovery,
)
from aftermath_bench.integrations.erpnext_evidence import (
    ERPNextEvidenceCollector,
    ProcurementPaymentIDs,
)
from aftermath_bench.integrations.erpnext_faults import (
    ERP_NEXT_FAULT_VARIANTS,
    default_worker_control,
)
from aftermath_bench.integrations.erpnext_stack import ERPNextStack
from aftermath_bench.integrations.frappe import (
    FrappeConfig,
    FrappeHTTPAdapter,
)
from aftermath_bench.schema import repository_root


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run the state-driven reference recovery through agent-visible "
            "ERPNext tools."
        )
    )
    parser.add_argument("--variant", required=True, choices=ERP_NEXT_FAULT_VARIANTS)
    parser.add_argument("--prefix", type=Path, required=True)
    parser.add_argument("--credentials", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    parser.add_argument(
        "--container-cli",
        choices=("docker", "podman"),
        default="docker",
    )
    args = parser.parse_args()

    root = repository_root()
    runtime = root / "runtimes" / "erpnext"
    prefix = json.loads(args.prefix.read_text(encoding="utf-8"))
    credentials = json.loads(args.credentials.read_text(encoding="utf-8"))
    adapter = FrappeHTTPAdapter(
        FrappeConfig(
            base_url=args.base_url,
            api_key=credentials["api_key"],
            api_secret=credentials["api_secret"],
        )
    )
    ids = ProcurementPaymentIDs(
        purchase_order=prefix["purchase_order"],
        purchase_receipt=prefix["purchase_receipt"],
        purchase_invoice=prefix["purchase_invoice"],
    )
    stack = ERPNextStack(
        compose_file=runtime / "compose.yaml",
        container_cli=args.container_cli,
        db_root_password=os.environ.get(
            "AFTERMATH_DB_ROOT_PASSWORD",
            "aftermath-root",
        ),
    )
    environment = ERPNextRecoveryEnvironment(
        adapter=adapter,
        ids=ids,
        payment_entry=prefix["payment_entry"],
        stack=stack,
        worker_control=default_worker_control(
            root,
            container_cli=args.container_cli,
        ),
        collector=ERPNextEvidenceCollector(adapter),
    )
    trace = reference_erpnext_recovery(environment)
    final_evidence = environment.snapshot()
    evaluation = evaluate_erpnext_recovery(
        final_evidence,
        expected_prefix_fingerprints=prefix["protected_fingerprints"],
    )
    report = {
        "schema_version": "0.3",
        "variant": args.variant,
        "control": "state_driven_reference_using_agent_visible_tools",
        "reference_trace": trace,
        "environment_tool_events": environment.event_log(),
        "final_evidence": final_evidence,
        "evaluation": {
            "passed": evaluation.passed,
            "checks": evaluation.checks,
            "diagnostics": evaluation.diagnostics,
            "failures": evaluation.failures,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(
        {
            "variant": args.variant,
            "passed": evaluation.passed,
            "failures": evaluation.failures,
            "tools": [step["tool"] for step in trace],
            "output": str(args.output),
        },
        indent=2,
    ))
    return 0 if evaluation.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
