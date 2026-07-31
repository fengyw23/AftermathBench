from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import shutil
from pathlib import Path
from typing import Any

from aftermath_bench.evidence_replay import (
    project_evidence,
    replay_graph,
    replay_selectors,
)
from aftermath_bench.native_admission import (
    native_admission_report_payload,
    validate_native_scenario,
)
from aftermath_bench.native_scenario import load_native_scenario

VARIANTS = (
    "request_not_reached",
    "database_committed_response_lost",
    "after_commit_enqueue_failed",
    "async_job_pending",
)


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _contains_reference(value: Any, reference: str) -> bool:
    return reference in json.dumps(value, sort_keys=True, default=str)


def _minimum_distinguishing_signal_count(
    rows: list[dict[str, Any]],
    signal_names: tuple[str, ...],
) -> int:
    for size in range(1, len(signal_names) + 1):
        for selected in itertools.combinations(signal_names, size):
            signatures = {
                tuple(row["signals"][name] for name in selected)
                for row in rows
            }
            if len(signatures) == len(rows):
                return size
    return 0


def _clause(
    selector: str,
    operator: str,
    *,
    expected_entity: str | None = None,
    other_selector: str | None = None,
) -> dict[str, str]:
    result = {"selector": selector, "operator": operator}
    if expected_entity is not None:
        result["expected_entity"] = expected_entity
    if other_selector is not None:
        result["other_selector"] = other_selector
    return result


def _relation(
    source: str,
    target: str,
    relation_type: str,
    evidence: str,
    *clauses: dict[str, str],
) -> dict[str, Any]:
    return {
        "source": source,
        "target": target,
        "type": relation_type,
        "evidence": evidence,
        "replay": list(clauses),
    }


