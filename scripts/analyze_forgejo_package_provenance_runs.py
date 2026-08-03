from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from statistics import mean
from typing import Any

from aftermath_bench.native_forgejo_package_provenance_family import (
    FORGEJO_PACKAGE_PROVENANCE_MUTATIONS,
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
        if report.get("family") != "forgejo-package-provenance":
            continue
        report["_path"] = path.as_posix()
        reports.append(report)
    return reports, errors


def _calls(report: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        call
        for turn in report.get("turns", ())
        for call in turn.get("tool_calls", ())
    ]


def _evidence(names: list[str]) -> dict[str, bool]:
    return {
        "package_inventory": (
            ("list_packages" in names or "get_package_version" in names)
            and "list_package_files" in names
        ),
        # The approved base branch already contains the merged provenance
        # manifest. Reading the manifest and a declared source file is an
        # authoritative route; the historical Pull Request is optional.
        "repository_manifest_and_source": names.count("get_repository_file") >= 2,
        "release_state": "list_releases" in names,
        "hook_inventory_and_histories": (
            "list_hooks" in names and names.count("get_webhook_history") >= 2
        ),
        "receiver_ledger": "list_external_deliveries" in names,
    }


def _scope_polarity(variant: str, mutations: list[str]) -> bool:
    deleted = "delete_package_version" in mutations
    if variant == "r2_package_corrupt_binary_index_missing":
        return deleted
    if variant.startswith("r2_"):
        return not deleted
    return True


def analyze(root: Path) -> dict[str, Any]:
    reports, load_errors = _load_reports(root)
    rows: list[dict[str, Any]] = []
    failure_types: Counter[str] = Counter()
    failed_checks: Counter[str] = Counter()
    mutation_signatures: Counter[str] = Counter()

    for report in reports:
        calls = _calls(report)
        names = [str(call.get("name")) for call in calls]
        first_write = next(
            (
                index
                for index, name in enumerate(names)
                if name in FORGEJO_PACKAGE_PROVENANCE_MUTATIONS
            ),
            len(names),
        )
        evidence_before = _evidence(names[:first_write])
        evidence_anytime = _evidence(names)
        mutations = [
            name
            for name in names
            if name in FORGEJO_PACKAGE_PROVENANCE_MUTATIONS
        ]
        signature = ",".join(mutations) or "no_write"
        mutation_signatures[signature] += 1
        evaluation = report.get("evaluation", {})
        diagnostics = report.get("trajectory_diagnostics", {})
        primary_error = diagnostics.get("primary_error")
        if primary_error:
            failure_types[str(primary_error)] += 1
        for check, passed in evaluation.get("checks", {}).items():
            if not passed:
                failed_checks[str(check)] += 1
        variant = str(report.get("variant"))
        rows.append(
            {
                "model": str(report.get("model")),
                "variant": variant,
                "passed": bool(evaluation.get("passed")),
                "execution_control": bool(report.get("execution_control")),
                "turn_count": len(report.get("turns", ())),
                "query_call_count": sum(
                    name not in FORGEJO_PACKAGE_PROVENANCE_MUTATIONS
                    for name in names
                ),
                "prewrite_query_call_count": first_write,
                "mutation_call_count": len(mutations),
                "mutation_signature": signature,
                "scope_polarity_correct": _scope_polarity(variant, mutations),
                "evidence_complete_before_first_write": all(
                    evidence_before.values()
                ),
                "evidence_complete_at_any_time": all(
                    evidence_anytime.values()
                ),
                "evidence_before_first_write": evidence_before,
                "recorded_primary_error": primary_error,
                "failed_checks": sorted(
                    check
                    for check, passed in evaluation.get("checks", {}).items()
                    if not passed
                ),
                "path": report["_path"],
            }
        )

    by_model: dict[str, dict[str, Any]] = {}
    for model in sorted({row["model"] for row in rows}):
        selected = [row for row in rows if row["model"] == model]
        variants = {row["variant"]: row for row in selected}
        valid = variants.get("r2_package_complete_index_missing")
        corrupt = variants.get("r2_package_corrupt_binary_index_missing")
        pair_polarity = bool(
            valid
            and corrupt
            and valid["scope_polarity_correct"]
            and corrupt["scope_polarity_correct"]
        )
        by_model[model] = {
            "completed_runs": len(selected),
            "task_pass_rate": (
                sum(row["passed"] for row in selected) / len(selected)
                if selected
                else 0
            ),
            "matched_group_success": bool(selected)
            and all(row["passed"] for row in selected),
            "same_inventory_pair_scope_polarity_correct": pair_polarity,
            "evidence_complete_before_first_write_rate": (
                sum(
                    row["evidence_complete_before_first_write"]
                    for row in selected
                )
                / len(selected)
                if selected
                else 0
            ),
        }

    return {
        "schema_version": "0.1",
        "completed_runs": len(rows),
        "load_errors": load_errors,
        "model_results": by_model,
        "failure_type_counts": dict(sorted(failure_types.items())),
        "failed_check_counts": dict(sorted(failed_checks.items())),
        "mutation_signature_counts": dict(sorted(mutation_signatures.items())),
        "mean_turn_count": mean(row["turn_count"] for row in rows) if rows else 0,
        "rows": rows,
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
