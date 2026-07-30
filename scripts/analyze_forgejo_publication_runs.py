from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from statistics import mean
from typing import Any

from aftermath_bench.native_forgejo_publication_family import (
    FORGEJO_PUBLICATION_MUTATIONS,
)


def _load_reports(root: Path) -> tuple[list[dict[str, Any]], list[str]]:
    reports: list[dict[str, Any]] = []
    errors: list[str] = []
    for path in sorted(root.rglob("*.json")):
        if path.name.endswith("-failure.json") or path.name in {
            "analysis.json",
            "prefix.json",
            "summary.json",
        }:
            continue
        try:
            report = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            errors.append(f"{path}: {error}")
            continue
        if "evaluation" not in report or "variant" not in report:
            continue
        report["_path"] = path.as_posix()
        reports.append(report)
    return reports, errors


def _ordered_calls(report: dict[str, Any]) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    for turn in report.get("turns", ()):
        results = {
            result.get("call_id"): result.get("result")
            for result in turn.get("tool_results", ())
        }
        for call in turn.get("tool_calls", ()):
            calls.append(
                {
                    "turn": turn.get("turn"),
                    "name": str(call.get("name")),
                    "arguments": call.get("arguments", {}),
                    "result": results.get(call.get("call_id")),
                }
            )
    return calls


def _evidence_status(calls: list[dict[str, Any]]) -> dict[str, bool]:
    names = [call["name"] for call in calls]
    return {
        # list_releases returns each Release's native asset list, so a
        # separate list_release_assets call is not required to establish the
        # pre-write scope.
        "publication_manifest": "get_repository_file" in names,
        "target_release_and_assets": "list_releases" in names,
        "both_native_delivery_histories": (
            names.count("get_webhook_history") >= 2
        ),
        "external_receiver_ledger": (
            "list_external_deliveries" in names
        ),
    }


def _tool_result_failed(result: Any) -> bool:
    return isinstance(result, dict) and result.get("ok") is False


def _derive_stage(
    *,
    evaluation: dict[str, Any],
    complete_evidence_before_write: bool,
    tool_error_count: int,
    verified_after_write: bool,
) -> str:
    if evaluation.get("passed"):
        return "pass"
    components = evaluation.get("components", {})
    if not complete_evidence_before_write:
        return "investigation_failure"
    if not components.get("preservation", False):
        return "over_repair_scope_failure"
    if not components.get("protocol_safety", False):
        return "state_inference_or_replay_scope_failure"
    if tool_error_count:
        return "execution_failure"
    if (
        not components.get("goal_completion", False)
        or not components.get("repair_completeness", False)
    ):
        return "under_repair_scope_failure"
    if not verified_after_write:
        return "verification_failure"
    return "unclassified_terminal_failure"


