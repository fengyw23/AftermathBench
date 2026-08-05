from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .native_admission import validate_native_scenario
from .native_scenario import load_native_scenario, native_scenario_paths
from .release_manifest import default_release_manifest_path, load_release_manifest
from .schema import repository_root
from .strict_json import load_json_strict


ACCOUNTING_STATUSES = frozenset(
    {
        "ordinary-model-tested",
        "current-formal-model-tested",
        "historical-development",
        "control-only",
    }
)
ORDINARY_STATUSES = frozenset(
    {"ordinary-model-tested", "current-formal-model-tested"}
)
IDENTITY_FIELDS = (
    "scenario_sha256",
    "tool_contract_sha256",
    "evaluator_sha256",
    "formal_input_lock_sha256",
)
COMPONENTS = (
    "goal_completion",
    "repair_completeness",
    "preservation",
    "protocol_safety",
)


class ModelEvidenceRegistryError(ValueError):
    pass


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("ascii")
    return hashlib.sha256(payload).hexdigest()


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ModelEvidenceRegistryError(f"{label} must be an object")
    return value


def _string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ModelEvidenceRegistryError(f"{label} must be a non-empty string")
    return value


def _path(root: Path, value: Any, label: str) -> Path:
    relative = Path(_string(value, label))
    if relative.is_absolute() or ".." in relative.parts:
        raise ModelEvidenceRegistryError(f"{label} must be repository-relative")
    resolved = (root / relative).resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as error:
        raise ModelEvidenceRegistryError(f"{label} escapes repository") from error
    if not resolved.is_file():
        raise ModelEvidenceRegistryError(f"{label} does not exist: {relative}")
    return resolved


def _trajectory_set_sha256(trajectories: list[dict[str, Any]]) -> str:
    return _canonical_sha256(
        sorted(
            (
                {
                    "variant_id": item["variant_id"],
                    "sha256": item["sha256"],
                }
                for item in trajectories
            ),
            key=lambda item: (item["variant_id"], item["sha256"]),
        )
    )


def _components(trajectory: dict[str, Any]) -> dict[str, bool]:
    evaluation = _object(trajectory.get("evaluation"), "trajectory.evaluation")
    raw = _object(evaluation.get("components"), "trajectory.evaluation.components")
    if set(raw) != set(COMPONENTS) or any(
        not isinstance(raw[name], bool) for name in COMPONENTS
    ):
        raise ModelEvidenceRegistryError(
            "trajectory evaluation must contain four boolean components"
        )
    return {name: raw[name] for name in COMPONENTS}


def _load_artifact_condition(
    condition: dict[str, Any], root: Path
) -> dict[str, Any]:
    evidence = _object(condition.get("evidence"), "condition.evidence")
    audit_path = _path(root, evidence.get("audit_path"), "evidence.audit_path")
    audit = _object(load_json_strict(audit_path), "artifact audit")
    condition_id = _string(
        evidence.get("audit_condition_id"), "evidence.audit_condition_id"
    )
    matches = [
        item
        for item in audit.get("conditions", [])
        if isinstance(item, dict) and item.get("condition_id") == condition_id
    ]
    if len(matches) != 1:
        raise ModelEvidenceRegistryError(
            f"artifact audit condition must resolve once: {condition_id}"
        )
    source = matches[0]
    trajectories = [
        {
            "variant_id": _string(item.get("variant_id"), "trajectory.variant_id"),
            "path": _string(item.get("path"), "trajectory.path"),
            "sha256": _string(item.get("sha256"), "trajectory.sha256"),
            "run_id": _string(item.get("run_id"), "trajectory.run_id"),
            "passed": item.get("passed") is True,
            "components": _object(item.get("components"), "trajectory.components"),
            "primary_error": item.get("primary_error"),
            "execution_control": False,
        }
        for item in source.get("trajectories", [])
        if isinstance(item, dict)
    ]
    summary = _object(source.get("summary"), "artifact summary")
    scenario = _object(audit.get("scenario"), "artifact scenario")
    return {
        "scenario_id": audit.get("scenario_id"),
        "scenario_sha256": scenario.get("sha256"),
        "model": source.get("model"),
        "provider": source.get("provider"),
        "provider_service": source.get("provider_service"),
        "repetition": source.get("repetition"),
        "infrastructure_valid": source.get("infrastructure_valid") is True,
        "summary_sha256": summary.get("sha256"),
        "trajectories": trajectories,
        "source_run_id": audit.get("source_run_id"),
    }


