from __future__ import annotations

import hashlib
import json
import shutil
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class TrajectorySource:
    run_id: str
    root: Path
    role: str


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _load_trajectories(
    source: TrajectorySource,
) -> dict[tuple[str, str, str], tuple[Path, dict[str, Any]]]:
    reports: dict[tuple[str, str, str], tuple[Path, dict[str, Any]]] = {}
    for repetition_root in sorted(
        path for path in source.root.rglob("repetition-*") if path.is_dir()
    ):
        repetition = repetition_root.name
        for path in sorted(repetition_root.glob("*.json")):
            if path.name.endswith("-failure.json"):
                continue
            payload = json.loads(path.read_text(encoding="utf-8"))
            if "evaluation" not in payload or "variant" not in payload:
                continue
            scenario_id = str(payload.get("scenario_id", "")).strip()
            variant = str(payload.get("variant", "")).strip()
            if not scenario_id or not variant:
                raise ValueError(f"trajectory has no scenario/variant: {path}")
            key = (scenario_id, repetition, variant)
            if key in reports:
                raise ValueError(
                    f"run {source.run_id} contains duplicate trajectory {key}"
                )
            reports[key] = (path, payload)
    return reports


def assemble_model_coverage(
    *,
    primary: TrajectorySource,
    retries: Iterable[TrajectorySource],
    expected_variants: set[str],
    output_root: Path,
) -> dict[str, Any]:
    """Assemble provider retries without permitting outcome replacement.

    A retry may fill a trajectory that is absent from the primary run. It may
    never replace or duplicate a scored primary trajectory. This makes retry
    provenance auditable and prevents choosing a more favorable second sample.
    """

    if not expected_variants or any(not item for item in expected_variants):
        raise ValueError("expected_variants must contain non-empty identifiers")
    retries = tuple(retries)
    if output_root.exists() and any(output_root.iterdir()):
        raise ValueError("output_root must be absent or empty")
    primary_reports = _load_trajectories(primary)
    if not primary_reports:
        raise ValueError("primary run contains no scored trajectories")
    scenarios = {key[0] for key in primary_reports}
    repetitions = {key[1] for key in primary_reports}
    if len(scenarios) != 1:
        raise ValueError("primary run must contain exactly one scenario")
    scenario_id = next(iter(scenarios))
    execution_controls = {
        bool(payload.get("execution_control", False))
        for _path, payload in primary_reports.values()
    }
    if len(execution_controls) != 1:
        raise ValueError("primary trajectories mix execution-control modes")
    expected_execution_control = next(iter(execution_controls))
    unexpected_primary = {
        key[2] for key in primary_reports if key[2] not in expected_variants
    }
    if unexpected_primary:
        raise ValueError(
            f"primary run contains unexpected variants: {sorted(unexpected_primary)}"
        )

    selected = dict(primary_reports)
    provenance = {
        key: {
            "source_role": primary.role,
            "source_run_id": primary.run_id,
            "source_path": str(path.relative_to(primary.root)),
            "source_sha256": _sha256(path),
        }
        for key, (path, _payload) in primary_reports.items()
    }
    missing_before = {
        (scenario_id, repetition, variant)
        for repetition in repetitions
        for variant in expected_variants
        if (scenario_id, repetition, variant) not in primary_reports
    }
    still_missing = set(missing_before)

    for retry in retries:
        reports = _load_trajectories(retry)
        for key, report in reports.items():
            if key[0] != scenario_id or key[1] not in repetitions:
                raise ValueError(
                    f"retry {retry.run_id} does not match the primary experiment: {key}"
                )
            if key[2] not in expected_variants:
                raise ValueError(
                    f"retry {retry.run_id} contains unexpected variant {key[2]}"
                )
            if bool(report[1].get("execution_control", False)) != (
                expected_execution_control
            ):
                raise ValueError(
                    f"retry {retry.run_id} changes execution-control mode: {key}"
                )
            if key not in missing_before:
                raise ValueError(
                    "retry attempts to replace or duplicate an existing primary "
                    f"trajectory: {key}"
                )
            if key not in still_missing:
                raise ValueError(f"multiple retries provide trajectory {key}")
            path, _payload = report
            selected[key] = report
            provenance[key] = {
                "source_role": retry.role,
                "source_run_id": retry.run_id,
                "source_path": str(path.relative_to(retry.root)),
                "source_sha256": _sha256(path),
            }
            still_missing.remove(key)

    if still_missing:
        missing = ["/".join(key) for key in sorted(still_missing)]
        raise ValueError(f"provider retries did not complete coverage: {missing}")

    output_root.mkdir(parents=True, exist_ok=True)
    rows = []
    for key in sorted(selected):
        _scenario, repetition, variant = key
        source_path, payload = selected[key]
        target = output_root / repetition / f"{variant}.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source_path, target)
        row = {
            "scenario_id": scenario_id,
            "repetition": repetition,
            "variant": variant,
            "execution_control": bool(payload.get("execution_control", False)),
            "passed": bool(payload["evaluation"].get("passed", False)),
            "target_path": str(target.relative_to(output_root)),
            "target_sha256": _sha256(target),
            **provenance[key],
        }
        if row["target_sha256"] != row["source_sha256"]:
            raise RuntimeError(f"trajectory copy changed bytes: {key}")
        rows.append(row)

    manifest = {
        "schema_version": "1.0",
        "artifact_type": "native_model_coverage_assembly",
        "scenario_id": scenario_id,
        "expected_variants": sorted(expected_variants),
        "primary_run_id": primary.run_id,
        "retry_run_ids": [source.run_id for source in retries],
        "missing_primary_variants": sorted({key[2] for key in missing_before}),
        "trajectory_count": len(rows),
        "trajectories": rows,
    }
    manifest_path = output_root / "coverage-manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest


__all__ = ["TrajectorySource", "assemble_model_coverage"]
