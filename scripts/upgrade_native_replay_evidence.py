from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _replay_clauses(relation: dict[str, Any]) -> list[dict[str, Any]]:
    source = str(relation["source"])
    target = str(relation["target"])
    relation_type = str(relation["type"])
    target_selector = (
        "replacement_invoices.*"
        if target == "replacement_invoice"
        else target
    )
    if relation_type == "fulfilled_by":
        return [{
            "selector": f"{target}.items.*.purchase_order",
            "operator": "any_equals",
            "expected_entity": source,
        }]
    if relation_type == "billed_by":
        return [{
            "selector": f"{target_selector}.items.*.purchase_receipt",
            "operator": "any_equals",
            "expected_entity": source,
        }]
    if relation_type == "paid_by":
        return [{
            "selector": f"{target}.references.*.reference_name",
            "operator": "any_equals",
            "expected_entity": source,
        }]
    if relation_type == "inspected_by":
        return [{
            "selector": f"{target}.reference_name",
            "operator": "any_equals",
            "expected_entity": source,
        }]
    if relation_type == "motivates":
        return [{
            "selector": f"{source}.item_code",
            "operator": "intersects",
            "other_selector": f"{target}.items.*.item_code",
        }]
    if relation_type in {"returned_by", "credited_by"}:
        return [{
            "selector": f"{target}.return_against",
            "operator": "any_equals",
            "expected_entity": source,
        }]
    if relation_type == "posts":
        ledger = (
            "stock_ledger_entries"
            if "stock_ledger" in target
            else "gl_entries"
        )
        return [{
            "selector": f"{ledger}.*.voucher_no",
            "operator": "any_equals",
            "expected_entity": source,
        }]
    if relation_type == "reconciles_with":
        return [
            {
                "selector": f"{source}.outstanding_amount",
                "operator": "all_numeric_zero",
            },
            {
                "selector": f"{target_selector}.outstanding_amount",
                "operator": "any_numeric_zero",
            },
        ]
    if relation_type == "enqueues":
        return [{
            "selector": "rq_jobs.*",
            "operator": "any_serialized_contains",
            "expected_entity": source,
        }]
    if relation_type == "delivers":
        return [
            {
                "selector": "rq_jobs.*",
                "operator": "nonempty",
            },
            {
                "selector": "pickup_delivery",
                "operator": "nonempty",
            },
        ]
    if relation_type == "ordered_in":
        return [{
            "selector": f"{target}.items.*.item_code",
            "operator": "any_equals",
            "expected_entity": source,
        }]
    if relation_type == "inspected_as":
        return [{
            "selector": f"{target}.item_code",
            "operator": "any_equals",
            "expected_entity": source,
        }]
    raise ValueError(f"no replay mapping for relation type {relation_type}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", type=Path, required=True)
    parser.add_argument(
        "--source-report",
        type=Path,
        action="append",
        required=True,
        help="One live native report per matched variant.",
    )
    args = parser.parse_args()
    scenario = _read(args.scenario)
    scenario_dir = args.scenario.parent
    graph_path = scenario_dir / scenario["admission_artifacts"][
        "observed_graph"
    ]
    graph = _read(graph_path)
    prefix_path = scenario_dir / scenario["admission_artifacts"]["prefix"]
    prefix = _read(prefix_path)
    reports = [_read(path) for path in args.source_report]
    expected = {
        str(item["id"]) for item in scenario["matched_variants"]
    }
    observed = {str(report["variant"]) for report in reports}
    if observed != expected:
        raise RuntimeError(
            f"variant coverage mismatch: {sorted(observed)} != "
            f"{sorted(expected)}"
        )
    entity_ids = {str(entity["id"]) for entity in graph["entities"]}
    for entity_id in (
        "affected_item",
        "unaffected_item",
        "replacement_item",
    ):
        if entity_id not in entity_ids:
            graph["entities"].append(
                {
                    "id": entity_id,
                    "type": "Item",
                    "native_name": prefix[entity_id],
                }
            )
    relation_keys = {
        (
            str(relation["source"]),
            str(relation["target"]),
            str(relation["type"]),
        )
        for relation in graph["relations"]
    }
    item_relations = (
        ("affected_item", "original_purchase_order", "ordered_in"),
        ("unaffected_item", "original_purchase_order", "ordered_in"),
        ("replacement_item", "replacement_purchase_order", "ordered_in"),
        ("affected_item", "quality_inspection", "inspected_as"),
    )
    for source, target, relation_type in item_relations:
        if (source, target, relation_type) not in relation_keys:
            graph["relations"].append(
                {
                    "source": source,
                    "target": target,
                    "type": relation_type,
                    "evidence": "replayed from native item_code fields",
                }
            )
    graph["required_evidence_groups"] = [
        [
            "purchase_return",
            "quality_inspection",
            "replacement_purchase_receipt",
        ],
        [
            "return_stock_ledger",
            "payment_general_ledger",
            "debit_general_ledger",
        ],
        ["pickup_job"],
        ["pickup_delivery"],
    ]
    graph["schema_version"] = "1.0"
    graph["source"] = (
        "native replay projection with executable relation assertions"
    )
    for relation in graph["relations"]:
        relation.pop("observed", None)
        relation["replay"] = _replay_clauses(relation)
    replay = {
        "schema_version": "1.0",
        "scenario_id": scenario["scenario_id"],
        "captures": [
            {
                "variant": report["variant"],
                "source_report": str(path.as_posix()),
                "source_report_sha256": _sha256(path),
                "source_evaluation_passed": bool(
                    report.get("evaluation", {}).get("passed", False)
                ),
                "evidence": report["final_evidence"],
            }
            for path, report in zip(args.source_report, reports)
        ],
    }
    replay_relative = "artifacts/replay_evidence.json"
    scenario["schema_version"] = "1.0"
    scenario["admission_artifacts"]["replay_evidence"] = replay_relative
    graph_path.write_text(
        json.dumps(graph, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (scenario_dir / replay_relative).write_text(
        json.dumps(replay, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    args.scenario.write_text(
        json.dumps(scenario, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