def _load_local_condition(
    condition: dict[str, Any], root: Path
) -> dict[str, Any]:
    evidence = _object(condition.get("evidence"), "condition.evidence")
    summary_path = _path(
        root, evidence.get("summary_path"), "evidence.summary_path"
    )
    summary = _object(load_json_strict(summary_path), "summary")
    trajectory_root = Path(
        _string(evidence.get("trajectory_root"), "evidence.trajectory_root")
    )
    if trajectory_root.is_absolute() or ".." in trajectory_root.parts:
        raise ModelEvidenceRegistryError(
            "evidence.trajectory_root must be repository-relative"
        )
    trajectories: list[dict[str, Any]] = []
    for report in summary.get("reports", []):
        report = _object(report, "summary report")
        variant = _string(
            report.get("variant", report.get("variant_id")), "summary variant"
        )
        if evidence.get("kind") == "formal-control":
            declared = report.get("path")
            if not isinstance(declared, str):
                raise ModelEvidenceRegistryError(
                    "formal control summary report must declare a path"
                )
            declared_path = Path(declared)
            if declared_path.is_absolute():
                try:
                    declared_path = declared_path.relative_to(root)
                except ValueError as error:
                    raise ModelEvidenceRegistryError(
                        "formal control trajectory path escapes repository"
                    ) from error
            path = _path(root, str(declared_path).replace("\\", "/"), "trajectory path")
        else:
            path = _path(
                root,
                str(trajectory_root / f"{variant}.json").replace("\\", "/"),
                "trajectory path",
            )
        trajectory = _object(load_json_strict(path), "trajectory")
        trajectories.append(
            {
                "variant_id": variant,
                "path": str(path.relative_to(root)).replace("\\", "/"),
                "sha256": _sha256(path),
                "run_id": _string(trajectory.get("run_id"), "trajectory.run_id"),
                "passed": _object(
                    trajectory.get("evaluation"), "trajectory.evaluation"
                ).get("passed")
                is True,
                "components": _components(trajectory),
                "primary_error": _object(
                    trajectory.get("trajectory_diagnostics", {}),
                    "trajectory.trajectory_diagnostics",
                ).get("primary_error"),
                "execution_control": trajectory.get("execution_control") is True,
            }
        )
    first = trajectories and load_json_strict(root / trajectories[0]["path"])
    first = _object(first, "first trajectory")
    return {
        "scenario_id": first.get("scenario_id"),
        "scenario_sha256": None,
        "model": first.get("model"),
        "provider": first.get("provider"),
        "provider_service": condition.get("model", {}).get("provider_service"),
        "repetition": condition.get("model", {}).get("repetition"),
        "infrastructure_valid": not summary.get("run_errors"),
        "summary_sha256": _sha256(summary_path),
        "trajectories": trajectories,
        "source_run_id": condition.get("source", {}).get("run_id"),
    }


def _current_formal_identities(root: Path) -> dict[str, dict[str, Any]]:
    manifest = load_release_manifest(default_release_manifest_path())
    identities: dict[str, dict[str, Any]] = {}
    for binding in manifest["scenario_bindings"]:
        evidence = binding["formal_evidence"]
        lock_path = Path(evidence["tool_contract"]["path"]).parents[2] / (
            "formal-input-lock.json"
        )
        identities[str(binding["scenario_id"])] = {
            "scenario_sha256": binding["scenario_sha256"],
            "tool_contract_sha256": evidence["tool_contract"]["sha256"],
            "evaluator_sha256": evidence["evaluator"]["sha256"],
            "formal_input_lock_sha256": _sha256(root / lock_path),
        }
    return identities


def _active_hard_scenarios() -> set[str]:
    result: set[str] = set()
    for path in native_scenario_paths():
        scenario = load_native_scenario(path)
        report = validate_native_scenario(scenario)
        if report.passed and report.admitted_tier == "hard":
            result.add(scenario.scenario_id)
    return result


