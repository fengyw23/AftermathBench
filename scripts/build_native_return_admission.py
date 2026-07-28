from __future__ import annotations

import argparse
import itertools
import json
from pathlib import Path
from typing import Any, Callable


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


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


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build replay-derived admission artifacts."
    )
    parser.add_argument("--prefix", type=Path, required=True)
    parser.add_argument("--control-directory", type=Path, required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    args = parser.parse_args()
    prefix = _read(args.prefix)
    reports = [
        _read(path)
        for path in sorted(args.control_directory.glob("*-control.json"))
    ]
    if len(reports) != 4:
        raise RuntimeError(
            f"expected four control reports, found {len(reports)}"
        )
    reference = {
        "schema_version": "0.4",
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
    baseline_reports = []
    for path in sorted(
        args.control_directory.glob("*-baseline-*.json")
    ):
        report = _read(path)
        if "baseline" in report and "evaluation" in report:
            baseline_reports.append(report)
    baseline_names = sorted(
        {str(report["baseline"]) for report in baseline_reports}
    )
    variant_names = sorted(
        {str(report["variant"]) for report in baseline_reports}
    )
    if len(baseline_names) < 6 or len(variant_names) != 4:
        raise RuntimeError(
            "expected at least six executed baselines across four variants"
        )
    for baseline_name in baseline_names:
        covered = {
            str(report["variant"])
            for report in baseline_reports
            if report["baseline"] == baseline_name
        }
        if len(covered) != 4:
            raise RuntimeError(
                f"baseline {baseline_name!r} does not cover four variants"
            )
    failure_reports = [
        _read(path)
        for path in sorted(
            args.control_directory.glob("*-failure.json")
        )
        if "-baseline-" not in path.name
    ]
    if len(failure_reports) != 4:
        raise RuntimeError(
            f"expected four failure reports, found {len(failure_reports)}"
        )
    final_evidence = [report["final_evidence"] for report in reports]
    first_evidence = final_evidence[0]

    def every(predicate: Callable[[dict[str, Any]], bool]) -> bool:
        return all(predicate(evidence) for evidence in final_evidence)

    affected_invoice = prefix["affected_invoice"]
    unaffected_invoice = prefix["unaffected_invoice"]
    original_order = prefix["original_purchase_order"]
    original_receipt = prefix["original_purchase_receipt"]
    purchase_return = prefix["purchase_return"]
    debit_note = prefix["debit_note"]
    replacement_order = prefix["replacement_purchase_order"]
    replacement_receipt = prefix["replacement_purchase_receipt"]
    replacement_invoice = first_evidence["replacement_invoices"][0]["name"]
    pickup_jobs = [
        job
        for job in first_evidence["rq_jobs"]
        if _contains_reference(job, purchase_return)
    ]
    if not pickup_jobs:
        raise RuntimeError("reference replay did not produce a pickup job")
    pickup_job = pickup_jobs[0]["name"]

    entity_types = {
        "original_purchase_order": "Purchase Order",
        "original_purchase_receipt": "Purchase Receipt",
        "quality_inspection": "Quality Inspection",
        "affected_invoice": "Purchase Invoice",
        "unaffected_invoice": "Purchase Invoice",
        "shared_payment_entry": "Payment Entry",
        "purchase_return": "Purchase Receipt",
        "debit_note": "Purchase Invoice",
        "replacement_purchase_order": "Purchase Order",
        "replacement_purchase_receipt": "Purchase Receipt",
        "replacement_invoice": "Purchase Invoice",
        "return_stock_ledger": "Stock Ledger",
        "replacement_stock_ledger": "Stock Ledger",
        "payment_general_ledger": "General Ledger",
        "return_general_ledger": "General Ledger",
        "debit_general_ledger": "General Ledger",
        "pickup_job": "RQ Job",
        "pickup_delivery": "External Delivery",
    }
    native_names = {
        **{
            entity: prefix.get(entity)
            for entity in entity_types
        },
        "replacement_invoice": replacement_invoice,
        "return_stock_ledger": purchase_return,
        "replacement_stock_ledger": replacement_receipt,
        "payment_general_ledger": prefix["shared_payment_entry"],
        "return_general_ledger": purchase_return,
        "debit_general_ledger": debit_note,
        "pickup_job": pickup_job,
        "pickup_delivery": purchase_return,
    }
    relations = [
        (
            "original_purchase_order",
            "original_purchase_receipt",
            "fulfilled_by",
            every(lambda e: any(
                item.get("purchase_order") == original_order
                for item in e["original_purchase_receipt"]["items"]
            )),
            "original_purchase_receipt.items[].purchase_order",
        ),
        (
            "original_purchase_receipt",
            "affected_invoice",
            "billed_by",
            every(lambda e: any(
                item.get("purchase_receipt") == original_receipt
                for item in e["affected_invoice"]["items"]
            )),
            "affected_invoice.items[].purchase_receipt",
        ),
        (
            "original_purchase_receipt",
            "unaffected_invoice",
            "billed_by",
            every(lambda e: any(
                item.get("purchase_receipt") == original_receipt
                for item in e["unaffected_invoice"]["items"]
            )),
            "unaffected_invoice.items[].purchase_receipt",
        ),
        (
            "affected_invoice",
            "shared_payment_entry",
            "paid_by",
            every(lambda e: any(
                row.get("reference_name") == affected_invoice
                for row in e["shared_payment_entry"]["references"]
            )),
            "shared_payment_entry.references[].reference_name",
        ),
        (
            "unaffected_invoice",
            "shared_payment_entry",
            "paid_by",
            every(lambda e: any(
                row.get("reference_name") == unaffected_invoice
                for row in e["shared_payment_entry"]["references"]
            )),
            "shared_payment_entry.references[].reference_name",
        ),
        (
            "original_purchase_receipt",
            "quality_inspection",
            "inspected_by",
            every(lambda e: (
                e["quality_inspection"].get("reference_name")
                == original_receipt
            )),
            "quality_inspection.reference_name",
        ),
        (
            "quality_inspection",
            "purchase_return",
            "motivates",
            every(lambda e: (
                e["quality_inspection"].get("item_code")
                in {
                    item.get("item_code")
                    for item in e["purchase_returns"][0]["items"]
                }
            )),
            "quality_inspection.item_code + purchase_returns[0].items",
        ),
        (
            "original_purchase_receipt",
            "purchase_return",
            "returned_by",
            every(lambda e: (
                e["purchase_returns"][0].get("return_against")
                == original_receipt
            )),
            "purchase_returns[0].return_against",
        ),
        (
            "purchase_return",
            "return_stock_ledger",
            "posts",
            every(lambda e: any(
                row.get("voucher_no") == purchase_return
                for row in e["stock_ledger_entries"]
            )),
            "stock_ledger_entries[].voucher_no",
        ),
        (
            "purchase_return",
            "return_general_ledger",
            "posts",
            every(lambda e: any(
                row.get("voucher_no") == purchase_return
                for row in e["gl_entries"]
            )),
            "gl_entries[].voucher_no",
        ),
        (
            "affected_invoice",
            "debit_note",
            "credited_by",
            every(lambda e: (
                e["debit_notes"][0].get("return_against")
                == affected_invoice
            )),
            "debit_notes[0].return_against",
        ),
        (
            "debit_note",
            "debit_general_ledger",
            "posts",
            every(lambda e: any(
                row.get("voucher_no") == debit_note
                for row in e["gl_entries"]
            )),
            "gl_entries[].voucher_no",
        ),
        (
            "replacement_purchase_order",
            "replacement_purchase_receipt",
            "fulfilled_by",
            every(lambda e: any(
                item.get("purchase_order") == replacement_order
                for item in e["replacement_receipts"][0]["items"]
            )),
            "replacement_receipts[0].items[].purchase_order",
        ),
        (
            "replacement_purchase_receipt",
            "replacement_invoice",
            "billed_by",
            every(lambda e: any(
                item.get("purchase_receipt") == replacement_receipt
                for item in e["replacement_invoices"][0]["items"]
            )),
            "replacement_invoices[0].items[].purchase_receipt",
        ),
        (
            "replacement_purchase_receipt",
            "replacement_stock_ledger",
            "posts",
            every(lambda e: any(
                row.get("voucher_no") == replacement_receipt
                for row in e["stock_ledger_entries"]
            )),
            "stock_ledger_entries[].voucher_no",
        ),
        (
            "debit_note",
            "replacement_invoice",
            "reconciles_with",
            every(lambda e: (
                float(e["debit_notes"][0].get("outstanding_amount", 1))
                == 0
                and float(
                    e["replacement_invoices"][0].get(
                        "outstanding_amount",
                        1,
                    )
                )
                == 0
            )),
            "debit_notes[0].outstanding_amount + "
            "replacement_invoices[0].outstanding_amount",
        ),
        (
            "shared_payment_entry",
            "payment_general_ledger",
            "posts",
            every(lambda e: any(
                row.get("voucher_no") == prefix["shared_payment_entry"]
                for row in e["gl_entries"]
            )),
            "gl_entries[].voucher_no",
        ),
        (
            "purchase_return",
            "pickup_job",
            "enqueues",
            every(lambda e: any(
                _contains_reference(job, purchase_return)
                for job in e["rq_jobs"]
            )),
            "rq_jobs[].arguments",
        ),
        (
            "pickup_job",
            "pickup_delivery",
            "delivers",
            every(lambda e: (
                e["pickup_delivery"] is not None
                and e["pickup_delivery"].get("key") == purchase_return
                and any(
                    _contains_reference(job, purchase_return)
                    for job in e["rq_jobs"]
                )
            )),
            "rq_jobs[].arguments + pickup_delivery.key",
        ),
    ]
    missing_relations = [
        f"{source}->{target}:{relation_type}"
        for source, target, relation_type, observed, _ in relations
        if not observed
    ]
    if missing_relations:
        raise RuntimeError(
            f"native replay did not evidence relations: {missing_relations}"
        )
    boundary_rows = []
    for report in failure_reports:
        evidence = report["failure_boundary_evidence"]
        unfinished_jobs = [
            job
            for job in evidence["rq_jobs"]
            if _contains_reference(job, purchase_return)
            and str(job.get("status", "")).lower()
            in {"queued", "started", "failed", "deferred", "scheduled"}
        ]
        boundary_rows.append(
            {
                "variant": report["variant"],
                "signals": {
                    "purchase_return": int(
                        evidence["purchase_return"]["docstatus"]
                    ),
                    "external_delivery": (
                        evidence["pickup_delivery"] is not None
                    ),
                    "background_job": bool(unfinished_jobs),
                },
            }
        )
    boundary_signals = (
        "purchase_return",
        "external_delivery",
        "background_job",
    )
    minimum_boundary_queries = _minimum_distinguishing_signal_count(
        boundary_rows,
        boundary_signals,
    )
    graph = {
        "schema_version": "0.2",
        "scenario_id": prefix["scenario_id"],
        "source": "native prefix and reference replay projection",
        "entities": [
            {
                "id": entity,
                "type": entity_type,
                "native_name": native_names.get(entity),
            }
            for entity, entity_type in entity_types.items()
        ],
        "relations": [
            {
                "source": source,
                "target": target,
                "type": relation_type,
                "observed": observed,
                "evidence": citation,
            }
            for source, target, relation_type, observed, citation in relations
        ],
        "protected_effects": [
            "original_purchase_order",
            "original_purchase_receipt",
            "unaffected_invoice",
            "shared_payment_entry",
        ],
        "required_evidence_groups": [
            [
                "purchase_return",
                "quality_inspection",
                "replacement_purchase_receipt"
            ],
            [
                "return_stock_ledger",
                "payment_general_ledger",
                "debit_general_ledger"
            ],
            ["pickup_job", "pickup_delivery"]
        ],
        "boundary_signal_matrix": boundary_rows,
        "minimum_boundary_query_groups": minimum_boundary_queries,
        "single_query_decisive": minimum_boundary_queries == 1,
        "unsafe_actions": [
            "resubmit a committed Purchase Return",
            "return the unaffected item quantity",
            "cancel the shared Payment Entry",
            "create a duplicate replacement receipt",
            "enqueue a duplicate pickup delivery"
        ]
    }
    heuristics = []
    for baseline_name in baseline_names:
        baseline_group = [
            report
            for report in baseline_reports
            if report["baseline"] == baseline_name
        ]
        passed = [
            bool(report["evaluation"]["passed"])
            for report in baseline_group
        ]
        heuristics.append(
            {
                "name": baseline_name,
                "pass_rate": sum(passed) / len(passed),
                "matched_group_success": all(passed),
                "reports": [
                    {
                        "variant": report["variant"],
                        "passed": report["evaluation"]["passed"],
                    }
                    for report in baseline_group
                ],
            }
        )
    baselines = {
        "schema_version": "0.2",
        "scenario_id": prefix["scenario_id"],
        "source": "executed native terminal-state evaluations",
        "heuristics": heuristics,
    }
    args.output_directory.mkdir(parents=True, exist_ok=True)
    for name, payload in (
        ("reference.json", reference),
        ("observed_graph.json", graph),
        ("baselines.json", baselines),
    ):
        (args.output_directory / name).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
