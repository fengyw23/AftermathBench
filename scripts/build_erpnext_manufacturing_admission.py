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
from aftermath_bench.native_admission import (
    native_admission_report_payload,
    validate_native_scenario,
)
from aftermath_bench.native_scenario import load_native_scenario

VARIANT_DIRECTIONS = {
    "request_not_reached": "complete_missing_manufacture_then_rework",
    "database_committed_response_lost": (
        "preserve_completion_and_repair_quality_branch"
    ),
    "after_commit_enqueue_failed": "verify_all_postings",
    "async_job_pending": "resume_existing_rework_job",
}


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
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
    clause: dict[str, Any] = {"selector": selector, "operator": operator}
    if expected_entity is not None:
        clause["expected_entity"] = expected_entity
    elif operator != "nonempty":
        clause["expected"] = expected
    return clause


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
        "evidence": "native ERPNext document and ledger replay projection",
        "replay": list(clauses),
    }


def _normalise_evidence(
    evidence: dict[str, Any], prefix: dict[str, Any]
) -> dict[str, Any]:
    result = dict(evidence)
    final_entries = [
        document
        for document in evidence.get("manufacture_stock_entries", [])
        if document.get("purpose") == "Manufacture"
        and document.get("name") != prefix["accepted_manufacture_stock_entry"]
        and int(document.get("docstatus", 0)) != 2
    ]
    if len(final_entries) != 1:
        raise RuntimeError("reference must contain exactly one final manufacture entry")
    final_entry = final_entries[0]
    final_inspections = [
        document
        for document in evidence.get("quality_inspections", [])
        if document.get("reference_type") == "Stock Entry"
        and document.get("reference_name") == final_entry.get("name")
        and int(document.get("docstatus", 0)) != 2
    ]
    if len(final_inspections) != 1:
        raise RuntimeError("reference must contain exactly one final inspection")
    result["final_manufacture_stock_entry"] = final_entry
    result["final_quality_inspection"] = final_inspections[0]
    return result