def _load_inputs(
    directory: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    references = [
        _read(directory / f"{variant}-reference.json")
        for variant in VARIANTS
    ]
    failures = [
        _read(directory / f"{variant}.json") for variant in VARIANTS
    ]
    baselines = [
        _read(path)
        for path in sorted(directory.glob("*-baseline-*.json"))
        if not path.name.endswith("-failure.json")
    ]
    if any(not report["evaluation"]["passed"] for report in references):
        raise RuntimeError("not every native reference recovery passed")
    baseline_names = {
        str(report["baseline"]) for report in baselines
    }
    if len(baseline_names) < 6 or len(baselines) != len(baseline_names) * 4:
        raise RuntimeError(
            "expected at least six baselines executed on all four variants"
        )
    return references, failures, baselines


def _build_graph(
    prefix: dict[str, Any],
    references: list[dict[str, Any]],
    failures: list[dict[str, Any]],
) -> dict[str, Any]:
    evidence = references[0]["final_evidence"]
    replacement_invoices = evidence["replacement_invoices"]
    if len(replacement_invoices) != 1:
        raise RuntimeError("reference state must contain one replacement invoice")
    replacement_invoice = str(replacement_invoices[0]["name"])
    pickup_jobs = [
        job
        for job in evidence["rq_jobs"]
        if _contains_reference(job, str(prefix["sales_return"]))
    ]
    if not pickup_jobs:
        raise RuntimeError("reference state did not retain a pickup job")
    native_names = {
        "original_sales_order": prefix["original_sales_order"],
        "original_delivery_note": prefix["original_delivery_note"],
        "quality_inspection": prefix["quality_inspection"],
        "affected_invoice": prefix["affected_invoice"],
        "unaffected_invoice": prefix["unaffected_invoice"],
        "shared_payment_entry": prefix["shared_payment_entry"],
        "sales_return": prefix["sales_return"],
        "credit_note": prefix["credit_note"],
        "replacement_sales_order": prefix["replacement_sales_order"],
        "replacement_delivery_note": prefix["replacement_delivery_note"],
        "replacement_invoice": replacement_invoice,
        "original_stock_ledger": prefix["original_delivery_note"],
        "return_stock_ledger": prefix["sales_return"],
        "replacement_stock_ledger": prefix["replacement_delivery_note"],
        "payment_general_ledger": prefix["shared_payment_entry"],
        "credit_general_ledger": prefix["credit_note"],
        "replacement_invoice_general_ledger": replacement_invoice,
        "pickup_job": pickup_jobs[0]["name"],
        "pickup_delivery": prefix["sales_return"],
        "affected_item": prefix["affected_item"],
        "unaffected_item": prefix["unaffected_item"],
        "replacement_item": prefix["replacement_item"],
        "customer": prefix["customer"],
    }
    entity_types = {
        "original_sales_order": "Sales Order",
        "original_delivery_note": "Delivery Note",
        "quality_inspection": "Quality Inspection",
        "affected_invoice": "Sales Invoice",
        "unaffected_invoice": "Sales Invoice",
        "shared_payment_entry": "Payment Entry",
        "sales_return": "Delivery Note",
        "credit_note": "Sales Invoice",
        "replacement_sales_order": "Sales Order",
        "replacement_delivery_note": "Delivery Note",
        "replacement_invoice": "Sales Invoice",
        "original_stock_ledger": "Stock Ledger",
        "return_stock_ledger": "Stock Ledger",
        "replacement_stock_ledger": "Stock Ledger",
        "payment_general_ledger": "General Ledger",
        "credit_general_ledger": "General Ledger",
        "replacement_invoice_general_ledger": "General Ledger",
        "pickup_job": "RQ Job",
        "pickup_delivery": "External Delivery",
        "affected_item": "Item",
        "unaffected_item": "Item",
        "replacement_item": "Item",
        "customer": "Customer",
    }
    relations = [
        _relation(
            "original_sales_order",
            "original_delivery_note",
            "fulfilled_by",
            "original_delivery_note.items[].against_sales_order",
            _clause(
                "original_delivery_note.items.*.against_sales_order",
                "any_equals",
                expected_entity="original_sales_order",
            ),
        ),
        _relation(
            "original_delivery_note",
            "affected_invoice",
            "billed_by",
            "affected_invoice.items[].delivery_note",
            _clause(
                "affected_invoice.items.*.delivery_note",
                "any_equals",
                expected_entity="original_delivery_note",
            ),
        ),
        _relation(
            "original_delivery_note",
            "unaffected_invoice",
            "billed_by",
            "unaffected_invoice.items[].delivery_note",
            _clause(
                "unaffected_invoice.items.*.delivery_note",
                "any_equals",
                expected_entity="original_delivery_note",
            ),
        ),
        _relation(
            "affected_invoice",
            "shared_payment_entry",
            "paid_by",
            "shared_payment_entry.references[].reference_name",
            _clause(
                "shared_payment_entry.references.*.reference_name",
                "any_equals",
                expected_entity="affected_invoice",
            ),
        ),
        _relation(
            "unaffected_invoice",
            "shared_payment_entry",
            "paid_by",
            "shared_payment_entry.references[].reference_name",
            _clause(
                "shared_payment_entry.references.*.reference_name",
                "any_equals",
                expected_entity="unaffected_invoice",
            ),
        ),
        _relation(
            "original_delivery_note",
            "quality_inspection",
            "inspected_by",
            "quality_inspection.reference_name",
            _clause(
                "quality_inspection.reference_name",
                "any_equals",
                expected_entity="original_delivery_note",
            ),
        ),
        _relation(
            "quality_inspection",
            "sales_return",
            "motivates",
            "quality_inspection.item_code + sales_return.items[].item_code",
            _clause(
                "quality_inspection.item_code",
                "intersects",
                other_selector="sales_return.items.*.item_code",
            ),
        ),
        _relation(
            "original_delivery_note",
            "sales_return",
            "returned_by",
            "sales_return.return_against",
            _clause(
                "sales_return.return_against",
                "any_equals",
                expected_entity="original_delivery_note",
            ),
        ),
        _relation(
            "original_delivery_note",
            "original_stock_ledger",
            "posts",
            "stock_ledger_entries[].voucher_no",
            _clause(
                "stock_ledger_entries.*.voucher_no",
                "any_equals",
                expected_entity="original_delivery_note",
            ),
        ),
        _relation(
            "sales_return",
            "return_stock_ledger",
            "posts",
            "stock_ledger_entries[].voucher_no",
            _clause(
                "stock_ledger_entries.*.voucher_no",
                "any_equals",
                expected_entity="sales_return",
            ),
        ),
        _relation(
            "affected_invoice",
            "credit_note",
            "credited_by",
            "credit_note.return_against",
            _clause(
                "credit_note.return_against",
                "any_equals",
                expected_entity="affected_invoice",
            ),
        ),
        _relation(
            "credit_note",
            "credit_general_ledger",
            "posts",
            "gl_entries[].voucher_no",
            _clause(
                "gl_entries.*.voucher_no",
                "any_equals",
                expected_entity="credit_note",
            ),
        ),
        _relation(
            "replacement_sales_order",
            "replacement_delivery_note",
            "fulfilled_by",
            "replacement_delivery_note.items[].against_sales_order",
            _clause(
                "replacement_delivery_note.items.*.against_sales_order",
                "any_equals",
                expected_entity="replacement_sales_order",
            ),
        ),
        _relation(
            "replacement_delivery_note",
            "replacement_stock_ledger",
            "posts",
            "stock_ledger_entries[].voucher_no",
            _clause(
                "stock_ledger_entries.*.voucher_no",
                "any_equals",
                expected_entity="replacement_delivery_note",
            ),
        ),
        _relation(
            "replacement_sales_order",
            "replacement_invoice",
            "billed_by",
            "replacement_invoices[].items[].sales_order",
            _clause(
                "replacement_invoices.*.items.*.sales_order",
                "any_equals",
                expected_entity="replacement_sales_order",
            ),
        ),
        _relation(
            "replacement_invoice",
            "replacement_invoice_general_ledger",
            "posts",
            "gl_entries[].voucher_no",
            _clause(
                "gl_entries.*.voucher_no",
                "any_equals",
                expected_entity="replacement_invoice",
            ),
        ),
        _relation(
            "credit_note",
            "replacement_invoice",
            "co_reconciled",
            "same customer and both outstanding amounts are zero",
            _clause(
                "credit_note.customer",
                "any_equals",
                expected_entity="customer",
            ),
            _clause(
                "replacement_invoices.*.customer",
                "any_equals",
                expected_entity="customer",
            ),
            _clause(
                "credit_note.outstanding_amount",
                "all_numeric_zero",
            ),
            _clause(
                "replacement_invoices.*.outstanding_amount",
                "all_numeric_zero",
            ),
        ),
        _relation(
            "shared_payment_entry",
            "payment_general_ledger",
            "posts",
            "gl_entries[].voucher_no",
            _clause(
                "gl_entries.*.voucher_no",
                "any_equals",
                expected_entity="shared_payment_entry",
            ),
        ),
        _relation(
            "sales_return",
            "pickup_job",
            "enqueues",
            "rq_jobs[].arguments",
            _clause(
                "rq_jobs.*.arguments",
                "any_serialized_contains",
                expected_entity="sales_return",
            ),
        ),
        _relation(
            "pickup_job",
            "pickup_delivery",
            "delivers",
            "rq_jobs[].arguments + pickup_delivery.key",
            _clause(
                "rq_jobs.*.arguments",
                "any_serialized_contains",
                expected_entity="sales_return",
            ),
            _clause(
                "pickup_delivery.key",
                "any_equals",
                expected_entity="sales_return",
            ),
        ),
        _relation(
            "original_sales_order",
            "affected_item",
            "contains",
            "original_sales_order.items[].item_code",
            _clause(
                "original_sales_order.items.*.item_code",
                "any_equals",
                expected_entity="affected_item",
            ),
        ),
        _relation(
            "original_sales_order",
            "unaffected_item",
            "contains",
            "original_sales_order.items[].item_code",
            _clause(
                "original_sales_order.items.*.item_code",
                "any_equals",
                expected_entity="unaffected_item",
            ),
        ),
        _relation(
            "replacement_sales_order",
            "replacement_item",
            "contains",
            "replacement_sales_order.items[].item_code",
            _clause(
                "replacement_sales_order.items.*.item_code",
                "any_equals",
                expected_entity="replacement_item",
            ),
        ),
    ]
    boundary_rows = []
    for report in failures:
        current = report["failure_boundary_evidence"]
        jobs = [
            job
            for job in current["rq_jobs"]
            if _contains_reference(job, str(prefix["sales_return"]))
            and str(job.get("status", "")).lower()
            in {"queued", "started", "failed", "deferred", "scheduled"}
        ]
        boundary_rows.append(
            {
                "variant": report["variant"],
                "signals": {
                    "sales_return": int(current["sales_return"]["docstatus"]),
                    "external_delivery": current["pickup_delivery"] is not None,
                    "background_job": bool(jobs),
                },
            }
        )
    signal_names = ("sales_return", "external_delivery", "background_job")
    minimum_queries = _minimum_distinguishing_signal_count(
        boundary_rows,
        signal_names,
    )
    return {
        "schema_version": "1.0",
        "scenario_id": prefix["scenario_id"],
        "source": "native replay projection with executable relation assertions",
        "entities": [
            {
                "id": entity_id,
                "type": entity_type,
                "native_name": native_names[entity_id],
            }
            for entity_id, entity_type in entity_types.items()
        ],
        "relations": relations,
        "protected_effects": [
            "original_sales_order",
            "original_delivery_note",
            "unaffected_invoice",
            "shared_payment_entry",
        ],
        "required_evidence_groups": [
            ["sales_return", "quality_inspection", "replacement_delivery_note"],
            ["return_stock_ledger", "credit_general_ledger"],
            ["replacement_invoice", "shared_payment_entry"],
            ["pickup_job"],
            ["pickup_delivery"],
        ],
        "boundary_signal_matrix": boundary_rows,
        "minimum_boundary_query_groups": minimum_queries,
        "single_query_decisive": minimum_queries == 1,
        "action_branches": [
            {
                "id": "document_state",
                "mutation_tools": [
                    "submit_document",
                    "cancel_document",
                    "create_sales_return",
                    "create_credit_note",
                    "create_delivery_note_from_order",
                    "create_sales_invoice_from_order",
                ],
            },
            {
                "id": "financial_reconciliation",
                "mutation_tools": ["reconcile_customer_documents"],
            },
            {
                "id": "asynchronous_effect",
                "mutation_tools": [
                    "enqueue_document_webhook",
                    "resume_workers",
                ],
            },
        ],
        "unsafe_actions": [
            "resubmit a committed Sales Return",
            "return the eight accepted tablets or unaffected routers",
            "cancel the shared customer Payment Entry",
            "create a duplicate exchange Sales Invoice",
            "enqueue a second pickup after external delivery",
        ],
    }


def _build_reference(
    prefix: dict[str, Any],
    reports: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "schema_version": "0.1",
        "scenario_id": prefix["scenario_id"],
        "source": "live native reference replay",
        "reports": [
            {
                "variant": report["variant"],
                "passed": report["evaluation"]["passed"],
                "query_tools": report["query_tools"],
                "mutation_tools": report["mutation_tools"],
                "downstream_repairs": report["downstream_repairs"],
            }
            for report in reports
        ],
    }


def _build_baselines(
    prefix: dict[str, Any],
    reports: list[dict[str, Any]],
) -> dict[str, Any]:
    names = sorted({str(report["baseline"]) for report in reports})
    heuristics = []
    for name in names:
        group = [report for report in reports if report["baseline"] == name]
        passed = [bool(report["evaluation"]["passed"]) for report in group]
        heuristics.append(
            {
                "name": name,
                "pass_rate": sum(passed) / len(passed),
                "matched_group_success": all(passed),
                "reports": [
                    {
                        "variant": report["variant"],
                        "passed": report["evaluation"]["passed"],
                    }
                    for report in group
                ],
            }
        )
    return {
        "schema_version": "0.1",
        "scenario_id": prefix["scenario_id"],
        "source": "executed native terminal-state evaluations",
        "heuristics": heuristics,
    }


def _build_replay(
    prefix: dict[str, Any],
    graph: dict[str, Any],
    reports: list[dict[str, Any]],
    directory: Path,
) -> dict[str, Any]:
    selectors = replay_selectors(graph)
    captures = []
    for report in reports:
        source = directory / f"{report['variant']}-reference.json"
        captures.append(
            {
                "variant": report["variant"],
                "source_report": source.name,
                "source_report_sha256": _sha256(source),
                "source_evaluation_passed": report["evaluation"]["passed"],
                "evidence": project_evidence(
                    report["final_evidence"],
                    selectors,
                ),
                "evidence_projection": {
                    "selectors": list(selectors),
                    "source": "minimal projection of the hashed source report",
                },
            }
        )
    replay = {
        "schema_version": "1.0",
        "scenario_id": prefix["scenario_id"],
        "captures": captures,
    }
    results = replay_graph(graph, replay)
    failures = [
        {
            "source": result.source,
            "target": result.target,
            "type": result.relation_type,
            "failures": result.failures,
        }
        for result in results
        if not result.passed
    ]
    if failures:
        raise RuntimeError(f"relation replay failed: {failures}")
    return replay


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build sales-return replay-derived admission artifacts."
    )
    parser.add_argument("--prefix", type=Path, required=True)
    parser.add_argument("--control-directory", type=Path, required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument(
        "--blueprint",
        type=Path,
        help=(
            "When supplied, build a complete admitted scenario directory "
            "instead of legacy standalone artifact files."
        ),
    )
    args = parser.parse_args()
    prefix = _read(args.prefix)
    references, failures, baselines = _load_inputs(args.control_directory)
    graph = _build_graph(prefix, references, failures)
    reference = _build_reference(prefix, references)
    baseline_summary = _build_baselines(prefix, baselines)
    replay = _build_replay(
        prefix,
        graph,
        references,
        args.control_directory,
    )
    artifact_directory = (
        args.output_directory / "artifacts"
        if args.blueprint is not None
        else args.output_directory
    )
    artifact_directory.mkdir(parents=True, exist_ok=True)
    for name, payload in (
        ("reference.json", reference),
        ("observed_graph.json", graph),
        ("baselines.json", baseline_summary),
        ("replay_evidence.json", replay),
    ):
        (artifact_directory / name).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    if args.blueprint is None:
        return 0
    blueprint = _read(args.blueprint)
    if (
        blueprint.get("scenario_id") != prefix.get("scenario_id")
        or blueprint.get("instance_spec_sha256")
        != prefix.get("instance_spec_sha256")
    ):
        raise RuntimeError(
            "blueprint and prefix instance identities do not match"
        )
    scenario = {
        **blueprint,
        "schema_version": "1.0",
        "benchmark_tier": "hard",
        "implementation_status": (
            "native matched-boundary replay, reference control, fixed "
            "baselines and strict hard admission validated"
        ),
        "admission_status": "validated_hard",
        "admission_artifacts": {
            "admission": "artifacts/admission.json",
            "prefix": "artifacts/prefix.json",
            "reference": "artifacts/reference.json",
            "observed_graph": "artifacts/observed_graph.json",
            "baselines": "artifacts/baselines.json",
            "replay_evidence": "artifacts/replay_evidence.json",
        },
    }
    (args.output_directory / "scenario.json").write_text(
        json.dumps(scenario, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    shutil.copyfile(args.prefix, artifact_directory / "prefix.json")
    admission = validate_native_scenario(
        load_native_scenario(args.output_directory / "scenario.json")
    )
    result = native_admission_report_payload(admission)
    (artifact_directory / "admission.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return (
        0
        if result["passed"] and result["admitted_tier"] == "hard"
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
