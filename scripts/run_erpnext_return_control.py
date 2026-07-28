from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from aftermath_bench.integrations.erpnext_faults import (
    default_worker_control,
)
from aftermath_bench.integrations.erpnext_return_agent import (
    ERPNextPartialReturnEnvironment,
    reference_partial_return_recovery,
)
from aftermath_bench.integrations.erpnext_return_evaluator import (
    evaluate_partial_return_recovery,
)
from aftermath_bench.integrations.erpnext_return_evidence import (
    ERPNextPartialReturnEvidenceCollector,
)
from aftermath_bench.integrations.erpnext_stack import ERPNextStack
from aftermath_bench.integrations.frappe import (
    FrappeConfig,
    FrappeHTTPAdapter,
)
from aftermath_bench.schema import repository_root


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the reference partial-return recovery."
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
    credentials = json.loads(
        args.credentials.read_text(encoding="utf-8")
    )
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
    environment = ERPNextPartialReturnEnvironment(
        adapter=adapter,
        prefix=prefix,
        stack=stack,
        worker_control=default_worker_control(
            root,
            container_cli=args.container_cli,
        ),
        collector=ERPNextPartialReturnEvidenceCollector(adapter),
    )
    error = None
    try:
        trace = reference_partial_return_recovery(environment)
    except Exception as caught:
        trace = ()
        error = {
            "exception_type": type(caught).__name__,
            "error": str(caught),
        }
    evidence = environment.snapshot()
    evaluation = evaluate_partial_return_recovery(
        evidence,
        prefix=prefix,
    )
    mutation_tools = [
        step["tool"]
        for step in trace
        if step["tool"]
        in {
            "submit_document",
            "cancel_document",
            "create_purchase_return",
            "create_debit_note",
            "create_purchase_receipt_from_order",
            "create_purchase_invoice_from_receipt",
            "reconcile_supplier_documents",
            "enqueue_document_webhook",
            "resume_workers",
        }
    ]
    query_tools = [
        step["tool"]
        for step in trace
        if step["tool"] not in {
            "submit_document",
            "cancel_document",
            "create_purchase_return",
            "create_debit_note",
            "create_purchase_receipt_from_order",
            "create_purchase_invoice_from_receipt",
            "reconcile_supplier_documents",
            "enqueue_document_webhook",
            "resume_workers",
        }
    ]
    submitted_names = {
        step["arguments"].get("name")
        for step in trace
        if step["tool"] == "submit_document"
    }
    replacement_invoice_submitted = any(
        step["tool"] == "submit_document"
        and step["arguments"].get("doctype") == "Purchase Invoice"
        and step["arguments"].get("name") != prefix["debit_note"]
        for step in trace
    )
    repaired_groups = {
        "supplier_credit": (
            prefix["debit_note"] in submitted_names
            and "reconcile_supplier_documents" in mutation_tools
        ),
        "replacement_chain": (
            replacement_invoice_submitted
            and "reconcile_supplier_documents" in mutation_tools
        ),
        "pickup_delivery": (
            "enqueue_document_webhook" in mutation_tools
            or "resume_workers" in mutation_tools
        ),
    }
    report = {
        "schema_version": "0.4",
        "scenario_id": prefix["scenario_id"],
        "variant": args.variant,
        "control": "state_driven_reference_using_agent_visible_tools",
        "reference_trace": trace,
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
    print(json.dumps(
        {
            "scenario_id": prefix["scenario_id"],
            "passed": evaluation.passed,
            "mutations": mutation_tools,
            "failures": evaluation.failures,
            "control_error": error,
        },
        indent=2,
    ))
    return 0 if evaluation.passed and error is None else 1


if __name__ == "__main__":
    raise SystemExit(main())