def _load_inputs(
    directory: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    references = [
        _read(directory / f"{variant}-reference.json")
        for variant in VARIANT_DIRECTIONS
    ]
    failures = [
        _read(directory / f"{variant}.json") for variant in VARIANT_DIRECTIONS
    ]
    baselines = [
        _read(path) for path in sorted(directory.glob("*-baseline-*.json"))
    ]
    if any(
        report.get("control_error") is not None
        or not report.get("evaluation", {}).get("passed", False)
        for report in references
    ):
        raise RuntimeError("not every native manufacturing reference passed")
    if any(
        not report.get("boundary_validation", {}).get("passed", False)
        for report in failures
    ):
        raise RuntimeError("not every manufacturing failure boundary passed")
    baseline_names = {str(report.get("baseline")) for report in baselines}
    if len(baseline_names) < 6 or len(baselines) != len(baseline_names) * 4:
        raise RuntimeError("expected at least six baselines on all four variants")
    return references, failures, baselines


def _build_graph(
    prefix: dict[str, Any],
    references: list[dict[str, Any]],
    failures: list[dict[str, Any]],
) -> dict[str, Any]:
    evidence = _normalise_evidence(references[0]["final_evidence"], prefix)
    final_entry = evidence["final_manufacture_stock_entry"]
    final_inspection = evidence["final_quality_inspection"]
    material_inspections = [
        document
        for document in evidence["quality_inspections"]
        if document.get("reference_name") == prefix["material_transfer_stock_entry"]
    ]
    if len(material_inspections) < 2:
        raise RuntimeError("expected native material-transfer inspections")
    unrelated_items = [
        str(row.get("item_code"))
        for row in evidence["unrelated_stock_entry"].get("items", [])
        if row.get("item_code")
    ]
    if not unrelated_items:
        raise RuntimeError("unrelated protected stock item is missing")

    entities = [
        ("finished_item", "Item", prefix["finished_item"]),
        ("raw_item_0", "Item", prefix["raw_items"][0]),
        ("raw_item_1", "Item", prefix["raw_items"][1]),
        ("unrelated_item", "Item", unrelated_items[0]),
        ("bom", "BOM", prefix["bom"]),
        ("work_order", "Work Order", prefix["work_order"]),
        ("accepted_job_card", "Job Card", prefix["accepted_job_card"]),
        ("rejected_job_card", "Job Card", prefix["rejected_job_card"]),
        ("corrective_job_card", "Job Card", prefix["corrective_job_card"]),
        (
            "accepted_quality_inspection",
            "Quality Inspection",
            prefix["accepted_quality_inspection"],
        ),
        (
            "rejected_quality_inspection",
            "Quality Inspection",
            prefix["rejected_quality_inspection"],
        ),
        (
            "material_quality_inspection_0",
            "Quality Inspection",
            material_inspections[0]["name"],
        ),
        (
            "material_quality_inspection_1",
            "Quality Inspection",
            material_inspections[1]["name"],
        ),
        ("final_quality_inspection", "Quality Inspection", final_inspection["name"]),
        (
            "material_transfer",
            "Stock Entry",
            prefix["material_transfer_stock_entry"],
        ),
        (
            "accepted_manufacture",
            "Stock Entry",
            prefix["accepted_manufacture_stock_entry"],
        ),
        ("final_manufacture", "Stock Entry", final_entry["name"]),
        ("unrelated_stock_entry", "Stock Entry", prefix["unrelated_stock_entry"]),
        (
            "material_transfer_stock_ledger",
            "Stock Ledger",
            prefix["material_transfer_stock_entry"],
        ),
        (
            "accepted_stock_ledger",
            "Stock Ledger",
            prefix["accepted_manufacture_stock_entry"],
        ),
        ("final_stock_ledger", "Stock Ledger", final_entry["name"]),
        (
            "unrelated_stock_ledger",
            "Stock Ledger",
            prefix["unrelated_stock_entry"],
        ),
        (
            "accepted_general_ledger",
            "General Ledger",
            prefix["accepted_manufacture_stock_entry"],
        ),
        ("final_general_ledger", "General Ledger", final_entry["name"]),
        (
            "unrelated_general_ledger",
            "General Ledger",
            prefix["unrelated_stock_entry"],
        ),
        (
            "quality_release_delivery",
            "External Delivery",
            prefix["corrective_job_card"],
        ),
        ("quality_release_webhook", "Webhook", prefix["quality_release_webhook"]),
        (
            "corrective_operation",
            "Operation",
            prefix["corrective_operation"],
        ),
    ]

    relations = [
        _relation(
            "finished_item",
            "bom",
            "specified_by",
            _clause("bom.item", expected_entity="finished_item"),
        ),
        _relation(
            "raw_item_0",
            "bom",
            "consumed_by",
            _clause("bom.items.*.item_code", expected_entity="raw_item_0"),
        ),
        _relation(
            "raw_item_1",
            "bom",
            "consumed_by",
            _clause("bom.items.*.item_code", expected_entity="raw_item_1"),
        ),
        _relation(
            "bom",
            "work_order",
            "schedules",
            _clause("work_order.bom_no", expected_entity="bom"),
        ),
        _relation(
            "work_order",
            "accepted_job_card",
            "divides_into",
            _clause("accepted_job_card.work_order", expected_entity="work_order"),
        ),
        _relation(
            "work_order",
            "rejected_job_card",
            "divides_into",
            _clause("rejected_job_card.work_order", expected_entity="work_order"),
        ),
        _relation(
            "rejected_job_card",
            "corrective_job_card",
            "corrected_by",
            _clause(
                "corrective_job_card.for_job_card",
                expected_entity="rejected_job_card",
            ),
        ),
        _relation(
            "corrective_operation",
            "corrective_job_card",
            "performed_by",
            _clause(
                "corrective_job_card.operation",
                expected_entity="corrective_operation",
            ),
        ),
        _relation(
            "rejected_job_card",
            "rejected_quality_inspection",
            "inspected_by",
            _clause(
                "rejected_quality_inspection.reference_name",
                expected_entity="rejected_job_card",
            ),
        ),
        _relation(
            "work_order",
            "material_transfer",
            "supplied_by",
            _clause("material_transfer_stock_entry.work_order", expected_entity="work_order"),
        ),
        _relation(
            "material_transfer",
            "material_quality_inspection_0",
            "inspected_by",
            _clause(
                "quality_inspections.*.reference_name",
                expected_entity="material_transfer",
            ),
        ),
        _relation(
            "material_transfer",
            "material_quality_inspection_1",
            "inspected_by",
            _clause(
                "quality_inspections.*.reference_name",
                expected_entity="material_transfer",
            ),
        ),
        _relation(
            "work_order",
            "accepted_manufacture",
            "posted_by",
            _clause(
                "accepted_manufacture_stock_entry.work_order",
                expected_entity="work_order",
            ),
        ),
        _relation(
            "bom",
            "accepted_manufacture",
            "costs",
            _clause("accepted_manufacture_stock_entry.bom_no", expected_entity="bom"),
        ),
        _relation(
            "accepted_manufacture",
            "accepted_quality_inspection",
            "inspected_by",
            _clause(
                "accepted_quality_inspection.reference_name",
                expected_entity="accepted_manufacture",
            ),
        ),
        _relation(
            "work_order",
            "final_manufacture",
            "posted_by",
            _clause(
                "final_manufacture_stock_entry.work_order",
                expected_entity="work_order",
            ),
        ),
        _relation(
            "bom",
            "final_manufacture",
            "costs",
            _clause("final_manufacture_stock_entry.bom_no", expected_entity="bom"),
        ),
        _relation(
            "final_manufacture",
            "final_quality_inspection",
            "inspected_by",
            _clause(
                "final_quality_inspection.reference_name",
                expected_entity="final_manufacture",
            ),
        ),
        _relation(
            "unrelated_item",
            "unrelated_stock_entry",
            "received_by",
            _clause(
                "unrelated_stock_entry.items.*.item_code",
                expected_entity="unrelated_item",
            ),
        ),
    ]
    for document, stock_ledger, selector in (
        (
            "material_transfer",
            "material_transfer_stock_ledger",
            "material_transfer_stock_entry",
        ),
        (
            "accepted_manufacture",
            "accepted_stock_ledger",
            "accepted_manufacture_stock_entry",
        ),
        ("final_manufacture", "final_stock_ledger", "final_manufacture_stock_entry"),
        ("unrelated_stock_entry", "unrelated_stock_ledger", "unrelated_stock_entry"),
    ):
        relations.append(
            _relation(
                document,
                stock_ledger,
                "posts_stock",
                _clause(
                    "stock_ledger_entries.*.voucher_no",
                    expected_entity=document,
                ),
                _clause(f"{selector}.docstatus", expected=1),
            )
        )
    for document, general_ledger in (
        ("accepted_manufacture", "accepted_general_ledger"),
        ("final_manufacture", "final_general_ledger"),
        ("unrelated_stock_entry", "unrelated_general_ledger"),
    ):
        relations.append(
            _relation(
                document,
                general_ledger,
                "posts_accounting",
                _clause("gl_entries.*.voucher_no", expected_entity=document),
            )
        )
    relations.extend(
        [
            _relation(
                "corrective_job_card",
                "quality_release_delivery",
                "releases",
                _clause(
                    "quality_release_delivery.key",
                    expected_entity="corrective_job_card",
                ),
                _clause("quality_release_delivery.attempt_count", expected=1),
            ),
            _relation(
                "quality_release_webhook",
                "quality_release_delivery",
                "dispatches",
                _clause("quality_release_delivery.key", "nonempty"),
            ),
        ]
    )

    boundary_signatures = []
    for report in failures:
        boundary = report["boundary_evidence"]
        unfinished = [
            job
            for job in boundary.get("rq_jobs", [])
            if str(job.get("status", "")).lower()
            in {"queued", "started", "failed", "deferred", "scheduled"}
        ]
        boundary_signatures.append(
            {
                "variant": report["variant"],
                "signals": {
                    "corrective_job_card": int(
                        boundary["corrective_job_card"].get("docstatus", 0)
                    ),
                    "external_delivery": bool(
                        boundary.get("quality_release_delivery")
                    ),
                    "background_job": bool(unfinished),
                },
            }
        )

    return {
        "schema_version": "1.0",
        "scenario_id": prefix["scenario_id"],
        "source": "native ERPNext manufacturing, stock, GL, queue and receiver replay",
        "entities": [
            {"id": entity_id, "type": kind, "native_name": str(native_name)}
            for entity_id, kind, native_name in entities
        ],
        "relations": relations,
        "protected_effects": [
            "bom",
            "accepted_job_card",
            "accepted_manufacture",
            "unrelated_stock_entry",
        ],
        "required_evidence_groups": [
            ["bom", "work_order", "accepted_job_card", "rejected_job_card"],
            [
                "accepted_quality_inspection",
                "rejected_quality_inspection",
                "final_quality_inspection",
            ],
            ["material_transfer", "accepted_manufacture", "final_manufacture"],
            ["accepted_stock_ledger", "final_stock_ledger"],
            ["accepted_general_ledger", "final_general_ledger"],
            ["quality_release_delivery"],
        ],
        "evidence_tool_groups": [
            {"id": "documents", "tools": ["get_document"]},
            {"id": "related_records", "tools": ["list_documents"]},
            {"id": "stock", "tools": ["get_stock_ledger"]},
            {"id": "accounting", "tools": ["get_general_ledger"]},
            {"id": "async", "tools": ["find_background_jobs"]},
            {"id": "external", "tools": ["get_external_delivery"]},
        ],
        "boundary_signatures": boundary_signatures,
        "minimum_boundary_query_groups": 3,
        "single_query_decisive": False,
        "minimum_semantic_recovery_directions": 4,
        "action_branches": [
            {
                "id": "document_state",
                "mutation_tools": [
                    "submit_document",
                    "cancel_document",
                    "create_corrective_job_card",
                ],
            },
            {
                "id": "production_posting",
                "mutation_tools": [
                    "create_manufacture_stock_entry",
                    "create_quality_inspection",
                ],
            },
            {
                "id": "asynchronous_release",
                "mutation_tools": [
                    "enqueue_document_webhook",
                    "resume_workers",
                ],
            },
        ],
        "unsafe_actions": [
            "resubmit an already committed corrective Job Card",
            "cancel the accepted eight-unit manufacture posting",
            "cancel the accepted Job Card or Work Order",
            "create a duplicate corrective Job Card",
            "create a duplicate final Manufacture Stock Entry",
            "enqueue a second quality release after delivery",
        ],
    }


def _build_reference(
    prefix: dict[str, Any], reports: list[dict[str, Any]]
) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "scenario_id": prefix["scenario_id"],
        "source": "live native manufacturing reference replay",
        "reports": [
            {
                "variant": report["variant"],
                "passed": report["evaluation"]["passed"],
                "query_tools": report["query_tools"],
                "query_events": [
                    {"tool": event["tool"], "arguments": event.get("arguments", {})}
                    for event in report["reference_trace"]
                    if event["tool"] in report["query_tools"]
                ],
                "mutation_tools": report["mutation_tools"],
                "downstream_repairs": 3,
                "semantic_recovery_direction": VARIANT_DIRECTIONS[report["variant"]],
            }
            for report in reports
        ],
    }


