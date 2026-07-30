from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _metadata_path(root: Path, names: tuple[str, ...]) -> Path:
    matches = [root / name for name in names if (root / name).is_file()]
    if len(matches) != 1:
        raise ValueError(
            f"expected exactly one of {names!r} under {root}, "
            f"found {len(matches)}"
        )
    return matches[0]


def load_experiment_metadata(
    root: str | Path,
    *,
    condition: str,
) -> dict[str, Any]:
    directory = Path(root)
    if condition == "control":
        path = _metadata_path(directory, ("control.json", "experiment.json"))
    elif condition == "ordinary":
        path = _metadata_path(directory, ("experiment.json",))
    else:
        raise ValueError(f"unknown condition: {condition}")
    return json.loads(path.read_text(encoding="utf-8"))


def _variants(metadata: dict[str, Any]) -> set[str]:
    return {
        str(report["variant"])
        for report in metadata.get("reports", ())
        if report.get("variant")
    }


def compare_paired_experiments(
    control: dict[str, Any],
    ordinary: dict[str, Any],
) -> dict[str, Any]:
    control_variants = _variants(control)
    ordinary_variants = _variants(ordinary)
    control_prefix = control.get("supporting_files", {}).get("prefix.json")
    ordinary_prefix = ordinary.get("supporting_files", {}).get("prefix.json")
    threshold = float(control.get("control_min_pass_rate", 0.8))
    checks = {
        "scenario_matches": bool(control.get("scenario_id"))
        and control.get("scenario_id") == ordinary.get("scenario_id"),
        "source_commit_matches": len(str(control.get("head_sha", ""))) == 40
        and control.get("head_sha") == ordinary.get("head_sha"),
        "model_matches": bool(control.get("model"))
        and control.get("model") == ordinary.get("model"),
        "prefix_matches": bool(control_prefix)
        and control_prefix == ordinary_prefix,
        "conditions_are_paired": control.get("execution_control") is True
        and ordinary.get("execution_control") is False,
        "variant_sets_match": bool(control_variants)
        and control_variants == ordinary_variants,
        "control_meets_execution_threshold": float(
            control.get("task_pass_rate", 0.0)
        )
        >= threshold,
        "control_has_no_infrastructure_errors": int(
            control.get("provider_or_runtime_error_count", -1)
        )
        == 0,
        "ordinary_has_no_infrastructure_errors": int(
            ordinary.get("provider_or_runtime_error_count", -1)
        )
        == 0,
        "control_has_no_tool_errors": int(
            control.get("tool_error_count", -1)
        )
        == 0,
        "ordinary_has_no_tool_errors": int(
            ordinary.get("tool_error_count", -1)
        )
        == 0,
        "archives_have_no_credentials": (
            control.get("credentials_present") is False
            and ordinary.get("credentials_present") is False
        ),
    }
    control_rate = float(control.get("task_pass_rate", 0.0))
    ordinary_rate = float(ordinary.get("task_pass_rate", 0.0))
    return {
        "schema_version": "0.1",
        "valid_pair": all(checks.values()),
        "checks": checks,
        "scenario_id": ordinary.get("scenario_id"),
        "head_sha": ordinary.get("head_sha"),
        "model": ordinary.get("model"),
        "variants": sorted(ordinary_variants),
        "control_completed_runs": int(control.get("completed_runs", 0)),
        "ordinary_completed_runs": int(ordinary.get("completed_runs", 0)),
        "control_task_pass_rate": control_rate,
        "ordinary_task_pass_rate": ordinary_rate,
        "absolute_control_gap": control_rate - ordinary_rate,
        "control_matched_group_success_rate": float(
            control.get("matched_group_success_rate", 0.0)
        ),
        "ordinary_matched_group_success_rate": float(
            ordinary.get("matched_group_success_rate", 0.0)
        ),
    }
