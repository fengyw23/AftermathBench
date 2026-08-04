from __future__ import annotations

import argparse
import json
import os
import time
import urllib.request
from pathlib import Path
from typing import Any

from aftermath_bench.integrations.erpnext_faults import (
    ERPNextFaultController,
    default_worker_control,
)
from aftermath_bench.integrations.erpnext_shared_batch_evaluator import (
    shared_batch_document_fingerprint,
)
from aftermath_bench.integrations.erpnext_shared_batch_evidence import (
    ERPNextSharedBatchEvidenceCollector,
)
from aftermath_bench.integrations.erpnext_stack import ERPNextStack
from aftermath_bench.integrations.frappe import FrappeConfig, FrappeHTTPAdapter
from aftermath_bench.schema import repository_root


SHARED_BATCH_VARIANTS = {
    "request_not_reached": "request_not_reached",
    "job_card_committed_certificate_delivered_response_lost": (
        "database_committed_response_lost"
    ),
    "job_card_committed_certificate_enqueue_failed": "after_commit_enqueue_failed",
    "job_card_committed_certificate_job_pending": "async_job_pending",
}


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


def ensure_native_pending_certificate_job(
    public_variant: str,
    evidence: dict[str, Any],
    prefix: dict[str, Any],
    stack: ERPNextStack,
) -> dict[str, Any] | None:
    """Materialize the native pending-job boundary when the hook races.

    ERPNext normally enqueues the configured Webhook in an after-commit
    callback.  Across repeated database/Redis bundle restores, that callback
    can occasionally leave no queue record even though the Job Card commit
    succeeded.  The pending-job variant is only admissible when a real Frappe
    RQ job exists, so use the same public native enqueue primitive exposed to
    the agent, and only when the automatic hook produced no matching job.
    Workers remain stopped, making the resulting queue state deterministic.
    """

    if public_variant != "job_card_committed_certificate_job_pending":
        return None
    reference = str(prefix["corrective_job_card"])
    if _unfinished_jobs(evidence, reference):
        return {"action": "automatic_hook_observed"}
    result = stack.enqueue_document_webhook(
        doctype="Job Card",
        document_name=reference,
        webhook_name=str(prefix["certificate_webhook"]),
    )
    return {"action": "native_enqueue_replayed", "result": result}


def collect_shared_batch_boundary(
    public_variant: str,
    collector: ERPNextSharedBatchEvidenceCollector,
    prefix: dict[str, Any],
    *,
    timeout_seconds: float = 30,
) -> dict[str, Any]:
    evidence = collector.collect(prefix)
    if public_variant not in {
        "job_card_committed_certificate_delivered_response_lost",
        "job_card_committed_certificate_job_pending",
    }:
        return evidence
    deadline = time.monotonic() + timeout_seconds
    reference = str(prefix["corrective_job_card"])
    while time.monotonic() < deadline:
        jobs = _unfinished_jobs(evidence, reference)
        if public_variant == "job_card_committed_certificate_delivered_response_lost":
            ready = evidence.get("certificate_delivery") is not None and not jobs
        else:
            ready = evidence.get("certificate_delivery") is None and bool(jobs)
        if ready:
            break
        time.sleep(0.5)
        evidence = collector.collect(prefix)
    return evidence


