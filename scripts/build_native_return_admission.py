from __future__ import annotations

import argparse
import json
from pathlib import Path


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


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
    relations = [
        ("original_purchase_order", "original_purchase_receipt", "fulfilled_by"),
        ("original_purchase_receipt", "affected_invoice", "billed_by"),
        ("original_purchase_receipt", "unaffected_invoice", "billed_by"),
        ("affected_invoice", "shared_payment_entry", "paid_by"),
        ("unaffected_invoice", "shared_payment_entry", "paid_by"),
        ("original_purchase_receipt", "quality_inspection", "inspected_by"),
        ("quality_inspection", "purchase_return", "motivates"),
        ("original_purchase_receipt", "purchase_return", "returned_by"),
        ("purchase_return", "return_stock_ledger", "posts"),
        ("purchase_return", "return_general_ledger", "posts"),
        ("affected_invoice", "debit_note", "credited_by"),
        ("debit_note", "debit_general_ledger", "posts"),
        ("replacement_purchase_order", "replacement_purchase_receipt", "fulfilled_by"),
        ("replacement_purchase_receipt", "replacement_invoice", "billed_by"),
        ("replacement_purchase_receipt", "replacement_stock_ledger", "posts"),
        ("debit_note", "replacement_invoice", "reconciles_with"),
        ("shared_payment_entry", "payment_general_ledger", "posts"),
        ("purchase_return", "pickup_job", "enqueues"),
        ("pickup_job", "pickup_delivery", "delivers"),
    ]
    graph = {
        "schema_version": "0.2",
        "scenario_id": prefix["scenario_id"],
        "source": "native prefix and reference replay projection",
        "entities": [
            {
                "id": entity,
                "type": entity_type,
                "native_name": prefix.get(entity),
            }
            for entity, entity_type in entity_types.items()
        ],
        "relations": [
            {"source": source, "target": target, "type": relation_type}
            for source, target, relation_type in relations
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
        "single_query_decisive": False,
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
