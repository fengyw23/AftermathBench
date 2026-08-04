from __future__ import annotations

import argparse
import json
import os
import time
import urllib.request
from decimal import Decimal
from pathlib import Path
from typing import Any

from aftermath_bench.integrations.erpnext_faults import (
    ERP_NEXT_FAULT_VARIANTS,
    ERPNextFaultController,
    default_worker_control,
)
from aftermath_bench.integrations.erpnext_multiwarehouse_evidence import (
    ERPNextMultiwarehouseEvidenceCollector,
)
from aftermath_bench.integrations.erpnext_stack import ERPNextStack
from aftermath_bench.integrations.frappe import FrappeConfig, FrappeHTTPAdapter
from aftermath_bench.schema import repository_root


def _request_json(url: str, method: str = "GET") -> dict[str, Any]:
    request = urllib.request.Request(
        url, headers={"Accept": "application/json"}, method=method
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


def _ledger_quantity(
    rows: list[dict[str, Any]],
    *,
    voucher_no: str,
    item_code: str,
    warehouse: str,
) -> Decimal:
    return sum(
        (
            Decimal(str(row.get("actual_qty", 0)))
            for row in rows
            if str(row.get("voucher_no")) == voucher_no
            and str(row.get("item_code")) == item_code
            and str(row.get("warehouse")) == warehouse
            and not bool(row.get("is_cancelled", False))
        ),
        Decimal(0),
    )


def validate_multiwarehouse_boundary(
    variant: str,
    evidence: dict[str, Any],
    prefix: dict[str, Any],
    gateway_events: list[dict[str, Any]],
) -> dict[str, Any]:
    incoming = next(
        document
        for document in evidence["second_leg_stock_entries"]
        if document["name"] == prefix["second_leg_stock_entry"]
    )
    incoming_submitted = int(incoming.get("docstatus", 0)) == 1
    jobs = _unfinished_jobs(evidence, str(incoming["name"]))
    delivery = evidence.get("arrival_deliveries", {}).get(str(incoming["name"]))
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
    clinic_reservations = [
        document
        for document in evidence.get("stock_reservation_entries", [])
        if str(document.get("voucher_no")) == str(prefix["clinic_sales_order"])
        and int(document.get("docstatus", 0)) != 2
    ]
    checks = {
        "one_submit_attempt_audited": len(submit_events) == 1,
        "surface_result_hidden": gateway.get("outcome")
        in {"request_suppressed", "upstream_completed_response_dropped"},
        "first_leg_preserved": int(
            evidence["outgoing_stock_entry"].get("docstatus", 0)
        )
        == 1,
        "protected_reservation_preserved": int(
            evidence["protected_reservation"].get("docstatus", 0)
        )
        == 1,
        "clinic_reservation_not_precreated": not clinic_reservations,
        "one_prepared_second_leg": len(evidence["second_leg_stock_entries"]) == 1,
    }
    if variant == "request_not_reached":
        checks.update(
            {
                "second_leg_remains_draft": not incoming_submitted,
                "arrival_not_delivered": delivery is None,
                "arrival_not_queued": not jobs,
                "request_never_reached_upstream": (
                    gateway.get("outcome") == "request_suppressed"
                    and gateway.get("upstream_status") is None
                ),
            }
        )
    else:
        quantity = Decimal(str(prefix["transfer_quantity"]))
        checks.update(
            {
                "second_leg_committed": incoming_submitted,
                "outgoing_marked_fully_transferred": Decimal(
                    str(evidence["outgoing_stock_entry"].get("per_transferred", 0))
                )
                == Decimal(100),
                "transit_ledger_closed": _ledger_quantity(
                    evidence["stock_ledger_entries"],
                    voucher_no=str(incoming["name"]),
                    item_code=str(prefix["transfer_item"]),
                    warehouse=str(prefix["transit_warehouse"]),
                )
                == -quantity,
                "destination_ledger_posted": _ledger_quantity(
                    evidence["stock_ledger_entries"],
                    voucher_no=str(incoming["name"]),
                    item_code=str(prefix["transfer_item"]),
                    warehouse=str(prefix["destination_warehouse"]),
                )
                == quantity,
                "upstream_completed": (
                    gateway.get("outcome") == "upstream_completed_response_dropped"
                    and gateway.get("upstream_status") is not None
                ),
            }
        )
        if variant == "database_committed_response_lost":
            checks.update(
                {
                    "arrival_delivered": delivery is not None,
                    "arrival_jobs_settled": not jobs,
                }
            )
        elif variant == "after_commit_enqueue_failed":
            checks.update(
                {
                    "arrival_not_delivered": delivery is None,
                    "arrival_not_queued": not jobs,
                }
            )
        else:
            checks.update(
                {
                    "arrival_not_delivered": delivery is None,
                    "arrival_job_pending": bool(jobs),
                }
            )
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "failures": [name for name, passed in checks.items() if not passed],
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Inject an inter-warehouse second-leg submit fault."
    )
    parser.add_argument("--variant", choices=ERP_NEXT_FAULT_VARIANTS, required=True)
    parser.add_argument("--prefix", type=Path, required=True)
    snapshot = parser.add_mutually_exclusive_group(required=True)
    snapshot.add_argument("--snapshot", type=Path)
    snapshot.add_argument("--snapshot-bundle", type=Path)
    parser.add_argument("--credentials", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--formal-contract",
        action="store_true",
        help="Emit the versioned boundary contract required for formal release.",
    )
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
    loaded = adapter.get_resource(
        "Stock Entry", str(prefix["second_leg_stock_entry"])
    ).get("data")
    if not isinstance(loaded, dict):
        raise TypeError("prepared second-leg Stock Entry was not found")
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
        raise RuntimeError("fault did not hide the Stock Entry submit result")
    finally:
        fault.disarm_transport_after_failure(args.variant)

    gateway_events = _request_json("http://127.0.0.1:9091/audit").get("events", [])
    collector = ERPNextMultiwarehouseEvidenceCollector(adapter)
    evidence = collector.collect(prefix)
    if args.variant == "database_committed_response_lost":
        deadline = time.monotonic() + 30
        while (
            (
                evidence.get("arrival_deliveries", {}).get(
                    str(prefix["second_leg_stock_entry"])
                )
                is None
                or _unfinished_jobs(evidence, str(prefix["second_leg_stock_entry"]))
            )
            and time.monotonic() < deadline
        ):
            time.sleep(0.5)
            evidence = collector.collect(prefix)
    validation = validate_multiwarehouse_boundary(
        args.variant, evidence, prefix, gateway_events
    )
    report = {
        "schema_version": "1.0" if args.formal_contract else "0.1",
        "artifact_type": "erpnext_multiwarehouse_failure_boundary",
        "scenario_id": prefix["scenario_id"],
        "variant": args.variant,
        "phase": "boundary",
        # Keep the user-visible transport failure as a first-class field in
        # the versioned boundary contract.  The formal evidence builder binds
        # this exact value to the scenario declaration, while the nested
        # `latest_attempt.result` remains the machine-readable tool result.
        "surface_result": (
            "HTTP connection lost before the Stock Entry submission response"
        ),
        "visible_failure": visible_failure,
        "surface_error": "connection_lost_before_confirmation",
        "latest_attempt": {
            "tool": "submit_document",
            "arguments": {
                "doctype": "Stock Entry",
                "name": prefix["second_leg_stock_entry"],
            },
            "result": visible_failure,
        },
        "gateway_events": gateway_events,
        "boundary_evidence": evidence,
        "boundary_validation": validation,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"variant": args.variant, **validation}, indent=2))
    return 0 if validation["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