def validate_shared_batch_boundary(
    public_variant: str,
    evidence: dict[str, Any],
    prefix: dict[str, Any],
    gateway_events: list[dict[str, Any]],
) -> dict[str, Any]:
    corrective = evidence["corrective_job_card"]
    submitted = int(corrective.get("docstatus", 0)) == 1
    jobs = _unfinished_jobs(evidence, str(prefix["corrective_job_card"]))
    delivery = evidence.get("certificate_delivery")
    final_entries = [
        document
        for document in evidence.get("manufacture_stock_entries", [])
        if str(document.get("work_order")) == str(prefix["primary_work_order"])
        and str(document.get("purpose")) == "Manufacture"
        and str(document.get("name")) != str(prefix["accepted_primary_manufacture"])
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
    protected_documents = {
        "shared_purchase_receipt": evidence["shared_purchase_receipt"],
        "primary_bom": evidence["primary_bom"],
        "secondary_bom": evidence["secondary_bom"],
        "primary_transfer": evidence["primary_transfer"],
        "secondary_transfer": evidence["secondary_transfer"],
        "primary_material_quality_inspection": evidence[
            "primary_material_quality_inspection"
        ],
        "secondary_material_quality_inspection": evidence[
            "secondary_material_quality_inspection"
        ],
        "accepted_primary_job_card": evidence["accepted_primary_job_card"],
        "rejected_primary_job_card": evidence["rejected_primary_job_card"],
        "secondary_job_card": evidence["secondary_job_card"],
        "accepted_primary_quality_inspection": evidence[
            "accepted_primary_quality_inspection"
        ],
        "rejected_quality_inspection": evidence["rejected_quality_inspection"],
        "secondary_quality_inspection": evidence["secondary_quality_inspection"],
        "accepted_primary_manufacture": evidence["accepted_primary_manufacture"],
        "secondary_manufacture": evidence["secondary_manufacture"],
        "customer_reservation": evidence["customer_reservation"],
        "shared_landed_cost_voucher": evidence["shared_landed_cost_voucher"],
        "unrelated_receipt": evidence["unrelated_receipt"],
    }
    fingerprints = {
        key: shared_batch_document_fingerprint(document)
        for key, document in protected_documents.items()
    }
    checks = {
        "one_submit_attempt_audited": len(submit_events) == 1,
        "surface_result_hidden": gateway.get("outcome")
        in {"request_suppressed", "upstream_completed_response_dropped"},
        "accepted_primary_output_preserved": (
            int(evidence["accepted_primary_manufacture"].get("docstatus", 0)) == 1
            and float(evidence["primary_work_order"].get("produced_qty", 0))
            == float(prefix["accepted_quantity"])
        ),
        "secondary_output_preserved": (
            int(evidence["secondary_manufacture"].get("docstatus", 0)) == 1
            and float(evidence["secondary_work_order"].get("produced_qty", 0))
            == float(prefix["secondary_quantity"])
        ),
        "customer_reservation_preserved": (
            int(evidence["stock_reservation_entry"].get("docstatus", 0)) == 1
            and float(evidence["stock_reservation_entry"].get("reserved_qty", 0))
            == float(prefix["secondary_quantity"])
        ),
        "landed_cost_and_protected_documents_preserved": (
            fingerprints == prefix["protected_fingerprints"]
        ),
        "corrective_manufacture_not_started": not final_entries,
    }
    if public_variant == "request_not_reached":
        checks.update(
            {
                "corrective_job_remains_draft": not submitted,
                "corrective_cost_not_posted": float(
                    evidence["primary_work_order"].get("corrective_operation_cost", 0)
                )
                == 0,
                "certificate_not_delivered": delivery is None,
                "certificate_not_queued": not jobs,
                "request_never_reached_upstream": (
                    gateway.get("outcome") == "request_suppressed"
                    and gateway.get("upstream_status") is None
                ),
            }
        )
    else:
        checks.update(
            {
                "corrective_job_committed": submitted,
                "corrective_cost_posted": float(
                    evidence["primary_work_order"].get("corrective_operation_cost", 0)
                )
                == float(prefix["expected_corrective_operation_cost"]),
                "upstream_completed": (
                    gateway.get("outcome") == "upstream_completed_response_dropped"
                    and gateway.get("upstream_status") is not None
                ),
            }
        )
        if public_variant == "job_card_committed_certificate_delivered_response_lost":
            checks.update(
                {
                    "certificate_delivered": delivery is not None,
                    "certificate_jobs_settled": not jobs,
                }
            )
        elif public_variant == "job_card_committed_certificate_enqueue_failed":
            checks.update(
                {
                    "certificate_not_delivered": delivery is None,
                    "certificate_not_queued": not jobs,
                }
            )
        else:
            checks.update(
                {
                    "certificate_not_delivered": delivery is None,
                    "certificate_job_pending": bool(jobs),
                }
            )
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "failures": [name for name, passed in checks.items() if not passed],
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Inject one shared-batch corrective Job Card fault."
    )
    parser.add_argument(
        "--variant", choices=tuple(SHARED_BATCH_VARIANTS), required=True
    )
    parser.add_argument("--prefix", type=Path, required=True)
    parser.add_argument("--snapshot-bundle", type=Path, required=True)
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
    stack.restore_bundle(args.snapshot_bundle)
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
    fault_variant = SHARED_BATCH_VARIANTS[args.variant]
    fault = ERPNextFaultController(
        worker_control=default_worker_control(root, container_cli=args.container_cli)
    )
    fault.arm(fault_variant)
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
        fault.disarm_transport_after_failure(fault_variant)

    gateway_events = _request_json("http://127.0.0.1:9091/audit").get("events", [])
    collector = ERPNextSharedBatchEvidenceCollector(adapter)
    pre_normalization_evidence = collector.collect(prefix)
    boundary_normalization = ensure_native_pending_certificate_job(
        args.variant,
        pre_normalization_evidence,
        prefix,
        stack,
    )
    evidence = collect_shared_batch_boundary(
        args.variant,
        collector,
        prefix,
    )
    validation = validate_shared_batch_boundary(
        args.variant, evidence, prefix, gateway_events
    )
    report = {
        "schema_version": "0.1",
        "artifact_type": "erpnext_shared_batch_failure_boundary",
        "scenario_id": prefix["scenario_id"],
        "variant": args.variant,
        "fault_variant": fault_variant,
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
        "boundary_normalization": boundary_normalization,
        "boundary_evidence": evidence,
        "boundary_validation": validation,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"variant": args.variant, **validation}, indent=2))
    return 0 if validation["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
