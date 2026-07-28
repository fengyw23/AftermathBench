from __future__ import annotations

import argparse
import json
import os
import time
import urllib.request
from pathlib import Path

from aftermath_bench.integrations.erpnext_faults import (
    ERP_NEXT_FAULT_VARIANTS,
    ERPNextFaultController,
    default_worker_control,
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


def _get_json(url: str) -> dict:
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


def _unfinished_jobs(evidence: dict, reference: str) -> list[dict]:
    return [
        job
        for job in evidence.get("rq_jobs", [])
        if reference in json.dumps(job, sort_keys=True, default=str)
        and str(job.get("status", "")).lower()
        in {"queued", "started", "failed", "deferred", "scheduled"}
    ]


def _validate_boundary(
    variant: str,
    evidence: dict,
    prefix: dict,
    gateway_events: list[dict],
) -> dict:
    purchase_return = evidence["purchase_return"]
    return_submitted = int(purchase_return.get("docstatus", 0)) == 1
    stock_rows = [
        row
        for row in evidence.get("stock_ledger_entries", [])
        if row.get("voucher_no") == prefix["purchase_return"]
        and not bool(row.get("is_cancelled", False))
    ]
    jobs = _unfinished_jobs(evidence, prefix["purchase_return"])
    delivery = evidence.get("pickup_delivery")
    submit_events = [
        event
        for event in gateway_events
        if str(event.get("method", "")).upper() == "POST"
        and str(event.get("path", "")).split("?", 1)[0]
        == "/api/method/frappe.client.submit"
    ]
    gateway = submit_events[-1] if submit_events else {}
    checks = {
        "one_submit_attempt_audited": len(submit_events) == 1,
        "surface_result_hidden": gateway.get("outcome")
        in {"request_suppressed", "upstream_completed_response_dropped"},
        "downstream_debit_note_still_draft": (
            int(evidence["debit_note"].get("docstatus", 0)) == 0
        ),
        "replacement_receipt_still_draft": (
            int(
                evidence["replacement_purchase_receipt"].get(
                    "docstatus",
                    0,
                )
            )
            == 0
        ),
    }
    if variant == "request_not_reached":
        checks.update(
            {
                "return_remains_draft": not return_submitted,
                "return_has_no_stock_effect": not stock_rows,
                "pickup_not_delivered": delivery is None,
                "pickup_not_queued": not jobs,
                "request_never_reached_upstream": (
                    gateway.get("outcome") == "request_suppressed"
                    and gateway.get("upstream_status") is None
                ),
            }
        )
    else:
        checks.update(
            {
                "return_committed": return_submitted,
                "return_stock_effect_committed": bool(stock_rows),
                "upstream_completed": (
                    gateway.get("outcome")
                    == "upstream_completed_response_dropped"
                    and gateway.get("upstream_status") is not None
                ),
            }
        )
        if variant == "database_committed_response_lost":
            checks.update(
                {
                    "pickup_delivered": delivery is not None,
                    "pickup_jobs_settled": not jobs,
                }
            )
        elif variant == "after_commit_enqueue_failed":
            checks.update(
                {
                    "pickup_not_delivered": delivery is None,
                    "pickup_not_queued": not jobs,
                }
            )
        else:
            checks.update(
                {
                    "pickup_not_delivered": delivery is None,
                    "pickup_job_pending": bool(jobs),
                }
            )
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "failures": [key for key, value in checks.items() if not value],
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Inject one native partial-return failure."
    )
    parser.add_argument(
        "--variant",
        required=True,
        choices=ERP_NEXT_FAULT_VARIANTS,
    )
    parser.add_argument("--prefix", type=Path, required=True)
    parser.add_argument("--snapshot", type=Path, required=True)
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
    runtime = root / "runtimes" / "erpnext"
    stack = ERPNextStack(
        compose_file=runtime / "compose.yaml",
        container_cli=args.container_cli,
        db_root_password=os.environ.get(
            "AFTERMATH_DB_ROOT_PASSWORD",
            "aftermath-root",
        ),
    )
    stack.restore_database(args.snapshot)
    adapter = FrappeHTTPAdapter(
        FrappeConfig(
            base_url=args.base_url,
            api_key=credentials["api_key"],
            api_secret=credentials["api_secret"],
        )
    )
    document = adapter.get_resource(
        "Purchase Receipt",
        prefix["purchase_return"],
    ).get("data")
    if not isinstance(document, dict):
        raise RuntimeError("draft Purchase Return was not found")
    fault = ERPNextFaultController(
        worker_control=default_worker_control(
            root,
            container_cli=args.container_cli,
        )
    )
    fault.arm(args.variant)
    try:
        adapter.submit_loaded_document(document)
    except Exception as error:
        visible_failure = {
            "ok": False,
            "error": "connection_lost_before_confirmation",
            "exception_type": type(error).__name__,
        }
    else:
        raise RuntimeError("fault did not hide the submit result")
    finally:
        fault.disarm_transport_after_failure(args.variant)

    collector = ERPNextPartialReturnEvidenceCollector(adapter)
    evidence = collector.collect(prefix)
    if args.variant == "database_committed_response_lost":
        deadline = time.monotonic() + 30
        while (
            evidence.get("pickup_delivery") is None
            and time.monotonic() < deadline
        ):
            time.sleep(0.5)
            evidence = collector.collect(prefix)
    gateway_audit = _get_json("http://127.0.0.1:9091/audit")
    boundary = _validate_boundary(
        args.variant,
        evidence,
        prefix,
        gateway_audit.get("events", []),
    )
    report = {
        "schema_version": "0.4",
        "scenario_id": prefix["scenario_id"],
        "variant": args.variant,
        "visible_failure": visible_failure,
        "failure_boundary_evidence": evidence,
        "gateway_audit": gateway_audit,
        "boundary_validation": boundary,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(
        {
            "scenario_id": prefix["scenario_id"],
            "variant": args.variant,
            "boundary_validation": boundary,
            "output": str(args.output),
        },
        indent=2,
    ))
    return 0 if boundary["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