def validate_model_evidence_registry(
    raw: dict[str, Any], *, root: Path | None = None
) -> dict[str, Any]:
    root = (root or repository_root()).resolve()
    if raw.get("schema_version") != "1.0":
        raise ModelEvidenceRegistryError("schema_version must be 1.0")
    conditions = raw.get("conditions")
    if not isinstance(conditions, list) or not conditions:
        raise ModelEvidenceRegistryError("conditions must be a non-empty list")
    active_hard = _active_hard_scenarios()
    formal_identities = _current_formal_identities(root)
    seen_condition_ids: set[str] = set()
    seen_run_conditions: set[tuple[Any, str]] = set()
    rows: list[dict[str, Any]] = []

    for index, value in enumerate(conditions):
        condition = _object(value, f"condition {index}")
        condition_id = _string(condition.get("condition_id"), "condition_id")
        if condition_id in seen_condition_ids:
            raise ModelEvidenceRegistryError(f"duplicate condition_id: {condition_id}")
        seen_condition_ids.add(condition_id)
        status = condition.get("accounting_status")
        if status not in ACCOUNTING_STATUSES:
            raise ModelEvidenceRegistryError(
                f"condition {condition_id} has invalid accounting_status"
            )
        kind = _object(condition.get("evidence"), "condition.evidence").get("kind")
        if kind == "artifact-audit":
            observed = _load_artifact_condition(condition, root)
        elif kind in {"local-summary", "formal-control"}:
            observed = _load_local_condition(condition, root)
        else:
            raise ModelEvidenceRegistryError(
                f"condition {condition_id} has invalid evidence kind"
            )

        scenario = _object(condition.get("scenario"), "condition.scenario")
        scenario_id = _string(scenario.get("scenario_id"), "scenario.scenario_id")
        if observed["scenario_id"] != scenario_id:
            raise ModelEvidenceRegistryError(
                f"condition {condition_id} scenario identity differs"
            )
        declared_path = scenario.get("path")
        scenario_sha256 = None
        if declared_path is not None:
            scenario_path = _path(root, declared_path, "scenario.path")
            scenario_sha256 = _sha256(scenario_path)
        identity = _object(condition.get("identity"), "condition.identity")
        if set(identity) != set(IDENTITY_FIELDS):
            raise ModelEvidenceRegistryError(
                f"condition {condition_id} identity fields differ"
            )
        if identity["scenario_sha256"] != scenario_sha256:
            raise ModelEvidenceRegistryError(
                f"condition {condition_id} scenario hash differs"
            )
        if observed["scenario_sha256"] not in {None, scenario_sha256}:
            raise ModelEvidenceRegistryError(
                f"condition {condition_id} artifact scenario hash differs"
            )
        if condition.get("identity_sha256") != _canonical_sha256(identity):
            raise ModelEvidenceRegistryError(
                f"condition {condition_id} identity hash differs"
            )

        model = _object(condition.get("model"), "condition.model")
        for field in ("name", "provider", "provider_service", "repetition"):
            expected = model.get(field)
            observed_field = {
                "name": "model",
                "provider": "provider",
                "provider_service": "provider_service",
                "repetition": "repetition",
            }[field]
            actual = observed.get(observed_field)
            if actual is not None and expected != actual:
                raise ModelEvidenceRegistryError(
                    f"condition {condition_id} model {field} differs"
                )

        source = _object(condition.get("source"), "condition.source")
        run_key = (
            source.get("run_id")
            if source.get("run_id") is not None
            else condition_id,
            str(source.get("condition", condition_id)),
        )
        if run_key in seen_run_conditions:
            raise ModelEvidenceRegistryError(
                f"duplicate source run/condition: {run_key}"
            )
        seen_run_conditions.add(run_key)
        if observed["source_run_id"] not in {None, source.get("run_id")}:
            raise ModelEvidenceRegistryError(
                f"condition {condition_id} source run differs"
            )
        if observed["summary_sha256"] != condition.get("summary_sha256"):
            raise ModelEvidenceRegistryError(
                f"condition {condition_id} summary hash differs"
            )
        trajectories = observed["trajectories"]
        variants = [_string(item, "variant_id") for item in scenario.get("variant_ids", [])]
        observed_variants = [item["variant_id"] for item in trajectories]
        if len(variants) != len(set(variants)) or set(variants) != set(observed_variants):
            raise ModelEvidenceRegistryError(
                f"condition {condition_id} variant set differs"
            )
        if condition.get("trajectory_set_sha256") != _trajectory_set_sha256(
            trajectories
        ):
            raise ModelEvidenceRegistryError(
                f"condition {condition_id} trajectory set hash differs"
            )
        execution_controls = {item["execution_control"] for item in trajectories}
        if status in ORDINARY_STATUSES and execution_controls != {False}:
            raise ModelEvidenceRegistryError(
                f"condition {condition_id}: control cannot count as ordinary"
            )
        if status == "control-only" and execution_controls != {True}:
            raise ModelEvidenceRegistryError(
                f"condition {condition_id}: control-only must be explicit scope"
            )
        if not observed["infrastructure_valid"]:
            raise ModelEvidenceRegistryError(
                f"condition {condition_id} has infrastructure errors"
            )

        score = _object(condition.get("score"), "condition.score")
        pass_count = sum(item["passed"] for item in trajectories)
        component_counts = {
            name: sum(item["components"][name] is True for item in trajectories)
            for name in COMPONENTS
        }
        errors: dict[str, int] = {}
        for item in trajectories:
            error = item["primary_error"]
            if error:
                errors[str(error)] = errors.get(str(error), 0) + 1
        recomputed_score = {
            "completed_runs": len(trajectories),
            "task_pass_count": pass_count,
            "component_pass_counts": component_counts,
            "matched_group_success": pass_count == len(trajectories),
            "error_attribution": errors,
        }
        if score != recomputed_score:
            raise ModelEvidenceRegistryError(
                f"condition {condition_id} deterministic score differs"
            )

        membership = condition.get("membership")
        if membership == "active-hard" and scenario_id not in active_hard:
            raise ModelEvidenceRegistryError(
                f"condition {condition_id} is not an active hard scenario"
            )
        if membership != "active-hard" and scenario_id in active_hard and status in ORDINARY_STATUSES:
            raise ModelEvidenceRegistryError(
                f"condition {condition_id} understates active hard membership"
            )
        current_identity = formal_identities.get(scenario_id)
        exact_formal = current_identity is not None and identity == current_identity
        if status == "current-formal-model-tested" and not exact_formal:
            raise ModelEvidenceRegistryError(
                f"condition {condition_id} does not match current formal identity"
            )
        rows.append(
            {
                "condition_id": condition_id,
                "accounting_status": status,
                "membership": membership,
                "scenario_id": scenario_id,
                "variant_ids": variants,
                "model": model,
                "source": source,
                "identity_sha256": condition["identity_sha256"],
                "current_formal_identity_match": exact_formal,
                "score": score,
            }
        )

    quarantined = raw.get("quarantined_imports", [])
    if not isinstance(quarantined, list):
        raise ModelEvidenceRegistryError("quarantined_imports must be a list")
    for item in quarantined:
        item = _object(item, "quarantined import")
        if item.get("counted_as_model_evidence") is not False:
            raise ModelEvidenceRegistryError(
                "quarantined imports must not count as model evidence"
            )

    def states_for(*, statuses: set[str], memberships: set[str] | None = None) -> set[tuple[str, str]]:
        return {
            (row["scenario_id"], variant)
            for row in rows
            if row["accounting_status"] in statuses
            and (memberships is None or row["membership"] in memberships)
            for variant in row["variant_ids"]
        }

    ordinary = states_for(statuses=set(ORDINARY_STATUSES))
    active_ordinary = states_for(
        statuses=set(ORDINARY_STATUSES), memberships={"active-hard"}
    )
    archived_ordinary = states_for(
        statuses=set(ORDINARY_STATUSES),
        memberships={"archived-hard-development"},
    )
    historical = states_for(statuses={"historical-development"})
    current_formal = states_for(statuses={"current-formal-model-tested"})
    controls = states_for(statuses={"control-only"})
    return {
        "passed": True,
        "schema_version": "1.0",
        "condition_count": len(rows),
        "counts": {
            "ordinary_model_tested_unique_state_count": len(ordinary),
            "active_hard_ordinary_unique_state_count": len(active_ordinary),
            "archived_hard_development_ordinary_unique_state_count": len(
                archived_ordinary
            ),
            "historical_development_unique_state_count": len(historical),
            "current_formal_model_tested_unique_state_count": len(current_formal),
            "control_only_unique_state_count": len(controls),
            "quarantined_import_count": len(quarantined),
        },
        "conditions": rows,
        "quarantined_imports": quarantined,
    }


def load_model_evidence_registry(
    path: str | Path | None = None, *, root: Path | None = None
) -> dict[str, Any]:
    root = (root or repository_root()).resolve()
    registry_path = Path(path) if path is not None else root / "data" / "model_evidence_registry.json"
    return validate_model_evidence_registry(
        _object(load_json_strict(registry_path), "model evidence registry"),
        root=root,
    )


__all__ = [
    "ACCOUNTING_STATUSES",
    "ModelEvidenceRegistryError",
    "load_model_evidence_registry",
    "validate_model_evidence_registry",
]
