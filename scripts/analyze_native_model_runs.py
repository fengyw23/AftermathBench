from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean
from typing import Any

from aftermath_bench.native_model_runner import NATIVE_RETURN_MUTATIONS


def _load_reports(
    root: Path,
) -> tuple[list[dict[str, Any]], list[str]]:
    reports = []
    errors = []
    for path in sorted(root.rglob("*.json")):
        if path.name.endswith("-failure.json") or path.name in {
            "summary.json",
            "manifest.json",
            "prefix.json",
            "analysis.json",
        }:
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            errors.append(f"{path}: {error}")
            continue
        if "evaluation" not in payload or "variant" not in payload:
            continue
        reports.append(payload)
    return reports, errors


def _ordered_calls(report: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        call
        for turn in report.get("turns", ())
        for call in turn.get("tool_calls", ())
    ]


def _queried_invoices_before_create(
    calls: list[dict[str, Any]],
) -> bool:
    queried = False
    for call in calls:
        name = call.get("name")
        arguments = call.get("arguments", {})
        if (
            name == "list_documents"
            and arguments.get("doctype") == "Purchase Invoice"
        ):
            queried = True
        if name == "create_purchase_invoice_from_receipt":
            return queried
    return queried


def analyze(root: Path) -> dict[str, Any]:
    reports, load_errors = _load_reports(root)
    variants: dict[str, list[bool]] = defaultdict(list)
    failure_checks: Counter[str] = Counter()
    primary_errors: Counter[str] = Counter()
    derived_failure_patterns: Counter[str] = Counter()
    stop_reasons: Counter[str] = Counter()
    tool_errors = 0
    goal_but_not_integrity = 0
    complete_but_protocol_unsafe = 0
    queried_invoice_before_create = 0
    created_invoice_without_query = 0
    query_counts: list[int] = []
    mutation_counts: list[int] = []
    turn_counts: list[int] = []

    for report in reports:
        evaluation = report["evaluation"]
        passed = bool(evaluation.get("passed", False))
        variants[str(report["variant"])].append(passed)
        components = evaluation.get("components", {})
        goal_but_not_integrity += int(
            bool(components.get("goal_completion")) and not passed
        )
        complete_but_protocol_unsafe += int(
            bool(components.get("goal_completion"))
            and bool(components.get("repair_completeness"))
            and bool(components.get("preservation"))
            and not bool(components.get("protocol_safety"))
        )
        for check, value in evaluation.get("checks", {}).items():
            if not value:
                failure_checks[str(check)] += 1
        recorded_error = report.get("trajectory_diagnostics", {}).get(
            "primary_error"
        )
        if recorded_error:
            primary_errors[str(recorded_error)] += 1
        stop_reasons[str(report.get("stop_reason", "unknown"))] += 1

        calls = _ordered_calls(report)
        queries = [
            call
            for call in calls
            if call.get("name") not in NATIVE_RETURN_MUTATIONS
        ]
        mutations = [
            call
            for call in calls
            if call.get("name") in NATIVE_RETURN_MUTATIONS
        ]
        query_counts.append(len(queries))
        mutation_counts.append(len(mutations))
        turn_counts.append(len(report.get("turns", ())))
        tool_errors += int(
            report.get("trajectory_diagnostics", {}).get(
                "tool_error_count",
                0,
            )
        )
        invoice_queried = _queried_invoices_before_create(calls)
        created_without_query = (
            any(
                call.get("name")
                == "create_purchase_invoice_from_receipt"
                for call in calls
            )
            and not invoice_queried
        )
        queried_invoice_before_create += int(invoice_queried)
        created_invoice_without_query += int(created_without_query)
        if not passed:
            if (
                not evaluation.get("checks", {}).get(
                    "no_duplicate_replacement_invoice",
                    True,
                )
                and created_without_query
            ):
                derived_failure_patterns[
                    "investigation_failure"
                ] += 1
            elif recorded_error:
                derived_failure_patterns[str(recorded_error)] += 1
            else:
                derived_failure_patterns["unclassified"] += 1

    total = len(reports)
    return {
        "schema_version": "0.1",
        "completed_runs": total,
        "load_errors": load_errors,
        "variant_pass_rates": {
            variant: sum(results) / len(results)
            for variant, results in sorted(variants.items())
        },
        "goal_but_not_integrity_count": goal_but_not_integrity,
        "complete_but_protocol_unsafe_count": (
            complete_but_protocol_unsafe
        ),
        "failed_check_counts": dict(sorted(failure_checks.items())),
        "recorded_primary_error_counts": dict(
            sorted(primary_errors.items())
        ),
        "derived_failure_pattern_counts": dict(
            sorted(derived_failure_patterns.items())
        ),
        "stop_reason_counts": dict(sorted(stop_reasons.items())),
        "tool_error_count": tool_errors,
        "queried_invoices_before_create_count": (
            queried_invoice_before_create
        ),
        "created_invoice_without_prior_list_count": (
            created_invoice_without_query
        ),
        "mean_turns": mean(turn_counts) if turn_counts else 0,
        "mean_query_calls": mean(query_counts) if query_counts else 0,
        "mean_mutation_calls": (
            mean(mutation_counts) if mutation_counts else 0
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-directory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = analyze(args.run_directory)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not result["load_errors"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
