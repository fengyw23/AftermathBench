from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean
from typing import Any

from aftermath_bench.integrations.kubernetes_interaction_recovery import (
    KubernetesInteractionEnvironment,
)


def _evidence_groups(calls: list[dict[str, Any]]) -> dict[str, bool]:
    names = [str(call.get("name", "")) for call in calls]
    listed = {
        str(call.get("arguments", {}).get("resource", "")).lower().rstrip("s")
        for call in calls
        if call.get("name") == "list_objects"
    }
    fetched = {
        str(call.get("arguments", {}).get("resource", "")).lower().rstrip("s")
        for call in calls
        if call.get("name") == "get_object"
    }
    return {
        "contracts_and_local_state": "configmap" in listed or "configmap" in fetched,
        "both_consumers": "deployment" in listed or "deployment" in fetched,
        "service_routing": "service" in listed or "service" in fetched,
        "shared_credential": "secret" in listed or "secret" in fetched,
        "controller_ownership": "job" in listed or "job" in fetched,
        "external_registry": "list_external_deliveries" in names,
    }


def _load_reports(root: Path) -> tuple[list[dict[str, Any]], list[str]]:
    reports = []
    errors = []
    for path in sorted(root.rglob("*.json")):
        if path.name.endswith("-failure.json") or path.name in {
            "summary.json",
            "prefix.json",
            "control.json",
        }:
            continue
        try:
            report = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            errors.append(f"{path}: {error}")
            continue
        if (
            report.get("family") != "k8s-constraint-interaction-recovery"
            or "evaluation" not in report
        ):
            continue
        report["_path"] = path.relative_to(root).as_posix()
        reports.append(report)
    return reports, errors


def analyze_kubernetes_interaction_runs(root: Path) -> dict[str, Any]:
    reports, load_errors = _load_reports(root)
    variant_results: dict[str, list[bool]] = defaultdict(list)
    component_totals: Counter[str] = Counter()
    failed_checks: Counter[str] = Counter()
    primary_errors: Counter[str] = Counter()
    semantic_directions: Counter[str] = Counter()
    protocol_violations: Counter[str] = Counter()
    mutation_signatures: Counter[str] = Counter()
    evidence_group_observations: Counter[str] = Counter()
    execution_controls: Counter[str] = Counter()
    unexpected_external_keys: Counter[str] = Counter()
    missing_external_keys: Counter[str] = Counter()
    turn_counts = []
    call_counts = []
    prewrite_query_counts = []
    complete_prewrite_investigations = 0
    rows = []

    for report in reports:
        evaluation = report["evaluation"]
        diagnostics = report.get("trajectory_diagnostics", {})
        evaluator_diagnostics = evaluation.get("diagnostics", {})
        passed = bool(evaluation.get("passed"))
        variant = str(report.get("variant"))
        variant_results[variant].append(passed)
        execution_controls[str(bool(report.get("execution_control"))).lower()] += 1
        for component, value in evaluation.get("components", {}).items():
            component_totals[str(component)] += int(bool(value))
        for check, value in evaluation.get("checks", {}).items():
            if not value:
                failed_checks[str(check)] += 1

        primary_error = diagnostics.get("primary_error")
        if primary_error:
            primary_errors[str(primary_error)] += 1
        direction = str(
            evaluator_diagnostics.get("semantic_recovery_direction")
            or diagnostics.get("semantic_recovery_direction")
            or "unknown"
        )
        semantic_directions[direction] += 1
        for name, observed in diagnostics.get("evidence_groups", {}).items():
            evidence_group_observations[str(name)] += int(bool(observed))
        for violation in evaluator_diagnostics.get(
            "protocol_violations", ()
        ):
            protocol_violations[str(violation)] += 1

        allowed = set(
            map(str, evaluator_diagnostics.get("allowed_external_keys", ()))
        )
        actual = set(
            map(str, evaluator_diagnostics.get("actual_external_keys", ()))
        )
        for key in actual - allowed:
            unexpected_external_keys[key] += 1
        for key in allowed - actual:
            missing_external_keys[key] += 1

        selected = tuple(map(str, diagnostics.get("selected_mutations", ())))
        mutation_signatures[" -> ".join(selected) or "<no mutation>"] += 1
        turns = len(report.get("turns", ()))
        ordered_calls = [
            call
            for turn in report.get("turns", ())
            for call in turn.get("tool_calls", ())
        ]
        calls = len(ordered_calls)
        mutation_tools = set(KubernetesInteractionEnvironment.MUTATION_TOOLS)
        first_mutation = next(
            (
                index
                for index, call in enumerate(ordered_calls)
                if str(call.get("name")) in mutation_tools
            ),
            len(ordered_calls),
        )
        prewrite_calls = ordered_calls[:first_mutation]
        prewrite_evidence = _evidence_groups(prewrite_calls)
        complete_prewrite = all(prewrite_evidence.values())
        complete_prewrite_investigations += int(complete_prewrite)
        prewrite_query_counts.append(len(prewrite_calls))
        turn_counts.append(turns)
        call_counts.append(calls)
        rows.append(
            {
                "variant": variant,
                "passed": passed,
                "execution_control": bool(report.get("execution_control")),
                "primary_error": primary_error,
                "semantic_recovery_direction": direction,
                "turns": turns,
                "tool_calls": calls,
                "prewrite_query_calls": len(prewrite_calls),
                "prewrite_evidence_groups": prewrite_evidence,
                "complete_investigation_before_first_mutation": complete_prewrite,
                "selected_mutations": list(selected),
                "allowed_external_keys": sorted(allowed),
                "actual_external_keys": sorted(actual),
                "unexpected_external_keys": sorted(actual - allowed),
                "missing_external_keys": sorted(allowed - actual),
                "protocol_violations": list(
                    evaluator_diagnostics.get("protocol_violations", ())
                ),
                "path": report["_path"],
            }
        )

    total = len(reports)
    matched = bool(reports) and all(row["passed"] for row in rows)
    return {
        "schema_version": "0.1",
        "completed_runs": total,
        "load_errors": load_errors,
        "task_pass_rate": (
            sum(row["passed"] for row in rows) / total if total else 0.0
        ),
        "matched_group_success": matched,
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
        "semantic_recovery_direction_counts": dict(
            sorted(semantic_directions.items())
        ),
        "evidence_group_observation_counts": dict(
            sorted(evidence_group_observations.items())
        ),
        "protocol_violation_counts": dict(
            sorted(protocol_violations.items())
        ),
        "unexpected_external_key_counts": dict(
            sorted(unexpected_external_keys.items())
        ),
        "missing_external_key_counts": dict(
            sorted(missing_external_keys.items())
        ),
        "execution_control_counts": dict(sorted(execution_controls.items())),
        "mutation_signature_counts": dict(sorted(mutation_signatures.items())),
        "mean_turns": mean(turn_counts) if turn_counts else 0.0,
        "mean_tool_calls": mean(call_counts) if call_counts else 0.0,
        "mean_prewrite_query_calls": (
            mean(prewrite_query_counts) if prewrite_query_counts else 0.0
        ),
        "complete_prewrite_investigation_rate": (
            complete_prewrite_investigations / total if total else 0.0
        ),
        "reports": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Analyze Kubernetes constraint-interaction trajectories."
    )
    parser.add_argument("--run-directory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = analyze_kubernetes_interaction_runs(args.run_directory)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not result["load_errors"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
