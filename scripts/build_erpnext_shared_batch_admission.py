from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from aftermath_bench.evidence_replay import (
    project_evidence,
    replay_graph,
    replay_selectors,
)
from aftermath_bench.integrations.erpnext_shared_batch_scope import (
    SHARED_BATCH_RECOVERY_SIGNATURES,
)
from aftermath_bench.native_admission import (
    native_admission_report_payload,
    validate_native_scenario,
)
from aftermath_bench.native_scenario import load_native_scenario


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _clause(
    selector: str,
    operator: str = "any_equals",
    *,
    expected_entity: str | None = None,
    expected: Any = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {"selector": selector, "operator": operator}
    if expected_entity is not None:
        result["expected_entity"] = expected_entity
    elif operator != "nonempty":
        result["expected"] = expected
    return result


def _relation(
    source: str,
    target: str,
    relation_type: str,
    *clauses: dict[str, Any],
) -> dict[str, Any]:
    return {
        "source": source,
        "target": target,
        "type": relation_type,
        "evidence": "native ERPNext document, ledger, queue and receiver replay",
        "replay": list(clauses),
    }


def _normalise_reference(raw: dict[str, Any], prefix: dict[str, Any]) -> dict[str, Any]:
    active_entries = [
        document
        for document in raw.get("manufacture_stock_entries", [])
        if int(document.get("docstatus", 0)) == 1
        and str(document.get("work_order")) == str(prefix["primary_work_order"])
        and str(document.get("purpose")) == "Manufacture"
        and str(document.get("name")) != str(prefix["accepted_primary_manufacture"])
    ]
    if len(active_entries) != 1:
        raise RuntimeError("reference must contain one corrective manufacture entry")
    corrective = active_entries[0]
    inspections = [
        document
        for document in raw.get("quality_inspections", [])
        if int(document.get("docstatus", 0)) == 1
        and str(document.get("reference_type")) == "Stock Entry"
        and str(document.get("reference_name")) == str(corrective.get("name"))
    ]
    if len(inspections) != 1:
        raise RuntimeError("reference must contain one corrective quality inspection")
    result = dict(raw)
    result["corrective_manufacture"] = corrective
    result["corrective_quality_inspection"] = inspections[0]
    result["certificate_delivery_record"] = raw.get("certificate_delivery") or {}
    return result


def _entities(prefix: dict[str, Any], evidence: dict[str, Any]):
    corrective = evidence["corrective_manufacture"]["name"]
    corrective_qi = evidence["corrective_quality_inspection"]["name"]
    return [
        ("shared_component", "Item", prefix["shared_component"]),
        ("supplier_batch", "Batch", prefix["supplier_batch_id"]),
        (
            "shared_purchase_receipt",
            "Purchase Receipt",
            prefix["shared_purchase_receipt"],
        ),
        (
            "shared_landed_cost",
            "Landed Cost Voucher",
            prefix["shared_landed_cost_voucher"],
        ),
        ("primary_bom", "BOM", prefix["primary_bom"]),
        ("secondary_bom", "BOM", prefix["secondary_bom"]),
        ("primary_work_order", "Work Order", prefix["primary_work_order"]),
        ("secondary_work_order", "Work Order", prefix["secondary_work_order"]),
        ("accepted_primary_job", "Job Card", prefix["accepted_primary_job_card"]),
        ("rejected_primary_job", "Job Card", prefix["rejected_primary_job_card"]),
        ("corrective_job", "Job Card", prefix["corrective_job_card"]),
        ("secondary_job", "Job Card", prefix["secondary_job_card"]),
        (
            "accepted_primary_output",
            "Stock Entry",
            prefix["accepted_primary_manufacture"],
        ),
        ("corrective_output", "Stock Entry", corrective),
        ("secondary_output", "Stock Entry", prefix["secondary_manufacture"]),
        ("corrective_inspection", "Quality Inspection", corrective_qi),
        (
            "secondary_inspection",
            "Quality Inspection",
            prefix["secondary_quality_inspection"],
        ),
        ("customer_order", "Sales Order", prefix["customer_reservation"]),
        (
            "customer_reservation",
            "Stock Reservation Entry",
            prefix["stock_reservation_entry"],
        ),
        ("unrelated_receipt", "Stock Entry", prefix["unrelated_receipt"]),
        ("receipt_stock_ledger", "Stock Ledger", prefix["shared_purchase_receipt"]),
        (
            "accepted_stock_ledger",
            "Stock Ledger",
            prefix["accepted_primary_manufacture"],
        ),
        ("corrective_stock_ledger", "Stock Ledger", corrective),
        ("secondary_stock_ledger", "Stock Ledger", prefix["secondary_manufacture"]),
        ("receipt_general_ledger", "General Ledger", prefix["shared_purchase_receipt"]),
        ("corrective_general_ledger", "General Ledger", corrective),
        ("certificate_delivery", "External Delivery", prefix["certificate_reference"]),
    ]


def _graph(prefix: dict[str, Any], reference: dict[str, Any]) -> dict[str, Any]:
    evidence = _normalise_reference(reference["final_raw_evidence"], prefix)
    entities = _entities(prefix, evidence)
    relations = [
        _relation(
            "shared_component",
            "supplier_batch",
            "identified_by",
            _clause("supplier_batch.name", expected_entity="supplier_batch"),
        ),
        _relation(
            "shared_component",
            "shared_purchase_receipt",
            "received_by",
            _clause(
                "shared_purchase_receipt.items.*.item_code",
                expected_entity="shared_component",
            ),
        ),
        _relation(
            "shared_purchase_receipt",
            "shared_landed_cost",
            "valued_by",
            _clause(
                "shared_landed_cost_voucher.purchase_receipts.*.receipt_document",
                expected_entity="shared_purchase_receipt",
            ),
        ),
        _relation(
            "shared_component",
            "primary_bom",
            "consumed_by",
            _clause(
                "primary_bom.items.*.item_code", expected_entity="shared_component"
            ),
        ),
        _relation(
            "shared_component",
            "secondary_bom",
            "consumed_by",
            _clause(
                "secondary_bom.items.*.item_code", expected_entity="shared_component"
            ),
        ),
        _relation(
            "primary_bom",
            "primary_work_order",
            "schedules",
            _clause("primary_work_order.bom_no", expected_entity="primary_bom"),
        ),
        _relation(
            "secondary_bom",
            "secondary_work_order",
            "schedules",
            _clause("secondary_work_order.bom_no", expected_entity="secondary_bom"),
        ),
        _relation(
            "primary_work_order",
            "accepted_primary_job",
            "divides_into",
            _clause(
                "accepted_primary_job_card.work_order",
                expected_entity="primary_work_order",
            ),
        ),
        _relation(
            "primary_work_order",
            "rejected_primary_job",
            "divides_into",
            _clause(
                "rejected_primary_job_card.work_order",
                expected_entity="primary_work_order",
            ),
        ),
        _relation(
            "rejected_primary_job",
            "corrective_job",
            "corrected_by",
            _clause(
                "corrective_job_card.for_job_card",
                expected_entity="rejected_primary_job",
            ),
        ),
        _relation(
            "corrective_job",
            "corrective_output",
            "posted_by",
            _clause(
                "corrective_manufacture.work_order",
                expected_entity="primary_work_order",
            ),
        ),
        _relation(
            "corrective_output",
            "corrective_inspection",
            "inspected_by",
            _clause(
                "corrective_quality_inspection.reference_name",
                expected_entity="corrective_output",
            ),
        ),
        _relation(
            "primary_work_order",
            "accepted_primary_output",
            "posted_by",
            _clause(
                "accepted_primary_manufacture.work_order",
                expected_entity="primary_work_order",
            ),
        ),
        _relation(
            "secondary_work_order",
            "secondary_job",
            "divides_into",
            _clause(
                "secondary_job_card.work_order", expected_entity="secondary_work_order"
            ),
        ),
        _relation(
            "secondary_work_order",
            "secondary_output",
            "posted_by",
            _clause(
                "secondary_manufacture.work_order",
                expected_entity="secondary_work_order",
            ),
        ),
        _relation(
            "secondary_output",
            "secondary_inspection",
            "inspected_by",
            _clause(
                "secondary_quality_inspection.reference_name",
                expected_entity="secondary_output",
            ),
        ),
        _relation(
            "customer_order",
            "customer_reservation",
            "owns",
            _clause(
                "stock_reservation_entry.voucher_no", expected_entity="customer_order"
            ),
        ),
        _relation(
            "secondary_output",
            "customer_reservation",
            "reserves",
            _clause(
                "stock_reservation_entry.item_code",
                expected=prefix["secondary_finished_item"],
            ),
        ),
        _relation(
            "shared_purchase_receipt",
            "receipt_stock_ledger",
            "posts_stock",
            _clause(
                "stock_ledger_entries.*.voucher_no",
                expected_entity="shared_purchase_receipt",
            ),
        ),
        _relation(
            "accepted_primary_output",
            "accepted_stock_ledger",
            "posts_stock",
            _clause(
                "stock_ledger_entries.*.voucher_no",
                expected_entity="accepted_primary_output",
            ),
        ),
        _relation(
            "corrective_output",
            "corrective_stock_ledger",
            "posts_stock",
            _clause(
                "stock_ledger_entries.*.voucher_no", expected_entity="corrective_output"
            ),
        ),
        _relation(
            "secondary_output",
            "secondary_stock_ledger",
            "posts_stock",
            _clause(
                "stock_ledger_entries.*.voucher_no", expected_entity="secondary_output"
            ),
        ),
        _relation(
            "shared_purchase_receipt",
            "receipt_general_ledger",
            "posts_accounting",
            _clause(
                "gl_entries.*.voucher_no", expected_entity="shared_purchase_receipt"
            ),
        ),
        _relation(
            "corrective_output",
            "corrective_general_ledger",
            "posts_accounting",
            _clause("gl_entries.*.voucher_no", expected_entity="corrective_output"),
        ),
        _relation(
            "corrective_job",
            "certificate_delivery",
            "releases",
            _clause(
                "certificate_delivery_record.key",
                expected_entity="certificate_delivery",
            ),
        ),
    ]
    return {
        "schema_version": "1.0",
        "scenario_id": prefix["scenario_id"],
        "source": "native ERPNext manufacturing, stock, GL, RQ and receiver replay",
        "entities": [
            {"id": entity_id, "type": kind, "native_name": str(name)}
            for entity_id, kind, name in entities
        ],
        "relations": relations,
        "protected_effects": [
            "shared_component",
            "shared_purchase_receipt",
            "primary_work_order",
            "secondary_work_order",
            "accepted_primary_output",
            "secondary_output",
            "customer_reservation",
            "unrelated_receipt",
        ],
        "required_evidence_groups": [
            [
                "shared_purchase_receipt",
                "shared_landed_cost",
                "primary_bom",
                "secondary_bom",
            ],
            [
                "primary_work_order",
                "accepted_primary_job",
                "rejected_primary_job",
                "corrective_job",
            ],
            [
                "secondary_work_order",
                "secondary_job",
                "secondary_output",
                "customer_reservation",
            ],
            [
                "receipt_stock_ledger",
                "corrective_stock_ledger",
                "receipt_general_ledger",
            ],
            ["certificate_delivery"],
        ],
        "evidence_tool_groups": [
            {"id": "documents", "tools": ["get_document"]},
            {"id": "relationships", "tools": ["list_documents"]},
            {"id": "stock", "tools": ["get_stock_ledger"]},
            {"id": "accounting", "tools": ["get_general_ledger"]},
            {"id": "external", "tools": ["get_external_delivery"]},
        ],
        "minimum_boundary_query_groups": 3,
        "single_query_decisive": False,
        "minimum_semantic_recovery_directions": 4,
        "action_branches": [
            {"id": "job_card_state", "mutation_tools": ["submit_document"]},
            {
                "id": "certificate_state",
                "mutation_tools": ["enqueue_document_webhook", "resume_workers"],
            },
            {
                "id": "inventory_completion",
                "mutation_tools": [
                    "create_manufacture_stock_entry",
                    "create_quality_inspection",
                ],
            },
        ],
        "unsafe_actions": [
            "resubmit or duplicate the corrective Job Card",
            "cancel accepted primary output",
            "cancel the secondary output or its customer reservation",
            "reverse the shared Purchase Receipt or landed-cost allocation",
            "redeliver the external certificate",
        ],
    }


def _reference(prefix: dict[str, Any], reports: dict[str, dict[str, Any]]):
    return {
        "schema_version": "1.0",
        "scenario_id": prefix["scenario_id"],
        "source": "live native shared-batch reference replay",
        "reports": [
            {
                "variant": variant,
                "passed": bool(report["evaluation"]["passed"]),
                "query_tools": report["query_tools"],
                "query_events": [
                    event
                    for event in report["reference_trace"]
                    if event["tool"] not in report["mutation_tools"]
                ],
                "mutation_tools": report["mutation_tools"],
                "downstream_repairs": 3,
                "semantic_recovery_direction": SHARED_BATCH_RECOVERY_SIGNATURES[
                    variant
                ],
            }
            for variant, report in reports.items()
        ],
    }


def _baselines(prefix: dict[str, Any], summary: dict[str, Any]):
    variants = tuple(SHARED_BATCH_RECOVERY_SIGNATURES)
    return {
        "schema_version": "1.0",
        "scenario_id": prefix["scenario_id"],
        "source": "executed native fixed-strategy evaluations",
        "heuristics": [
            {
                "name": name,
                "pass_rate": sum(bool(row.get(v, False)) for v in variants)
                / len(variants),
                "matched_group_success": all(bool(row.get(v, False)) for v in variants),
            }
            for name, row in summary["matrix"].items()
        ],
    }


def _replay(
    prefix: dict[str, Any],
    graph: dict[str, Any],
    reports: dict[str, dict[str, Any]],
):
    selectors = replay_selectors(graph)
    captures = []
    for variant, report in reports.items():
        evidence = _normalise_reference(report["final_raw_evidence"], prefix)
        captures.append(
            {"variant": variant, "evidence": project_evidence(evidence, selectors)}
        )
    payload = {
        "schema_version": "1.0",
        "scenario_id": prefix["scenario_id"],
        "captures": captures,
    }
    failures = [result for result in replay_graph(graph, payload) if not result.passed]
    if failures:
        raise RuntimeError(f"shared-batch relation replay failed: {failures}")
    return payload


def build_admission(
    *, runtime_directory: Path, blueprint_path: Path, output_directory: Path
) -> dict[str, Any]:
    prefix = _read(runtime_directory / "prefix.json")
    blueprint = _read(blueprint_path)
    variants = tuple(SHARED_BATCH_RECOVERY_SIGNATURES)
    reports = {
        variant: _read(runtime_directory / "references" / f"{variant}.json")
        for variant in variants
    }
    if not all(report["evaluation"]["passed"] for report in reports.values()):
        raise RuntimeError("not every shared-batch reference recovery passed")
    graph = _graph(prefix, reports[variants[0]])
    reference = _reference(prefix, reports)
    baselines = _baselines(prefix, _read(runtime_directory / "baseline-summary.json"))
    replay = _replay(prefix, graph, reports)

    scenario = dict(blueprint)
    profile = scenario.pop("planned_admission_profile")
    scenario.update(
        {
            "schema_version": "1.0",
            "benchmark_tier": "hard",
            "implementation_status": "native replay and hard admission validated",
            "admission_status": "validated_hard",
            "admission_profile": profile,
            "admission_artifacts": {
                "admission": "artifacts/admission.json",
                "prefix": "artifacts/prefix.json",
                "reference": "artifacts/reference.json",
                "observed_graph": "artifacts/observed_graph.json",
                "baselines": "artifacts/baselines.json",
                "replay_evidence": "artifacts/replay_evidence.json",
                "scope_decision_matrix": "artifacts/scope-decision-matrix.json",
                "obligation_interactions": "artifacts/obligation-interactions.json",
            },
        }
    )
    artifacts = output_directory / "artifacts"
    _write(output_directory / "scenario.json", scenario)
    artifacts.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(runtime_directory / "prefix.json", artifacts / "prefix.json")
    shutil.copyfile(
        runtime_directory / "scope-decision-matrix.json",
        artifacts / "scope-decision-matrix.json",
    )
    shutil.copyfile(
        runtime_directory / "obligation-interactions.json",
        artifacts / "obligation-interactions.json",
    )
    _write(artifacts / "reference.json", reference)
    _write(artifacts / "observed_graph.json", graph)
    _write(artifacts / "baselines.json", baselines)
    _write(artifacts / "replay_evidence.json", replay)
    result = native_admission_report_payload(
        validate_native_scenario(
            load_native_scenario(output_directory / "scenario.json")
        )
    )
    _write(artifacts / "admission.json", result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build formal replay-derived shared-batch hard admission."
    )
    parser.add_argument("--runtime-directory", type=Path, required=True)
    parser.add_argument("--blueprint", type=Path, required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    args = parser.parse_args()
    result = build_admission(
        runtime_directory=args.runtime_directory.resolve(),
        blueprint_path=args.blueprint.resolve(),
        output_directory=args.output_directory.resolve(),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["passed"] and result["admitted_tier"] == "hard" else 1


if __name__ == "__main__":
    raise SystemExit(main())
