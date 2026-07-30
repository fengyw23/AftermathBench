from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean
from typing import Any


def _load_reports(root: Path) -> tuple[list[dict[str, Any]], list[str]]:
    reports = []
    errors = []
    for path in sorted(root.rglob("*.json")):
        if path.name.endswith("-failure.json") or path.name in {
            "summary.json",
            "control.json",
            "prefix.json",
        }:
            continue
        try:
            report = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            errors.append(f"{path}: {error}")
            continue
        if (
            report.get("family")
            != "erpnext-sales-return-exchange-reconciliation"
            or "evaluation" not in report
        ):
            continue
        report["_path"] = str(path)
        reports.append(report)
    return reports, errors


def analyze_sales_return_runs(root: Path) -> dict[str, Any]:
    reports, load_errors = _load_reports(root)
    variant_results: dict[str, list[bool]] = defaultdict(list)
    component_totals: Counter[str] = Counter()
    failed_checks: Counter[str] = Counter()
    primary_errors: Counter[str] = Counter()
    stop_reasons: Counter[str] = Counter()
    mutation_signatures: Counter[str] = Counter()
    execution_controls: Counter[str] = Counter()
    turn_counts = []
    call_counts = []
    linked_invoice_investigations = 0
    unsafe_return_resubmits = 0
    created_without_invoice_investigation = 0
    tool_errors = 0
    rows = []

    for report in reports:
        evaluation = report["evaluation"]
        passed = bool(evaluation.get("passed"))
        variant = str(report.get("variant"))
        variant_results[variant].append(passed)
        execution_controls[str(bool(report.get("execution_control"))).lower()] += 1
        for component, value in evaluation.get("components", {}).items():
            component_totals[str(component)] += int(bool(value))
        for check, value in evaluation.get("checks", {}).items():
            if not value:
                failed_checks[str(check)] += 1

        diagnostics = report.get("trajectory_diagnostics", {})
        primary_error = diagnostics.get("primary_error")
        if primary_error:
            primary_errors[str(primary_error)] += 1
        stop_reasons[str(report.get("stop_reason", "unknown"))] += 1
        selected = tuple(map(str, diagnostics.get("selected_mutations", ())))
        mutation_signatures[" -> ".join(selected) or "<no mutation>"] += 1
        linked_invoice_investigations += int(
            bool(diagnostics.get("queried_linked_invoices_before_create"))
        )
        unsafe_return_resubmits += int(
            bool(diagnostics.get("unsafe_return_resubmit"))
        )
        created_without_invoice_investigation += int(
            bool(
                diagnostics.get(
                    "created_invoice_without_linked_invoice_investigation"
                )
            )
        )
        tool_errors += int(diagnostics.get("tool_error_count", 0))
        turns = len(report.get("turns", ()))
        calls = sum(
            len(turn.get("tool_calls", ()))
            for turn in report.get("turns", ())
        )
        turn_counts.append(turns)
        call_counts.append(calls)
        rows.append(
            {
                "variant": variant,
                "passed": passed,
                "execution_control": bool(report.get("execution_control")),
                "primary_error": primary_error,
                "turns": turns,
                "tool_calls": calls,
                "selected_mutations": list(selected),
                "queried_linked_invoices_before_create": bool(
                    diagnostics.get(
                        "queried_linked_invoices_before_create"
                    )
                ),
                "unsafe_return_resubmit": bool(
                    diagnostics.get("unsafe_return_resubmit")
                ),
                "path": report["_path"],
            }
        )

    total = len(reports)
    return {
        "schema_version": "0.1",
        "completed_runs": total,
        "load_errors": load_errors,
        "task_pass_rate": (
            sum(row["passed"] for row in rows) / total if total else 0.0
        ),
        "variant_pass_rates": {
            variant: sum(values) / len(values)
            for variant, values in sorted(variant_results.items())
        },
        "component_pass_rates": {
            component: count / total if total else 0.0
            for component, count in sorted(component_totals.items())
        },
        "failed_check_counts": dict(sorted(failed_checks.items())),
        "primary_error_counts": dict(sorted(primary_errors.items())),
        "stop_reason_counts": dict(sorted(stop_reasons.items())),
        "execution_control_counts": dict(sorted(execution_controls.items())),
        "mutation_signature_counts": dict(sorted(mutation_signatures.items())),
        "linked_invoice_investigation_rate": (
            linked_invoice_investigations / total if total else 0.0
        ),
        "unsafe_return_resubmit_count": unsafe_return_resubmits,
        "created_without_invoice_investigation_count": (
            created_without_invoice_investigation
        ),
        "tool_error_count": tool_errors,
        "mean_turns": mean(turn_counts) if turn_counts else 0.0,
        "mean_tool_calls": mean(call_counts) if call_counts else 0.0,
        "reports": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Analyze ERPNext sales-return model trajectories."
    )
    parser.add_argument("--run-directory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = analyze_sales_return_runs(args.run_directory)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not result["load_errors"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
