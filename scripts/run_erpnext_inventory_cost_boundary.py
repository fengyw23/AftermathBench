from __future__ import annotations

import argparse
import hashlib
import json
import os
import urllib.request
from pathlib import Path
from typing import Any

from aftermath_bench.integrations.erpnext_faults import (
    ERPNextFaultController,
    default_worker_control,
)
from aftermath_bench.integrations.erpnext_inventory_cost_evidence import (
    ERPNextInventoryCostEvidenceCollector,
)
from aftermath_bench.integrations.erpnext_inventory_cost_recovery import (
    INVENTORY_COST_VARIANTS,
    evaluate_inventory_cost_terminal,
    project_inventory_cost_dimensions,
    reference_inventory_cost_recovery,
    wait_for_attestation,
)
from aftermath_bench.integrations.erpnext_stack import ERPNextStack
from aftermath_bench.integrations.frappe import FrappeConfig, FrappeHTTPAdapter
from aftermath_bench.native_scenario import load_native_scenario
from aftermath_bench.schema import repository_root


def _request_json(url: str) -> Any:
    request = urllib.request.Request(
        url, headers={"Accept": "application/json"}, method="GET"
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


def _sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), default=str
        ).encode("utf-8")
    ).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build and recover one native inventory-cost failure boundary."
    )
    parser.add_argument("--scenario", type=Path, required=True)
    parser.add_argument("--prefix", type=Path, required=True)
    parser.add_argument("--variant", choices=INVENTORY_COST_VARIANTS, required=True)
    parser.add_argument("--credentials", type=Path, required=True)
    parser.add_argument("--snapshot-bundle", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    parser.add_argument(
        "--container-cli", choices=("docker", "podman"), default="docker"
    )
    parser.add_argument("--run-reference", action="store_true")
    args = parser.parse_args()

    root = repository_root()
    scenario = load_native_scenario(args.scenario)
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
    workers = default_worker_control(root, container_cli=args.container_cli)
    faults = ERPNextFaultController(worker_control=workers)
    collector = ERPNextInventoryCostEvidenceCollector(adapter)
    stack.restore_bundle(args.snapshot_bundle)
    transport_variant = (
        "request_not_reached"
        if args.variant == "request_not_reached"
        else "async_job_pending"
    )
    loaded = collector.get_document(
        "Landed Cost Voucher", str(prefix["landed_cost_voucher"])
    )
    faults.arm(transport_variant)
    surface_error: dict[str, str] | None = None
    try:
        adapter.submit_loaded_document(loaded)
    except Exception as error:  # noqa: BLE001 - surface ambiguity is expected
        surface_error = {
            "exception_type": type(error).__name__,
            "message": str(error),
        }
    finally:
        faults.disarm_transport_after_failure(transport_variant)
    if surface_error is None:
        raise RuntimeError("faulted Landed Cost Voucher submission returned normally")

    if args.variant in {
        "voucher_committed_repost_completed_attestation_pending",
    }:
        stack.process_repost_item_valuation_queue()
    if args.variant == "voucher_committed_repost_queued_attested_response_lost":
        workers.start()
        if wait_for_attestation(collector, prefix) is None:
            raise RuntimeError("native settlement attestation was not delivered")

    boundary_evidence = collector.collect(prefix)
    projection = project_inventory_cost_dimensions(boundary_evidence)
    reposts = boundary_evidence.get("repost_item_valuations", [])
    statuses = {str(row.get("status", "")).lower() for row in reposts}
    delivery = boundary_evidence.get("settlement_attestation")
    unfinished_jobs = [
        row
        for row in boundary_evidence.get("rq_jobs", [])
        if str(row.get("status", "")).lower()
        in {"queued", "started", "failed", "deferred", "scheduled"}
    ]
    common = {
        "surface_error_observed": surface_error is not None,
        "single_landed_cost_document": len(
            boundary_evidence.get("landed_cost_vouchers", [])
        )
        == 1,
        "protected_reservation_active": int(
            boundary_evidence["stock_reservation_entry"].get("docstatus", 0)
        )
        == 1,
    }
    if args.variant == "request_not_reached":
        variant_checks = {
            "voucher_remains_draft": int(
                boundary_evidence["landed_cost_voucher"].get("docstatus", 0)
            )
            == 0,
            "repost_owner_absent": not reposts,
            "attestation_absent": delivery is None,
        }
    elif args.variant == "voucher_committed_repost_queued_attestation_pending":
        variant_checks = {
            "voucher_submitted": int(
                boundary_evidence["landed_cost_voucher"].get("docstatus", 0)
            )
            == 1,
            "repost_owner_queued": statuses == {"queued"},
            "attestation_pending": delivery is None and bool(unfinished_jobs),
        }
    elif args.variant == "voucher_committed_repost_completed_attestation_pending":
        variant_checks = {
            "voucher_submitted": int(
                boundary_evidence["landed_cost_voucher"].get("docstatus", 0)
            )
            == 1,
            "repost_owner_queued": statuses == {"queued"},
            "attestation_pending": delivery is None and bool(unfinished_jobs),
        }
    else:
        variant_checks = {
            "voucher_submitted": int(
                boundary_evidence["landed_cost_voucher"].get("docstatus", 0)
            )
            == 1,
            "repost_owner_completed": statuses == {"completed"},
            "attestation_delivered_once": (
                isinstance(delivery, dict)
                and int(delivery.get("attempt_count", 0)) == 1
            ),
        }
    boundary_checks = {**common, **variant_checks}
    if not all(boundary_checks.values()):
        raise RuntimeError(f"invalid native boundary: {boundary_checks}")

    reference_trace: list[dict[str, Any]] = []
    reference_evaluation: dict[str, Any] | None = None
    if args.run_reference:
        reference_trace = list(
            reference_inventory_cost_recovery(
                adapter=adapter,
                collector=collector,
                stack=stack,
                worker_control=workers,
                prefix=prefix,
            )
        )
        final_evidence = collector.collect(prefix)
        reference_evaluation = evaluate_inventory_cost_terminal(
            final_evidence,
            prefix=prefix,
            fixture=scenario.raw["fixture"],
        )
    else:
        final_evidence = None
    report = {
        "schema_version": "0.1",
        "artifact_type": "erpnext_inventory_cost_native_boundary",
        "scenario_id": scenario.scenario_id,
        "variant": args.variant,
        "surface_error": surface_error,
        "latest_attempt": {
            "tool": "submit_document",
            "arguments": {
                "doctype": "Landed Cost Voucher",
                "name": prefix["landed_cost_voucher"],
            },
            "result": {
                "ok": False,
                "error": scenario.raw["ambiguous_operation"]["surface_result"],
            },
        },
        "gateway_events": _request_json("http://127.0.0.1:9091/audit"),
        "boundary_checks": boundary_checks,
        "dimension_projection": projection,
        "boundary_evidence": boundary_evidence,
        "native_state_sha256": _sha256(boundary_evidence),
        "replay_bound": True,
        "reference_trace": reference_trace,
        "final_evidence": final_evidence,
        "reference_evaluation": reference_evaluation,
        "reference_passed": bool(
            reference_evaluation and reference_evaluation.get("passed")
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "variant": args.variant,
                "boundary_checks": boundary_checks,
                "projection": projection,
                "reference_passed": report["reference_passed"],
                "reference_failures": (
                    reference_evaluation.get("failures", [])
                    if reference_evaluation
                    else []
                ),
            },
            indent=2,
        )
    )
    return 0 if (not args.run_reference or report["reference_passed"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
