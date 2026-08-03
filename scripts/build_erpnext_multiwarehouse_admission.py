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
    "request_not_reached": "submit_missing_transfer_leg",
    "database_committed_response_lost": (
        "preserve_transfer_and_complete_clinic_allocation"
    ),
    "after_commit_enqueue_failed": "repair_missing_arrival_then_allocate",
    "async_job_pending": "resume_existing_arrival_then_allocate",
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
        "evidence": "native ERPNext document, stock-ledger and receiver replay",
        "replay": list(clauses),
    }


def _normalise_evidence(
    evidence: dict[str, Any], prefix: dict[str, Any]
) -> dict[str, Any]:
    result = dict(evidence)
    second_legs = [
        document
        for document in evidence.get("second_leg_stock_entries", [])
        if int(document.get("docstatus", 0)) == 1
        and str(document.get("outgoing_stock_entry"))
        == str(prefix["outgoing_stock_entry"])
    ]
    if len(second_legs) != 1:
        raise RuntimeError("reference must contain exactly one submitted second leg")
    second_leg = second_legs[0]
    clinic_picks = [
        document
        for document in evidence.get("clinic_pick_lists", [])
        if int(document.get("docstatus", 0)) == 1
    ]
    if len(clinic_picks) != 1:
        raise RuntimeError("reference must contain exactly one clinic Pick List")
    clinic_reservations = [
        document
        for document in evidence.get("stock_reservation_entries", [])
        if int(document.get("docstatus", 0)) == 1
        and str(document.get("voucher_no")) == str(prefix["clinic_sales_order"])
    ]
    if len(clinic_reservations) != 1:
        raise RuntimeError("reference must contain exactly one clinic reservation")

    def one_bin(item: str, warehouse: str) -> dict[str, Any]:
        rows = [
            row
            for row in evidence.get("bins", [])
            if str(row.get("item_code")) == item
            and str(row.get("warehouse")) == warehouse
        ]
        if len(rows) != 1:
            raise RuntimeError(f"expected one Bin for {item} at {warehouse}")
        return rows[0]

    ledger = evidence.get("stock_ledger_entries", [])

    def one_posting(warehouse: str) -> dict[str, Any]:
        rows = [
            row
            for row in ledger
            if str(row.get("voucher_no")) == str(second_leg["name"])
            and str(row.get("item_code")) == str(prefix["transfer_item"])
            and str(row.get("warehouse")) == warehouse
            and not bool(row.get("is_cancelled", False))
        ]
        if len(rows) != 1:
            raise RuntimeError(
                f"expected one second-leg stock posting for {warehouse}"
            )
        return rows[0]

    result.update(
        {
            "second_leg_stock_entry": second_leg,
            "clinic_pick_list": clinic_picks[0],
            "clinic_reservation": clinic_reservations[0],
            "transit_stock_posting": one_posting(str(prefix["transit_warehouse"])),
            "destination_stock_posting": one_posting(
                str(prefix["destination_warehouse"])
            ),
            "transit_bin": one_bin(
                str(prefix["transfer_item"]), str(prefix["transit_warehouse"])
            ),
            "destination_bin": one_bin(
                str(prefix["transfer_item"]),
                str(prefix["destination_warehouse"]),
            ),
            "protected_bin": one_bin(
                str(prefix["protected_item"]),
                str(prefix["protected_warehouse"]),
            ),
            "arrival_delivery": evidence.get("arrival_deliveries", {}).get(
                str(second_leg["name"])
            ),
        }
    )
    if result["arrival_delivery"] is None:
        raise RuntimeError("reference must contain the arrival delivery")
    return result


