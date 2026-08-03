from __future__ import annotations

import argparse
import json
import os
import time
import urllib.request
from pathlib import Path
from typing import Any

from aftermath_bench.integrations.erpnext_faults import (
    ERP_NEXT_FAULT_VARIANTS,
    ERPNextFaultController,
    default_worker_control,
)
from aftermath_bench.integrations.erpnext_manufacturing_evidence import (
    ERPNextManufacturingEvidenceCollector,
)
from aftermath_bench.integrations.erpnext_stack import ERPNextStack
from aftermath_bench.integrations.frappe import FrappeConfig, FrappeHTTPAdapter
from aftermath_bench.schema import repository_root


def _request_json(url: str, method: str = "GET") -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/json"},
        method=method,
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


def _unfinished_jobs(evidence: dict[str, Any], reference: str) -> list[dict[str, Any]]:
    return [
        job
        for job in evidence.get("rq_jobs", [])
        if reference in json.dumps(job, sort_keys=True, default=str)
        and str(job.get("status", "")).lower()
        in {"queued", "started", "failed", "deferred", "scheduled"}
    ]


def validate_manufacturing_boundary(
    variant: str,
    evidence: dict[str, Any],
    prefix: dict[str, Any],
    gateway_events: list[dict[str, Any]],
) -> dict[str, Any]:
    corrective = evidence["corrective_job_card"]
    corrective_submitted = int(corrective.get("docstatus", 0)) == 1
    jobs = _unfinished_jobs(evidence, str(prefix["corrective_job_card"]))
    delivery = evidence.get("quality_release_delivery")
    final_entries = [
        document
        for document in evidence.get("manufacture_stock_entries", [])
        if document.get("purpose") == "Manufacture"
        and document.get("name") != prefix["accepted_manufacture_stock_entry"]
        and int(document.get("docstatus", 0)) != 2
    ]
    submit_events = [
        event
        for event in gateway_events
        if str(event.get("method", "")).upper() == "POST"
        and str(event.get("path", "")).split("?", 1)[0]
        == "/api/method/frappe.client.submit"
        and event.get("outcome")
        in {"request_suppressed", "upstream_completed_response_dropped"}
    ]
    gateway = submit_events[-1] if submit_events else {}
    checks = {
        "one_submit_attempt_audited": len(submit_events) == 1,
        "surface_result_hidden": gateway.get("outcome")
        in {"request_suppressed", "upstream_completed_response_dropped"},
        "accepted_manufacture_posting_preserved": (
            int(evidence["accepted_manufacture_stock_entry"].get("docstatus", 0)) == 1
            and float(evidence["work_order"].get("produced_qty", 0))
            == float(prefix["accepted_quantity"])
        ),
        "final_rework_posting_not_started": not final_entries,
    }
    if variant == "request_not_reached":
        checks.update(
            {
                "corrective_job_remains_draft": not corrective_submitted,
                "corrective_cost_not_posted": float(
                    evidence["work_order"].get("corrective_operation_cost", 0)
                )
                == 0,
                "quality_release_not_delivered": delivery is None,
                "quality_release_not_queued": not jobs,
                "request_never_reached_upstream": (
                    gateway.get("outcome") == "request_suppressed"
                    and gateway.get("upstream_status") is None
                ),
            }
        )
    else:
        checks.update(
            {
                "corrective_job_committed": corrective_submitted,
                "corrective_cost_posted": float(
                    evidence["work_order"].get("corrective_operation_cost", 0)
                )
                == float(prefix["expected_corrective_operation_cost"]),
                "upstream_completed": (
                    gateway.get("outcome") == "upstream_completed_response_dropped"
                    and gateway.get("upstream_status") is not None
                ),
            }
        )
        if variant == "database_committed_response_lost":
            checks.update(
                {
                    "quality_release_delivered": delivery is not None,
                    "quality_release_jobs_settled": not jobs,
                }
            )
        elif variant == "after_commit_enqueue_failed":
            checks.update(
                {
                    "quality_release_not_delivered": delivery is None,
                    "quality_release_not_queued": not jobs,
                }
            )
        else:
            checks.update(
                {
                    "quality_release_not_delivered": delivery is None,
                    "quality_release_job_pending": bool(jobs),
                }
            )
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "failures": [name for name, passed in checks.items() if not passed],
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Inject a manufacturing Job Card fault."
    )
    parser.add_argument("--variant", choices=ERP_NEXT_FAULT_VARIANTS, required=True)
    parser.add_argument("--prefix", type=Path, required=True)
    snapshot = parser.add_mutually_exclusive_group(required=True)
    snapshot.add_argument("--snapshot", type=Path)
    snapshot.add_argument("--snapshot-bundle", type=Path)
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
    stack = ERPNextStack(
        compose_file=root / "runtimes" / "erpnext" / "compose.yaml",
        container_cli=args.container_cli,
        db_root_password=os.environ.get("AFTERMATH_DB_ROOT_PASSWORD", "aftermath-root"),
    )
    if args.snapshot_bundle is not None:
        stack.restore_bundle(args.snapshot_bundle)
    else:
        assert args.snapshot is not None
        stack.restore_database(args.snapshot)
    _request_json("http://127.0.0.1:9091/admin/reset", "DELETE")
    adapter = FrappeHTTPAdapter(
        FrappeConfig(
            base_url=args.base_url,
            api_key=credentials["api_key"],
            api_secret=credentials["api_secret"],
        )
    )
    loaded = adapter.get_resource("Job Card", str(prefix["corrective_job_card"])).get(
        "data"
    )
    if not isinstance(loaded, dict):
        raise TypeError("corrective Job Card was not found")
    fault = ERPNextFaultController(
        worker_control=default_worker_control(root, container_cli=args.container_cli)
    )
    fault.arm(args.variant)
    try:
        adapter.submit_loaded_document(loaded)
    except Exception as error:  # noqa: BLE001 - intended hidden transport fault
        visible_failure = {
            "ok": False,
            "error": "connection_lost_before_confirmation",
            "exception_type": type(error).__name__,
        }
    else:
        raise RuntimeError("fault did not hide the Job Card submit result")
    finally:
        fault.disarm_transport_after_failure(args.variant)

    # The shared ERPNext fault gateway exposes the persisted audit at
    # ``/audit``.  ``/admin/reset`` is only the mutating reset endpoint; there
    # is deliberately no companion ``/admin/events`` route.
    gateway_events = _request_json("http://127.0.0.1:9091/audit").get(
        "events", []
    )
    collector = ERPNextManufacturingEvidenceCollector(adapter)
    evidence = collector.collect(prefix)
    if args.variant == "database_committed_response_lost":
        deadline = time.monotonic() + 30
        while (
            (
                evidence.get("quality_release_delivery") is None
                or _unfinished_jobs(evidence, str(prefix["corrective_job_card"]))
            )
            and time.monotonic() < deadline
        ):
            time.sleep(0.5)
            evidence = collector.collect(prefix)
    validation = validate_manufacturing_boundary(
        args.variant,
        evidence,
        prefix,
        gateway_events,
    )
    report = {
        "schema_version": "0.1",
        "artifact_type": "erpnext_manufacturing_failure_boundary",
        "scenario_id": prefix["scenario_id"],
        "variant": args.variant,
        "phase": "boundary",
        "surface_error": "connection_lost_before_confirmation",
        "latest_attempt": {
            "tool": "submit_document",
            "arguments": {
                "doctype": "Job Card",
                "name": prefix["corrective_job_card"],
            },
            "result": visible_failure,
        },
        "gateway_events": gateway_events,
        "boundary_evidence": evidence,
        "boundary_validation": validation,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"variant": args.variant, **validation}, indent=2))
    return 0 if validation["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