def analyze(root: Path) -> dict[str, Any]:
    reports, load_errors = _load_reports(root)
    component_totals: Counter[str] = Counter()
    failed_checks: Counter[str] = Counter()
    recorded_errors: Counter[str] = Counter()
    derived_stages: Counter[str] = Counter()
    mutation_signatures: Counter[str] = Counter()
    rows = []

    for report in reports:
        calls = _ordered_calls(report)
        first_mutation = next(
            (
                index
                for index, call in enumerate(calls)
                if call["name"] in FORGEJO_PUBLICATION_MUTATIONS
            ),
            len(calls),
        )
        last_mutation = next(
            (
                index
                for index in range(len(calls) - 1, -1, -1)
                if calls[index]["name"]
                in FORGEJO_PUBLICATION_MUTATIONS
            ),
            -1,
        )
        before = _evidence_status(calls[:first_mutation])
        anytime = _evidence_status(calls)
        complete_before = all(before.values())
        complete_anytime = all(anytime.values())
        mutations = [
            call for call in calls
            if call["name"] in FORGEJO_PUBLICATION_MUTATIONS
        ]
        mutation_tool_error_count = sum(
            _tool_result_failed(call["result"]) for call in mutations
        )
        query_negative_result_count = sum(
            _tool_result_failed(call["result"])
            for call in calls
            if call["name"] not in FORGEJO_PUBLICATION_MUTATIONS
        )
        verification_requirements: list[bool] = []
        publication_indices = [
            index
            for index, call in enumerate(calls)
            if call["name"]
            in {
                "create_release",
                "upload_release_asset_from_repository",
            }
        ]
        if publication_indices:
            verification_requirements.append(
                any(
                    call["name"]
                    in {"list_releases", "list_release_assets"}
                    for call in calls[max(publication_indices) + 1 :]
                )
            )
        replay_indices = [
            index
            for index, call in enumerate(calls)
            if call["name"] == "replay_webhook"
        ]
        if replay_indices:
            verification_requirements.append(
                any(
                    call["name"]
                    in {
                        "get_external_delivery",
                        "list_external_deliveries",
                        "wait_for_release_delivery",
                    }
                    for call in calls[max(replay_indices) + 1 :]
                )
            )
        close_indices = [
            index
            for index, call in enumerate(calls)
            if call["name"] == "close_milestone"
        ]
        if close_indices:
            verification_requirements.append(
                any(
                    call["name"] == "get_milestone"
                    for call in calls[max(close_indices) + 1 :]
                )
            )
        verified_after_write = (
            all(verification_requirements)
            if verification_requirements
            else last_mutation < 0
        )
        signature = ",".join(call["name"] for call in mutations) or "no_write"
        mutation_signatures[signature] += 1

        evaluation = report["evaluation"]
        for component, value in evaluation.get("components", {}).items():
            component_totals[str(component)] += int(bool(value))
        for check, value in evaluation.get("checks", {}).items():
            if not value:
                failed_checks[str(check)] += 1
        recorded_error = report.get("trajectory_diagnostics", {}).get(
            "primary_error"
        )
        if recorded_error:
            recorded_errors[str(recorded_error)] += 1
        derived_stage = _derive_stage(
            evaluation=evaluation,
            complete_evidence_before_write=complete_before,
            tool_error_count=mutation_tool_error_count,
            verified_after_write=verified_after_write,
        )
        derived_stages[derived_stage] += 1
        rows.append(
            {
                "variant": report["variant"],
                "passed": bool(evaluation.get("passed")),
                "execution_control": bool(
                    report.get("execution_control", False)
                ),
                "turn_count": len(report.get("turns", ())),
                "query_call_count": len(calls) - len(mutations),
                "mutation_call_count": len(mutations),
                "mutation_signature": signature,
                "mutation_arguments": [
                    {
                        "name": call["name"],
                        "arguments": call["arguments"],
                    }
                    for call in mutations
                ],
                "mutation_tool_error_count": mutation_tool_error_count,
                "query_negative_result_count": (
                    query_negative_result_count
                ),
                "evidence_complete_before_first_write": complete_before,
                "evidence_complete_at_any_time": complete_anytime,
                "evidence_before_first_write": before,
                "verified_after_last_write": verified_after_write,
                "recorded_primary_error": recorded_error,
                "derived_failure_stage": derived_stage,
                "failed_checks": sorted(
                    check
                    for check, value in evaluation.get("checks", {}).items()
                    if not value
                ),
                "path": report["_path"],
            }
        )

    total = len(reports)
    passed = sum(row["passed"] for row in rows)
    return {
        "schema_version": "0.1",
        "completed_runs": total,
        "load_errors": load_errors,
        "task_pass_rate": passed / total if total else 0,
        "component_pass_rates": {
            component: count / total if total else 0
            for component, count in sorted(component_totals.items())
        },
        "evidence_complete_before_first_write_rate": (
            sum(row["evidence_complete_before_first_write"] for row in rows)
            / total
            if total
            else 0
        ),
        "evidence_complete_at_any_time_rate": (
            sum(row["evidence_complete_at_any_time"] for row in rows)
            / total
            if total
            else 0
        ),
        "post_write_verification_rate": (
            sum(row["verified_after_last_write"] for row in rows) / total
            if total
            else 0
        ),
        "mutation_tool_error_count": sum(
            row["mutation_tool_error_count"] for row in rows
        ),
        "query_negative_result_count": sum(
            row["query_negative_result_count"] for row in rows
        ),
        "failed_check_counts": dict(sorted(failed_checks.items())),
        "recorded_primary_error_counts": dict(
            sorted(recorded_errors.items())
        ),
        "derived_failure_stage_counts": dict(
            sorted(derived_stages.items())
        ),
        "mutation_signature_counts": dict(
            sorted(mutation_signatures.items())
        ),
        "mean_turn_count": (
            mean(row["turn_count"] for row in rows) if rows else 0
        ),
        "mean_query_call_count": (
            mean(row["query_call_count"] for row in rows) if rows else 0
        ),
        "mean_mutation_call_count": (
            mean(row["mutation_call_count"] for row in rows)
            if rows
            else 0
        ),
        "reports": rows,
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
        newline="\n",
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not result["load_errors"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
