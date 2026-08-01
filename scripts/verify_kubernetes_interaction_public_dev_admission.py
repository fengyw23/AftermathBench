from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from aftermath_bench.integrations.kubernetes_interaction_baselines import (
    INTERACTION_BASELINES,
)
from aftermath_bench.integrations.kubernetes_interaction_prefix import (
    SCENARIO_ID,
)
from aftermath_bench.integrations.kubernetes_interaction_scope import (
    KUBERNETES_INTERACTION_VARIANTS,
)


def _read(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError(f"expected JSON object: {path}")
    return payload


def _valid_bundle_manifest(payload: dict[str, Any]) -> bool:
    files = payload.get("files")
    if (
        payload.get("schema_version") != "1.0"
        or payload.get("capture_mode")
        != "etcd_snapshot_and_quiesced_registry_sqlite"
        or not isinstance(payload.get("cluster_name"), str)
        or not payload.get("cluster_name")
        or not isinstance(payload.get("node_image"), str)
        or "@sha256:" not in payload.get("node_image", "")
        or not isinstance(files, dict)
        or set(files) != {"etcd", "external_registry"}
    ):
        return False
    return all(
        isinstance(item, dict)
        and set(item) == {"path", "bytes", "sha256"}
        and isinstance(item.get("path"), str)
        and bool(item.get("path"))
        and isinstance(item.get("bytes"), int)
        and item["bytes"] > 0
        and isinstance(item.get("sha256"), str)
        and len(item["sha256"]) == 64
        for item in files.values()
    )


def verify_public_dev_admission(run_root: Path) -> dict[str, Any]:
    runtime_summary = _read(run_root / "runtime-summary.json")
    baseline_summary = _read(run_root / "baselines" / "summary.json")
    admission = _read(
        run_root / "admitted-scenario" / "artifacts" / "admission.json"
    )
    admitted_scenario = _read(run_root / "admitted-scenario" / "scenario.json")
    runtime_reports = [
        _read(run_root / "runtime" / f"{variant}-reference.json")
        for variant in KUBERNETES_INTERACTION_VARIANTS
    ]
    bundle_manifests = [
        _read(
            run_root
            / "runtime"
            / "bundle-manifests"
            / f"{variant}.json"
        )
        for variant in KUBERNETES_INTERACTION_VARIANTS
    ]
    baseline_reports = [
        _read(run_root / "baselines" / f"{baseline}-{variant}.json")
        for baseline in INTERACTION_BASELINES
        for variant in KUBERNETES_INTERACTION_VARIANTS
    ]
    exact_reference_pairs = [
        (
            run_root
            / "runtime"
            / "state-evidence"
            / f"{variant}-boundary.json",
            run_root
            / "runtime"
            / "state-evidence"
            / f"{variant}-reference-start.json",
        )
        for variant in KUBERNETES_INTERACTION_VARIANTS
    ]
    exact_policy_pairs = [
        (
            run_root
            / "runtime"
            / "state-evidence"
            / f"{variant}-boundary.json",
            run_root
            / "baselines"
            / "pre-state"
            / f"{baseline}-{variant}.json",
        )
        for baseline in INTERACTION_BASELINES
        for variant in KUBERNETES_INTERACTION_VARIANTS
    ]

    def exact_pairs_pass(
        pairs: list[tuple[Path, Path]],
    ) -> bool:
        return all(
            expected.is_file()
            and observed.is_file()
            and expected.read_bytes() == observed.read_bytes()
            for expected, observed in pairs
        )

    heuristic_rows = baseline_summary.get("heuristics", [])
    checks = {
        "runtime_scenario_matches_active_instance": (
            runtime_summary.get("scenario_id") == SCENARIO_ID
        ),
        "all_thirteen_boundaries_and_references_pass": (
            runtime_summary.get("passed") is True
            and runtime_summary.get("variant_count")
            == len(KUBERNETES_INTERACTION_VARIANTS)
            and runtime_summary.get("reference_pass_count")
            == len(KUBERNETES_INTERACTION_VARIANTS)
        ),
        "all_thirteen_native_bundle_manifests_are_pinned": (
            len(bundle_manifests) == len(KUBERNETES_INTERACTION_VARIANTS)
            and all(_valid_bundle_manifest(item) for item in bundle_manifests)
            and len(
                {
                    item["files"]["etcd"]["sha256"]
                    for item in bundle_manifests
                }
            )
            == len(KUBERNETES_INTERACTION_VARIANTS)
        ),
        "reference_reports_match_active_instance": all(
            report.get("scenario_id") == SCENARIO_ID
            and report.get("evaluation", {}).get("passed") is True
            and report.get("control_error") is None
            for report in runtime_reports
        ),
        "references_start_from_exact_admitted_boundaries": (
            exact_pairs_pass(exact_reference_pairs)
        ),
        "all_fixed_policy_reports_present": (
            len(baseline_reports)
            == len(INTERACTION_BASELINES)
            * len(KUBERNETES_INTERACTION_VARIANTS)
            and len(heuristic_rows) == len(INTERACTION_BASELINES)
        ),
        "fixed_policy_reports_match_active_instance": all(
            report.get("scenario_id") == SCENARIO_ID
            for report in baseline_reports
        ),
        "fixed_policies_start_from_exact_admitted_boundaries": (
            exact_pairs_pass(exact_policy_pairs)
        ),
        "fixed_policy_hard_gate_passes": (
            baseline_summary.get("hard_fixed_policy_gate_passed") is True
            and float(
                baseline_summary.get("maximum_heuristic_pass_rate", 1.0)
            )
            < 0.5
            and not baseline_summary.get("matched_group_solvers", [])
        ),
        "hard_admission_passes": (
            admission.get("scenario_id") == SCENARIO_ID
            and admission.get("passed") is True
            and admission.get("admitted_tier") == "hard"
            and admitted_scenario.get("scenario_id") == SCENARIO_ID
            and admitted_scenario.get("benchmark_tier") == "hard"
            and admitted_scenario.get("admission_status") == "validated"
        ),
    }
    return {
        "schema_version": "1.0",
        "scenario_id": SCENARIO_ID,
        "reference_report_count": len(runtime_reports),
        "native_bundle_manifest_count": len(bundle_manifests),
        "fixed_policy_report_count": len(baseline_reports),
        "exact_replay_comparison_count": (
            len(exact_reference_pairs) + len(exact_policy_pairs)
        ),
        "maximum_heuristic_pass_rate": baseline_summary.get(
            "maximum_heuristic_pass_rate"
        ),
        "matched_group_solvers": baseline_summary.get(
            "matched_group_solvers", []
        ),
        "checks": checks,
        "passed": all(checks.values()),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-directory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = verify_public_dev_admission(args.run_directory.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
