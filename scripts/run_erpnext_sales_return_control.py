from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from aftermath_bench.integrations.erpnext_faults import (
    default_worker_control,
)
from aftermath_bench.integrations.erpnext_sales_return_agent import (
    ERPNextSalesReturnEnvironment,
    reference_sales_return_recovery,
)
from aftermath_bench.integrations.erpnext_sales_return_evaluator import (
    evaluate_sales_return_recovery,
)
from aftermath_bench.integrations.erpnext_sales_return_evidence import (
    ERPNextSalesReturnEvidenceCollector,
)
from aftermath_bench.integrations.erpnext_stack import ERPNextStack
from aftermath_bench.integrations.frappe import (
    FrappeConfig,
    FrappeHTTPAdapter,
)
from aftermath_bench.schema import repository_root

MUTATION_TOOLS = {
    "submit_document",
    "cancel_document",
    "create_sales_return",
    "create_credit_note",
    "create_delivery_note_from_order",
    "create_sales_invoice_from_delivery",
    "reconcile_customer_documents",
    "enqueue_document_webhook",
    "resume_workers",
}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the reference native sales-return recovery."
    )
    parser.add_argument("--prefix", type=Path, required=True)
    parser.add_argument("--variant", required=True)
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
            "AFTERMATH_DB_ROOT_PASSWORD",
            "aftermath-root",
        ),
    )
    environment = ERPNextSalesReturnEnvironment(
        adapter=adapter,
        prefix=prefix,
        stack=stack,
        worker_control=default_worker_control(
            root,
            container_cli=args.container_cli,
        ),
        collector=ERPNextSalesReturnEvidenceCollector(adapter),
    )
    error = None
    try:
        trace = reference_sales_return_recovery(environment)
    except Exception as caught:  # noqa: BLE001 - control must preserve evidence
        trace = tuple(environment.event_log())
        error = {
            "exception_type": type(caught).__name__,
            "error": str(caught),
        }
    evidence = environment.snapshot()
    evaluation = evaluate_sales_return_recovery(
        evidence,
        prefix=prefix,
    )
    if trace and not isinstance(trace[0], dict):
        normalized_trace = [
            {
                "tool": event.tool,
                "arguments": event.arguments,
                "result": event.result,
            }
            for event in trace
        ]
    else:
        normalized_trace = list(trace)
    mutation_tools = [
        step["tool"]
        for step in normalized_trace
        if step["tool"] in MUTATION_TOOLS
    ]
    query_tools = [
        step["tool"]
        for step in normalized_trace
        if step["tool"] not in MUTATION_TOOLS
    ]
    repaired_groups = {
        "customer_credit": (
            prefix["credit_note"]
            in {
                step["arguments"].get("name")
                for step in normalized_trace
                if step["tool"] == "submit_document"
            }
            and "reconcile_customer_documents" in mutation_tools
        ),
        "replacement_chain": (
            any(
                step["tool"] == "submit_document"
                and step["arguments"].get("doctype") == "Sales Invoice"
                for step in normalized_trace
            )
            and "reconcile_customer_documents" in mutation_tools
        ),
        "pickup_delivery": (
            "enqueue_document_webhook" in mutation_tools
            or "resume_workers" in mutation_tools
            or evidence.get("pickup_delivery") is not None
        ),
    }
    report = {
        "schema_version": "0.1",
        "scenario_id": prefix["scenario_id"],
        "variant": args.variant,
        "control": "state_driven_reference_using_agent_visible_tools",
        "reference_trace": normalized_trace,
        "query_tools": query_tools,
        "mutation_tools": mutation_tools,
        "repaired_groups": repaired_groups,
        "downstream_repairs": sum(repaired_groups.values()),
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
                "scenario_id": prefix["scenario_id"],
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
