from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .strict_json import load_json_strict

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_ARTIFACT_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_ID = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
_COMPONENTS = frozenset(
    {
        "goal_completion",
        "repair_completeness",
        "preservation",
        "protocol_safety",
    }
)
_GATE_FIELDS = frozenset({"schema_version", "stage", "sources"})
_SOURCE_FIELDS = frozenset(
    {
        "evidence_id",
        "source_run_id",
        "source_commit",
        "source_workflow",
        "artifact_id",
        "artifact_name",
        "artifact_digest",
        "artifact_size_in_bytes",
        "scenario_id",
        "scenario_path",
        "scenario_sha256",
        "expected_variant_ids",
        "conditions",
    }
)
_CONDITION_FIELDS = frozenset(
    {
        "condition_id",
        "model",
        "provider",
        "provider_service",
        "repetition",
        "summary_path",
        "trajectory_root",
        "accounting_status",
    }
)


class ModelEvidenceImportError(ValueError):
    """Raised when a model artifact cannot enter the evidence archive."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _safe_relative(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise ModelEvidenceImportError(f"{label} is invalid")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise ModelEvidenceImportError(f"{label} is unsafe")
    return path.as_posix()


def _exact_mapping(value: Any, fields: frozenset[str], *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != fields:
        raise ModelEvidenceImportError(f"{label} fields are not exact")
    return value


@dataclass(frozen=True)
class ModelEvidenceCondition:
    condition_id: str
    model: str
    provider: str
    provider_service: str
    repetition: int
    summary_path: str
    trajectory_root: str
    accounting_status: str

    @classmethod
    def from_mapping(cls, value: Any) -> "ModelEvidenceCondition":
        item = _exact_mapping(value, _CONDITION_FIELDS, label="condition")
        condition_id = str(item.get("condition_id", ""))
        if _ID.fullmatch(condition_id) is None:
            raise ModelEvidenceImportError("condition_id is invalid")
        for field in ("model", "provider", "provider_service"):
            if not isinstance(item.get(field), str) or not item[field]:
                raise ModelEvidenceImportError(f"{field} is invalid")
        repetition = item.get("repetition")
        if type(repetition) is not int or repetition < 1:
            raise ModelEvidenceImportError("repetition is invalid")
        status = item.get("accounting_status")
        if status != "ordinary-model-tested":
            raise ModelEvidenceImportError(
                "artifact import only accepts ordinary-model-tested evidence"
            )
        return cls(
            condition_id=condition_id,
            model=str(item["model"]),
            provider=str(item["provider"]),
            provider_service=str(item["provider_service"]),
            repetition=repetition,
            summary_path=_safe_relative(item["summary_path"], label="summary_path"),
            trajectory_root=_safe_relative(
                item["trajectory_root"], label="trajectory_root"
            ),
            accounting_status=str(status),
        )


@dataclass(frozen=True)
class ModelEvidenceSource:
    evidence_id: str
    source_run_id: int
    source_commit: str
    source_workflow: str
    artifact_id: int
    artifact_name: str
    artifact_digest: str
    artifact_size_in_bytes: int
    scenario_id: str
    scenario_path: str
    scenario_sha256: str
    expected_variant_ids: tuple[str, ...]
    conditions: tuple[ModelEvidenceCondition, ...]

    @classmethod
    def from_mapping(cls, value: Any) -> "ModelEvidenceSource":
        item = _exact_mapping(value, _SOURCE_FIELDS, label="source")
        evidence_id = str(item.get("evidence_id", ""))
        if _ID.fullmatch(evidence_id) is None:
            raise ModelEvidenceImportError("evidence_id is invalid")
        run_id = item.get("source_run_id")
        artifact_id = item.get("artifact_id")
        size = item.get("artifact_size_in_bytes")
        if type(run_id) is not int or run_id < 1:
            raise ModelEvidenceImportError("source_run_id is invalid")
        if type(artifact_id) is not int or artifact_id < 1:
            raise ModelEvidenceImportError("artifact_id is invalid")
        if type(size) is not int or size < 1:
            raise ModelEvidenceImportError("artifact_size_in_bytes is invalid")
        commit = str(item.get("source_commit", ""))
        if _COMMIT.fullmatch(commit) is None:
            raise ModelEvidenceImportError("source_commit is invalid")
        workflow = _safe_relative(item.get("source_workflow"), label="source_workflow")
        if not workflow.startswith(".github/workflows/"):
            raise ModelEvidenceImportError("source_workflow is outside workflows")
        artifact_name = str(item.get("artifact_name", ""))
        if not artifact_name or not artifact_name.endswith(str(run_id)):
            raise ModelEvidenceImportError("artifact_name is not bound to run id")
        digest = str(item.get("artifact_digest", ""))
        if _ARTIFACT_DIGEST.fullmatch(digest) is None:
            raise ModelEvidenceImportError("artifact_digest is invalid")
        scenario_id = str(item.get("scenario_id", ""))
        if _ID.fullmatch(scenario_id) is None:
            raise ModelEvidenceImportError("scenario_id is invalid")
        scenario_path = _safe_relative(item.get("scenario_path"), label="scenario_path")
        scenario_sha = str(item.get("scenario_sha256", ""))
        if _SHA256.fullmatch(scenario_sha) is None:
            raise ModelEvidenceImportError("scenario_sha256 is invalid")
        variants_raw = item.get("expected_variant_ids")
        if not isinstance(variants_raw, Sequence) or isinstance(variants_raw, str):
            raise ModelEvidenceImportError("expected_variant_ids is invalid")
        variants = tuple(str(variant) for variant in variants_raw)
        if not variants or len(set(variants)) != len(variants):
            raise ModelEvidenceImportError("expected_variant_ids are empty or duplicated")
        if any(_ID.fullmatch(variant) is None for variant in variants):
            raise ModelEvidenceImportError("expected_variant_ids contain invalid values")
        conditions_raw = item.get("conditions")
        if not isinstance(conditions_raw, Sequence) or isinstance(conditions_raw, str):
            raise ModelEvidenceImportError("conditions are invalid")
        conditions = tuple(
            ModelEvidenceCondition.from_mapping(condition)
            for condition in conditions_raw
        )
        if not conditions or len({item.condition_id for item in conditions}) != len(conditions):
            raise ModelEvidenceImportError("conditions are empty or duplicated")
        return cls(
            evidence_id=evidence_id,
            source_run_id=run_id,
            source_commit=commit,
            source_workflow=workflow,
            artifact_id=artifact_id,
            artifact_name=artifact_name,
            artifact_digest=digest,
            artifact_size_in_bytes=size,
            scenario_id=scenario_id,
            scenario_path=scenario_path,
            scenario_sha256=scenario_sha,
            expected_variant_ids=variants,
            conditions=conditions,
        )


@dataclass(frozen=True)
class ModelEvidenceImportGate:
    sources: tuple[ModelEvidenceSource, ...]

    @classmethod
    def from_mapping(cls, value: Any) -> "ModelEvidenceImportGate":
        item = _exact_mapping(value, _GATE_FIELDS, label="gate")
        if item.get("schema_version") != "1.0":
            raise ModelEvidenceImportError("gate schema_version is invalid")
        if item.get("stage") != "ordinary-model-evidence-import":
            raise ModelEvidenceImportError("gate stage is invalid")
        sources_raw = item.get("sources")
        if not isinstance(sources_raw, Sequence) or isinstance(sources_raw, str):
            raise ModelEvidenceImportError("gate sources are invalid")
        sources = tuple(ModelEvidenceSource.from_mapping(source) for source in sources_raw)
        if not sources or len({source.evidence_id for source in sources}) != len(sources):
            raise ModelEvidenceImportError("gate sources are empty or duplicated")
        if len({source.source_run_id for source in sources}) != len(sources):
            raise ModelEvidenceImportError("source_run_id is duplicated")
        return cls(sources=sources)

    @classmethod
    def from_path(cls, path: str | Path) -> "ModelEvidenceImportGate":
        return cls.from_mapping(load_json_strict(path))

    def source(self, evidence_id: str) -> ModelEvidenceSource:
        matches = [source for source in self.sources if source.evidence_id == evidence_id]
        if len(matches) != 1:
            raise ModelEvidenceImportError(f"unknown evidence_id: {evidence_id}")
        return matches[0]


def validate_source_provenance(
    run: Any,
    artifacts: Any,
    *,
    source: ModelEvidenceSource,
) -> dict[str, Any]:
    if not isinstance(run, Mapping):
        raise ModelEvidenceImportError("source run metadata is invalid")
    checks = {
        "run_id": run.get("id") == source.source_run_id,
        "commit": run.get("head_sha") == source.source_commit,
        "status": run.get("status") == "completed",
        "conclusion": run.get("conclusion") == "success",
        "workflow": run.get("path") == source.source_workflow,
    }
    if not isinstance(artifacts, Mapping) or not isinstance(artifacts.get("artifacts"), list):
        raise ModelEvidenceImportError("artifact metadata is invalid")
    matches = [
        item
        for item in artifacts["artifacts"]
        if isinstance(item, Mapping) and item.get("id") == source.artifact_id
    ]
    checks.update(
        {
            "artifact_unique": len(matches) == 1,
            "artifact_name": len(matches) == 1
            and matches[0].get("name") == source.artifact_name,
            "artifact_digest": len(matches) == 1
            and matches[0].get("digest") == source.artifact_digest,
            "artifact_size": len(matches) == 1
            and matches[0].get("size_in_bytes") == source.artifact_size_in_bytes,
            "artifact_not_expired": len(matches) == 1
            and matches[0].get("expired") is False,
        }
    )
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise ModelEvidenceImportError(
            "source provenance failed: " + ", ".join(failures)
        )
    return {
        "schema_version": "1.0",
        "evidence_id": source.evidence_id,
        "source_run_id": source.source_run_id,
        "source_commit": source.source_commit,
        "source_workflow": source.source_workflow,
        "artifact_id": source.artifact_id,
        "artifact_name": source.artifact_name,
        "artifact_digest": source.artifact_digest,
        "artifact_size_in_bytes": source.artifact_size_in_bytes,
        "checks": checks,
    }


def _load_mapping(path: Path, *, label: str) -> Mapping[str, Any]:
    value = load_json_strict(path)
    if not isinstance(value, Mapping):
        raise ModelEvidenceImportError(f"{label} is not an object")
    return value


def validate_model_artifact(
    stage: str | Path,
    *,
    source: ModelEvidenceSource,
    root: str | Path,
) -> dict[str, Any]:
    stage_path = Path(stage).resolve(strict=True)
    root_path = Path(root).resolve(strict=True)
    scenario_path = (root_path / source.scenario_path).resolve(strict=True)
    if not scenario_path.is_relative_to(root_path):
        raise ModelEvidenceImportError("scenario_path escapes repository")
    if _sha256(scenario_path) != source.scenario_sha256:
        raise ModelEvidenceImportError("current scenario hash differs from gate")
    scenario = _load_mapping(scenario_path, label="scenario")
    if scenario.get("scenario_id") != source.scenario_id:
        raise ModelEvidenceImportError("scenario identity differs from gate")
    if scenario.get("benchmark_split") == "hidden_test":
        raise ModelEvidenceImportError("hidden-test artifacts cannot use this importer")
    scenario_variants = tuple(
        str(item.get("id"))
        for item in scenario.get("matched_variants", [])
        if isinstance(item, Mapping)
    )
    if scenario_variants != source.expected_variant_ids:
        raise ModelEvidenceImportError("scenario variants differ from gate")

    condition_reports: list[dict[str, Any]] = []
    seen_run_ids: set[str] = set()
    seen_trajectory_paths: set[str] = set()
    for condition in source.conditions:
        summary_path = (stage_path / condition.summary_path).resolve(strict=True)
        trajectory_root = (stage_path / condition.trajectory_root).resolve(strict=True)
        if not summary_path.is_relative_to(stage_path) or not trajectory_root.is_relative_to(stage_path):
            raise ModelEvidenceImportError("condition path escapes artifact stage")
        summary = _load_mapping(summary_path, label="summary")
        expected_count = len(source.expected_variant_ids)
        if summary.get("completed_runs") != expected_count:
            raise ModelEvidenceImportError("summary completed_runs is incorrect")
        if summary.get("run_errors") != []:
            raise ModelEvidenceImportError("summary contains run_errors")
        control_counts = summary.get("execution_control_counts")
        if not isinstance(control_counts, Mapping) or control_counts.get("false") != expected_count:
            raise ModelEvidenceImportError("summary is not an ordinary condition")
        reports = summary.get("reports")
        if not isinstance(reports, Sequence) or isinstance(reports, str):
            raise ModelEvidenceImportError("summary reports are invalid")
        report_variants = {
            str(report.get("variant"))
            for report in reports
            if isinstance(report, Mapping)
            and report.get("scenario_id") == source.scenario_id
        }
        if report_variants != set(source.expected_variant_ids):
            raise ModelEvidenceImportError("summary reports do not cover exact variants")
        repetition_path = trajectory_root / f"repetition-{condition.repetition:02d}"
        trajectories: list[dict[str, Any]] = []
        component_pass_counts = {component: 0 for component in sorted(_COMPONENTS)}
        pass_count = 0
        failure_type_counts: dict[str, int] = {}
        for variant in source.expected_variant_ids:
            trajectory_path = (repetition_path / f"{variant}.json").resolve(strict=True)
            if not trajectory_path.is_relative_to(stage_path):
                raise ModelEvidenceImportError("trajectory path escapes artifact stage")
            relative = trajectory_path.relative_to(stage_path).as_posix()
            if relative in seen_trajectory_paths:
                raise ModelEvidenceImportError("trajectory path is counted twice")
            seen_trajectory_paths.add(relative)
            trajectory = _load_mapping(trajectory_path, label="trajectory")
            identity_checks = {
                "scenario": trajectory.get("scenario_id") == source.scenario_id,
                "variant": trajectory.get("variant") == variant,
                "model": trajectory.get("model") == condition.model,
                "provider": trajectory.get("provider") == condition.provider,
                "ordinary": trajectory.get("execution_control") is False,
            }
            if not all(identity_checks.values()):
                failures = [name for name, passed in identity_checks.items() if not passed]
                raise ModelEvidenceImportError(
                    f"{relative} identity failed: " + ", ".join(failures)
                )
            run_id = trajectory.get("run_id")
            if not isinstance(run_id, str) or not run_id or run_id in seen_run_ids:
                raise ModelEvidenceImportError("trajectory run_id is invalid or duplicated")
            seen_run_ids.add(run_id)
            evaluation = trajectory.get("evaluation")
            if not isinstance(evaluation, Mapping):
                raise ModelEvidenceImportError("trajectory evaluation is missing")
            components = evaluation.get("components")
            if not isinstance(components, Mapping) or not _COMPONENTS.issubset(components):
                raise ModelEvidenceImportError("trajectory components are incomplete")
            passed = evaluation.get("passed") is True
            pass_count += int(passed)
            for component in component_pass_counts:
                component_pass_counts[component] += int(components.get(component) is True)
            diagnostics = trajectory.get("trajectory_diagnostics")
            primary_error = diagnostics.get("primary_error") if isinstance(diagnostics, Mapping) else None
            if primary_error == "infrastructure_failure":
                raise ModelEvidenceImportError("trajectory contains infrastructure failure")
            if primary_error:
                failure_type_counts[str(primary_error)] = (
                    failure_type_counts.get(str(primary_error), 0) + 1
                )
            trajectories.append(
                {
                    "run_id": run_id,
                    "variant_id": variant,
                    "path": relative,
                    "sha256": _sha256(trajectory_path),
                    "passed": passed,
                    "components": {
                        component: components.get(component) is True
                        for component in sorted(_COMPONENTS)
                    },
                    "primary_error": primary_error,
                }
            )
        matched_success = pass_count == expected_count
        summary_matched = summary.get("matched_group_success_rate")
        if summary_matched not in {0, 0.0, 1, 1.0} or bool(summary_matched) != matched_success:
            raise ModelEvidenceImportError("summary matched-group result is inconsistent")
        condition_reports.append(
            {
                "condition_id": condition.condition_id,
                "model": condition.model,
                "provider": condition.provider,
                "provider_service": condition.provider_service,
                "repetition": condition.repetition,
                "accounting_status": condition.accounting_status,
                "summary": {
                    "path": summary_path.relative_to(stage_path).as_posix(),
                    "sha256": _sha256(summary_path),
                },
                "infrastructure_valid": True,
                "completed_runs": expected_count,
                "task_pass_count": pass_count,
                "task_pass_rate": pass_count / expected_count,
                "matched_group_success": matched_success,
                "component_pass_counts": component_pass_counts,
                "failure_type_counts": dict(sorted(failure_type_counts.items())),
                "trajectories": trajectories,
            }
        )
    return {
        "schema_version": "1.0",
        "evidence_id": source.evidence_id,
        "source_run_id": source.source_run_id,
        "scenario_id": source.scenario_id,
        "scenario": {"path": source.scenario_path, "sha256": source.scenario_sha256},
        "variant_ids": list(source.expected_variant_ids),
        "infrastructure_valid": True,
        "conditions": condition_reports,
    }


def write_json(path: str | Path, value: Any) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )


__all__ = [
    "ModelEvidenceImportError",
    "ModelEvidenceImportGate",
    "ModelEvidenceSource",
    "validate_model_artifact",
    "validate_source_provenance",
    "write_json",
]
