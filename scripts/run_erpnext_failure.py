from __future__ import annotations

import argparse
import json
import os
import time
import urllib.request
from pathlib import Path

from aftermath_bench.integrations.erpnext_evidence import (
    ERPNextEvidenceCollector,
    ProcurementPaymentIDs,
)
from aftermath_bench.integrations.erpnext_evaluator import (
    evaluate_erpnext_recovery,
    validate_failure_boundary,
)
from aftermath_bench.integrations.erpnext_faults import (
    ERP_NEXT_FAULT_VARIANTS,
    ERPNextFaultController,
    default_worker_control,
)
from aftermath_bench.integrations.erpnext_stack import ERPNextStack
from aftermath_bench.integrations.frappe import (
    FrappeConfig,
    FrappeHTTPAdapter,
)
from aftermath_bench.schema import repository_root


def _get_json(url: str) -> dict:
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Restore a prefix and inject one native ERPNext failure."
    )
    parser.add_argument("--variant", required=True, choices=ERP_NEXT_FAULT_VARIANTS)
    parser.add_argument("--prefix", type=Path, required=True)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    parser.add_argument("--credentials", type=Path)
    parser.add_argument(
        "--container-cli",
        choices=("docker", "podman"),
        default="docker",
    )
    args = parser.parse_args()

    root = repository_root()
    runtime = root / "runtimes" / "erpnext"
    credentials_path = (
        args.credentials
        or runtime / ".runtime" / "credentials.json"
    )
    credentials = json.loads(credentials_path.read_text(encoding="utf-8"))
    prefix = json.loads(args.prefix.read_text(encoding="utf-8"))
    stack = ERPNextStack(
        compose_file=runtime / "compose.yaml",
        container_cli=args.container_cli,
        db_root_password=os.environ.get(
            "AFTERMATH_DB_ROOT_PASSWORD",
            "aftermath-root",
        ),
    )
    stack.restore_database(args.snapshot)
    fault = ERPNextFaultController(
        worker_control=default_worker_control(
            root,
            container_cli=args.container_cli,
        )
    )
    adapter = FrappeHTTPAdapter(
        FrappeConfig(
            base_url=args.base_url,
            api_key=credentials["api_key"],
            api_secret=credentials["api_secret"],
        )
    )
    payment_response = adapter.get_resource(
        "Payment Entry",
        prefix["payment_entry"],
    )
    payment_document = payment_response.get("data")
    if not isinstance(payment_document, dict):
        raise RuntimeError("Frappe returned no Payment Entry before fault arming")
    fault.arm(args.variant)
    visible_failure = None
    try:
        response = adapter.submit_loaded_document(payment_document)
    except Exception as error:
        visible_failure = {
            "ok": False,
            "error": "connection_lost_before_confirmation",
            "exception_type": type(error).__name__,
        }
    else:
        raise RuntimeError(
            f"fault did not hide the submit result: {response}"
        )
    finally:
        fault.disarm_transport_after_failure(args.variant)

    ids = ProcurementPaymentIDs(
        purchase_order=prefix["purchase_order"],
        purchase_receipt=prefix["purchase_receipt"],
        purchase_invoice=prefix["purchase_invoice"],
    )
    collector = ERPNextEvidenceCollector(adapter)
    evidence = collector.collect(ids)
    if args.variant == "database_committed_response_lost":
        deadline = time.monotonic() + 30
        while evidence.get("remittance") is None and time.monotonic() < deadline:
            time.sleep(0.5)
            evidence = collector.collect(ids)

    evaluation = evaluate_erpnext_recovery(
        evidence,
        expected_prefix_fingerprints=prefix["protected_fingerprints"],
    )
    gateway_audit = _get_json("http://127.0.0.1:9091/audit")
    boundary_validation = validate_failure_boundary(
        args.variant,
        evidence,
        gateway_audit.get("events", []),
    )
    report = {
        "schema_version": "0.3",
        "variant": args.variant,
        "visible_failure": visible_failure,
        "prefix": prefix,
        "failure_boundary_evidence": evidence,
        "gateway_audit": gateway_audit,
        "boundary_validation": {
            "passed": boundary_validation.passed,
            "checks": boundary_validation.checks,
            "failures": boundary_validation.failures,
        },
        "already_recovered_at_boundary": evaluation.passed,
        "boundary_evaluation": {
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
            "visible_failure": visible_failure,
            "already_recovered_at_boundary": evaluation.passed,
            "boundary_failures": evaluation.failures,
            "output": str(args.output),
        },
        indent=2,
    ))
    return 0 if boundary_validation.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