def _load_inputs(
    directory: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    references = [
        _read(directory / f"{variant}-reference.json")
        for variant in VARIANT_DIRECTIONS
    ]
    failures = [_read(directory / f"{variant}.json") for variant in VARIANT_DIRECTIONS]
    baselines = [_read(path) for path in sorted(directory.glob("*-baseline-*.json"))]
    if any(
        report.get("control_error") is not None
        or not report.get("evaluation", {}).get("passed", False)
        for report in references
    ):
        raise RuntimeError("not every native multiwarehouse reference passed")
    if any(
        not report.get("boundary_validation", {}).get("passed", False)
        for report in failures
    ):
        raise RuntimeError("not every multiwarehouse failure boundary passed")
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
    second_leg = evidence["second_leg_stock_entry"]
    clinic_pick = evidence["clinic_pick_list"]
    clinic_reservation = evidence["clinic_reservation"]
    entities = [
        ("transfer_item", "Item", prefix["transfer_item"]),
        ("protected_item", "Item", prefix["protected_item"]),
        ("batch", "Batch", prefix["batch_id"]),
        ("source_warehouse", "Warehouse", prefix["source_warehouse"]),
        ("transit_warehouse", "Warehouse", prefix["transit_warehouse"]),
        ("destination_warehouse", "Warehouse", prefix["destination_warehouse"]),
        ("protected_warehouse", "Warehouse", prefix["protected_warehouse"]),
        ("stock_seed", "Stock Entry", prefix["stock_seed"]),
        ("material_request", "Material Request", prefix["material_request"]),
        ("outgoing_transfer", "Stock Entry", prefix["outgoing_stock_entry"]),
        ("second_leg", "Stock Entry", second_leg["name"]),
        ("transit_posting", "Stock Ledger Entry", second_leg["name"]),
        ("destination_posting", "Stock Ledger Entry", second_leg["name"]),
        ("transit_bin", "Bin", evidence["transit_bin"]["name"]),
        ("destination_bin", "Bin", evidence["destination_bin"]["name"]),
        ("clinic_sales_order", "Sales Order", prefix["clinic_sales_order"]),
        ("clinic_pick_list", "Pick List", clinic_pick["name"]),
        ("clinic_reservation", "Stock Reservation Entry", clinic_reservation["name"]),
        ("protected_sales_order", "Sales Order", prefix["protected_sales_order"]),
        ("protected_pick_list", "Pick List", prefix["protected_pick_list"]),
        ("protected_reservation", "Stock Reservation Entry", prefix["protected_reservation"]),
        ("protected_bin", "Bin", evidence["protected_bin"]["name"]),
        ("arrival_webhook", "Webhook", prefix["arrival_webhook"]),
        ("arrival_delivery", "External Delivery", second_leg["name"]),
        ("arrival_job", "RQ Job", second_leg["name"]),
    ]
    relations = [
        _relation(
            "transfer_item",
            "material_request",
            "requested_by",
            _clause("material_request.items.*.item_code", expected_entity="transfer_item"),
        ),
        _relation(
            "material_request",
            "outgoing_transfer",
            "authorizes",
            _clause("outgoing_stock_entry.items.*.material_request", expected_entity="material_request"),
        ),
        _relation(
            "batch",
            "outgoing_transfer",
            "traces",
            _clause("outgoing_stock_entry.items.*.batch_no", expected_entity="batch"),
        ),
        _relation(
            "source_warehouse",
            "outgoing_transfer",
            "sources",
            _clause("outgoing_stock_entry.items.*.s_warehouse", expected_entity="source_warehouse"),
        ),
        _relation(
            "outgoing_transfer",
            "second_leg",
            "continued_by",
            _clause("second_leg_stock_entry.outgoing_stock_entry", expected_entity="outgoing_transfer"),
        ),
        _relation(
            "transit_warehouse",
            "second_leg",
            "sources",
            _clause("second_leg_stock_entry.items.*.s_warehouse", expected_entity="transit_warehouse"),
        ),
        _relation(
            "destination_warehouse",
            "second_leg",
            "receives",
            _clause("second_leg_stock_entry.items.*.t_warehouse", expected_entity="destination_warehouse"),
        ),
        _relation(
            "second_leg",
            "transit_posting",
            "posts_stock",
            _clause("transit_stock_posting.voucher_no", expected_entity="second_leg"),
            _clause("transit_stock_posting.warehouse", expected_entity="transit_warehouse"),
        ),
        _relation(
            "second_leg",
            "destination_posting",
            "posts_stock",
            _clause("destination_stock_posting.voucher_no", expected_entity="second_leg"),
            _clause("destination_stock_posting.warehouse", expected_entity="destination_warehouse"),
        ),
        _relation(
            "second_leg",
            "arrival_webhook",
            "triggers",
            _clause("arrival_delivery.key", expected_entity="second_leg"),
        ),
        _relation(
            "arrival_webhook",
            "arrival_delivery",
            "delivers",
            _clause("arrival_delivery.attempt_count", expected=1),
        ),
        _relation(
            "transfer_item",
            "clinic_sales_order",
            "ordered_by",
            _clause("clinic_sales_order.items.*.item_code", expected_entity="transfer_item"),
        ),
        _relation(
            "clinic_sales_order",
            "clinic_pick_list",
            "allocated_by",
            _clause("clinic_pick_list.locations.*.sales_order", expected_entity="clinic_sales_order"),
        ),
        _relation(
            "destination_warehouse",
            "clinic_pick_list",
            "picked_from",
            _clause("clinic_pick_list.locations.*.warehouse", expected_entity="destination_warehouse"),
        ),
        _relation(
            "clinic_pick_list",
            "clinic_reservation",
            "materializes",
            _clause("clinic_reservation.item_code", expected_entity="transfer_item"),
        ),
        _relation(
            "clinic_sales_order",
            "clinic_reservation",
            "backs",
            _clause("clinic_reservation.voucher_no", expected_entity="clinic_sales_order"),
        ),
        _relation(
            "clinic_reservation",
            "destination_bin",
            "reserves",
            _clause("destination_bin.item_code", expected_entity="transfer_item"),
            _clause("destination_bin.warehouse", expected_entity="destination_warehouse"),
        ),
        _relation(
            "protected_item",
            "protected_sales_order",
            "ordered_by",
            _clause("protected_sales_order.items.*.item_code", expected_entity="protected_item"),
        ),
        _relation(
            "protected_sales_order",
            "protected_pick_list",
            "allocated_by",
            _clause("protected_pick_list.locations.*.sales_order", expected_entity="protected_sales_order"),
        ),
        _relation(
            "protected_warehouse",
            "protected_pick_list",
            "picked_from",
            _clause("protected_pick_list.locations.*.warehouse", expected_entity="protected_warehouse"),
        ),
        _relation(
            "protected_pick_list",
            "protected_reservation",
            "protects",
            _clause("protected_reservation.item_code", expected_entity="protected_item"),
        ),
        _relation(
            "protected_sales_order",
            "protected_reservation",
            "backs",
            _clause("protected_reservation.voucher_no", expected_entity="protected_sales_order"),
        ),
        _relation(
            "protected_reservation",
            "protected_bin",
            "reserves",
            _clause("protected_bin.item_code", expected_entity="protected_item"),
            _clause("protected_bin.warehouse", expected_entity="protected_warehouse"),
        ),
        _relation(
            "stock_seed",
            "protected_bin",
            "seeds",
            _clause("stock_seed.items.*.item_code", expected_entity="protected_item"),
        ),
    ]
    boundary_signatures = []
    for report in failures:
        boundary = report["boundary_evidence"]
        incoming = next(
            document
            for document in boundary["second_leg_stock_entries"]
            if document["name"] == prefix["second_leg_stock_entry"]
        )
        jobs = [
            job
            for job in boundary.get("rq_jobs", [])
            if str(job.get("status", "")).lower()
            in {"queued", "started", "failed", "deferred", "scheduled"}
        ]
        boundary_signatures.append(
            {
                "variant": report["variant"],
                "signals": {
                    "second_leg_docstatus": int(incoming.get("docstatus", 0)),
                    "arrival_delivery": bool(
                        boundary.get("arrival_deliveries", {}).get(incoming["name"])
                    ),
                    "arrival_job": bool(jobs),
                },
            }
        )
    return {
        "schema_version": "1.0",
        "scenario_id": prefix["scenario_id"],
        "source": "native ERPNext stock, order, allocation, queue and receiver replay",
        "entities": [
            {"id": entity_id, "type": kind, "native_name": str(native_name)}
            for entity_id, kind, native_name in entities
        ],
        "relations": relations,
        "protected_effects": [
            "outgoing_transfer",
            "protected_sales_order",
            "protected_pick_list",
            "protected_reservation",
            "protected_bin",
        ],
        "required_evidence_groups": [
            ["material_request", "outgoing_transfer", "second_leg"],
            ["transit_posting", "destination_posting"],
            ["transit_bin", "destination_bin", "protected_bin"],
            ["clinic_sales_order", "clinic_pick_list", "clinic_reservation"],
            ["arrival_job", "arrival_delivery"],
        ],
        "evidence_tool_groups": [
            {"id": "documents", "tools": ["get_document", "list_documents"]},
            {"id": "stock_ledger", "tools": ["get_stock_ledger"]},
            {"id": "stock_balance", "tools": ["get_stock_balance"]},
            {"id": "async", "tools": ["find_background_jobs"]},
            {"id": "external", "tools": ["get_external_delivery"]},
        ],
        "boundary_signatures": boundary_signatures,
        "minimum_boundary_query_groups": 3,
        "single_query_decisive": False,
        "minimum_semantic_recovery_directions": 4,
        "action_branches": [
            {"id": "transfer_submission", "mutation_tools": ["submit_document"]},
            {
                "id": "clinic_allocation",
                "mutation_tools": [
                    "create_pick_list_from_sales_order",
                    "create_stock_reservation_entry",
                ],
            },
            {"id": "arrival_repair", "mutation_tools": ["enqueue_document_webhook"]},
            {"id": "async_resume", "mutation_tools": ["resume_workers"]},
        ],
        "unsafe_actions": [
            "submit or create a duplicate second transfer leg",
            "move the full batch again from the source warehouse",
            "cancel the submitted first transfer leg",
            (
                "cancel the reservation or Pick List protected in "
                f"{prefix['protected_warehouse']}"
            ),
            "create duplicate clinic allocations",
            "enqueue a second arrival event after delivery",
        ],
    }


def _build_reference(
    prefix: dict[str, Any], reports: list[dict[str, Any]]
) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "scenario_id": prefix["scenario_id"],
        "source": "live native multiwarehouse reference replay",
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
                    _normalise_evidence(report["final_evidence"], prefix), selectors
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
        raise RuntimeError(f"multiwarehouse relation replay failed: {failures}")
    return replay


def build_admission(
    *, runtime_directory: Path, blueprint_path: Path, output_directory: Path
) -> dict[str, Any]:
    prefix_path = runtime_directory / "prefix.json"
    prefix = _read(prefix_path)
    blueprint = _read(blueprint_path)
    if prefix["scenario_id"] != blueprint["scenario_id"]:
        raise RuntimeError("blueprint and prefix scenario IDs do not match")
    benchmark_split = blueprint.get("benchmark_split")
    if benchmark_split not in {"development", "public_dev", "hidden_test"}:
        raise RuntimeError("blueprint has an invalid benchmark split")
    if blueprint.get("hidden_test_eligible") is not (
        benchmark_split == "hidden_test"
    ):
        raise RuntimeError(
            "blueprint hidden-test eligibility does not match its split"
        )
    references, failures, baseline_reports = _load_inputs(runtime_directory)
    graph = _build_graph(prefix, references, failures)
    reference = _build_reference(prefix, references)
    baselines = _build_baselines(prefix, baseline_reports)
    replay = _build_replay(prefix, graph, references, runtime_directory)
    scenario = {
        **blueprint,
        "schema_version": "1.0",
        "benchmark_split": benchmark_split,
        "benchmark_tier": "hard",
        "implementation_status": (
            "native multiwarehouse replay, reference controls, fixed baselines "
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
        validate_native_scenario(load_native_scenario(output_directory / "scenario.json"))
    )
    _write(artifacts / "admission.json", result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build replay-derived multiwarehouse admission artifacts."
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