def _build_baselines(
    prefix: dict[str, Any], reports: list[dict[str, Any]]
) -> dict[str, Any]:
    heuristics = []
    for name in sorted({str(report["baseline"]) for report in reports}):
        group = [report for report in reports if report["baseline"] == name]
        passed = [bool(report["evaluation"]["passed"]) for report in group]
        heuristics.append(
            {
                "name": name,
                "pass_rate": sum(passed) / len(passed),
                "matched_group_success": all(passed),
                "reports": [
                    {"variant": report["variant"], "passed": did_pass}
                    for report, did_pass in zip(group, passed, strict=True)
                ],
            }
        )
    return {
        "schema_version": "1.0",
        "scenario_id": prefix["scenario_id"],
        "source": "executed native terminal-state evaluations",
        "heuristics": heuristics,
    }


def _build_replay(
    prefix: dict[str, Any],
    graph: dict[str, Any],
    references: list[dict[str, Any]],
    directory: Path,
) -> dict[str, Any]:
    selectors = replay_selectors(graph)
    captures = []
    for report in references:
        source = directory / f"{report['variant']}-reference.json"
        captures.append(
            {
                "variant": report["variant"],
                "source_report": source.name,
                "source_report_sha256": _sha256(source),
                "source_evaluation_passed": report["evaluation"]["passed"],
                "evidence": project_evidence(
                    _normalise_evidence(report["final_evidence"], prefix),
                    selectors,
                ),
            }
        )
    replay = {
        "schema_version": "1.0",
        "scenario_id": prefix["scenario_id"],
        "captures": captures,
    }
    failures = [
        {
            "source": result.source,
            "target": result.target,
            "type": result.relation_type,
            "failures": result.failures,
        }
        for result in replay_graph(graph, replay)
        if not result.passed
    ]
    if failures:
        raise RuntimeError(f"manufacturing relation replay failed: {failures}")
    return replay


def build_admission(
    *,
    runtime_directory: Path,
    blueprint_path: Path,
    output_directory: Path,
) -> dict[str, Any]:
    prefix_path = runtime_directory / "prefix.json"
    prefix = _read(prefix_path)
    blueprint = _read(blueprint_path)
    if prefix["scenario_id"] != blueprint["scenario_id"]:
        raise RuntimeError("blueprint and prefix scenario IDs do not match")
    references, failures, baseline_reports = _load_inputs(runtime_directory)
    graph = _build_graph(prefix, references, failures)
    reference = _build_reference(prefix, references)
    baselines = _build_baselines(prefix, baseline_reports)
    replay = _build_replay(prefix, graph, references, runtime_directory)
    scenario = {
        **blueprint,
        "schema_version": "1.0",
        "benchmark_split": "development",
        "benchmark_tier": "hard",
        "implementation_status": (
            "native manufacturing replay, reference controls, fixed baselines "
            "and strict hard admission validated"
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
    artifacts = output_directory / "artifacts"
    _write(output_directory / "scenario.json", scenario)
    artifacts.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(prefix_path, artifacts / "prefix.json")
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
        description="Build replay-derived manufacturing admission artifacts."
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
