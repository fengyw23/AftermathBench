from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .forgejo_publication_state_evidence import canonical_state_fingerprint
from .strict_json import load_json_strict


class ForgejoMigrationStateEvidenceError(ValueError):
    """Raised when migration evidence is not bound to native state."""


_BUNDLE_FIELDS = frozenset(
    {
        "schema_version",
        "capture_mode",
        "runner_enabled",
        "forgejo_sha256",
        "deployment_target_sha256",
    }
)
_CAPTURE_MODE = "simultaneous_actions_and_deployment_quiescence"


def file_sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def validate_migration_bundle_manifest(
    manifest_path: str | Path,
    *,
    forgejo_archive_path: str | Path,
    deployment_target_archive_path: str | Path,
) -> dict[str, Any]:
    manifest_file = Path(manifest_path).resolve()
    forgejo_archive = Path(forgejo_archive_path).resolve()
    deployment_archive = Path(deployment_target_archive_path).resolve()
    try:
        manifest = load_json_strict(manifest_file)
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as error:
        raise ForgejoMigrationStateEvidenceError(
            "migration bundle manifest is not strict readable JSON"
        ) from error
    if (
        not isinstance(manifest, dict)
        or set(manifest) != _BUNDLE_FIELDS
        or manifest.get("schema_version") != "1.0"
        or manifest.get("capture_mode") != _CAPTURE_MODE
        or type(manifest.get("runner_enabled")) is not bool
        or not forgejo_archive.is_file()
        or not deployment_archive.is_file()
        or manifest.get("forgejo_sha256") != file_sha256(forgejo_archive)
        or manifest.get("deployment_target_sha256")
        != file_sha256(deployment_archive)
    ):
        raise ForgejoMigrationStateEvidenceError(
            "migration bundle manifest does not bind the native archives"
        )
    return manifest


def _validate_state(state: Any) -> dict[str, Any]:
    required = {
        "deployment_state",
        "releases",
        "issues",
        "milestone",
        "comments",
        "action_runs",
        "action_jobs",
    }
    if not isinstance(state, dict) or not required.issubset(state):
        raise ForgejoMigrationStateEvidenceError(
            "migration capture omits mutable evaluator state"
        )
    if not isinstance(state.get("deployment_state"), dict):
        raise ForgejoMigrationStateEvidenceError(
            "migration deployment state is not an object"
        )
    for field in (
        "releases",
        "issues",
        "comments",
        "action_runs",
        "action_jobs",
    ):
        if not isinstance(state.get(field), list):
            raise ForgejoMigrationStateEvidenceError(
                f"migration state field is not a list: {field}"
            )
    if not isinstance(state.get("milestone"), dict):
        raise ForgejoMigrationStateEvidenceError(
            "migration milestone state is not an object"
        )
    return state


def _failure_report_matches_state(
    failure_report: dict[str, Any],
    state: dict[str, Any],
) -> bool:
    reported_run = failure_report.get("action_run")
    runs = state["action_runs"]
    if reported_run is None:
        run_matches = runs == []
    elif isinstance(reported_run, dict):
        run_id = reported_run.get("id")
        run_matches = any(
            isinstance(run, dict)
            and run.get("id") == run_id
            and run == reported_run
            for run in runs
        )
    else:
        run_matches = False
    return (
        run_matches
        and failure_report.get("action_jobs") == state["action_jobs"]
        and failure_report.get("deployment_state")
        == state["deployment_state"]
    )


def build_forgejo_migration_state_evidence(
    *,
    scenario_id: str,
    instance_id: str,
    instance_spec_sha256: str,
    variant_id: str,
    phase: str,
    prefix_path: str | Path,
    bundle_manifest_path: str | Path,
    forgejo_archive_path: str | Path,
    deployment_target_archive_path: str | Path,
    state: dict[str, Any],
    surface_result: str | None = None,
    failure_report_path: str | Path | None = None,
    reset_evidence_path: str | Path | None = None,
) -> dict[str, Any]:
    if phase not in {"reset", "boundary"}:
        raise ForgejoMigrationStateEvidenceError(
            "migration evidence phase must be reset or boundary"
        )
    if not all(
        (scenario_id, instance_id, instance_spec_sha256, variant_id)
    ):
        raise ForgejoMigrationStateEvidenceError(
            "migration evidence identity fields must be non-empty"
        )
    prefix_file = Path(prefix_path).resolve()
    manifest_file = Path(bundle_manifest_path).resolve()
    forgejo_archive = Path(forgejo_archive_path).resolve()
    deployment_archive = Path(deployment_target_archive_path).resolve()
    if not prefix_file.is_file():
        raise ForgejoMigrationStateEvidenceError(
            "migration prefix file is missing"
        )
    validated_state = _validate_state(state)
    bundle = validate_migration_bundle_manifest(
        manifest_file,
        forgejo_archive_path=forgejo_archive,
        deployment_target_archive_path=deployment_archive,
    )

    failure_report: dict[str, Any] | None = None
    failure_file: Path | None = None
    reset_file: Path | None = None
    if phase == "reset":
        if failure_report_path is not None or reset_evidence_path is not None:
            raise ForgejoMigrationStateEvidenceError(
                "reset capture cannot bind failure or reset evidence"
            )
    else:
        if failure_report_path is None or reset_evidence_path is None:
            raise ForgejoMigrationStateEvidenceError(
                "boundary capture requires failure and reset evidence"
            )
        failure_file = Path(failure_report_path).resolve()
        reset_file = Path(reset_evidence_path).resolve()
        try:
            failure_report = load_json_strict(failure_file)
            reset_evidence = load_json_strict(reset_file)
        except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as error:
            raise ForgejoMigrationStateEvidenceError(
                "boundary sources must be strict readable JSON"
            ) from error
        if (
            not isinstance(failure_report, dict)
            or failure_report.get("schema_version") != "1.0"
            or failure_report.get("scenario_id") != scenario_id
            or failure_report.get("instance_spec_sha256")
            != instance_spec_sha256
            or failure_report.get("variant") != variant_id
            or failure_report.get("passed") is not True
            or not _failure_report_matches_state(
                failure_report,
                validated_state,
            )
        ):
            raise ForgejoMigrationStateEvidenceError(
                "failure report does not prove the captured migration state"
            )
        if (
            not isinstance(reset_evidence, dict)
            or reset_evidence.get("artifact_type")
            != "forgejo_migration_state_evidence"
            or reset_evidence.get("scenario_id") != scenario_id
            or reset_evidence.get("instance_id") != instance_id
            or reset_evidence.get("variant_id") != variant_id
            or reset_evidence.get("phase") != "reset"
            or reset_evidence.get("reset_verified") is not True
        ):
            raise ForgejoMigrationStateEvidenceError(
                "boundary reset evidence is not the matching verified reset"
            )

    payload: dict[str, Any] = {
        "schema_version": "1.0",
        "artifact_type": "forgejo_migration_state_evidence",
        "scenario_id": scenario_id,
        "instance_id": instance_id,
        "instance_spec_sha256": instance_spec_sha256,
        "variant_id": variant_id,
        "phase": phase,
        "prefix_file_sha256": file_sha256(prefix_file),
        "bundle_manifest_file_sha256": file_sha256(manifest_file),
        "bundle": bundle,
        "state_fingerprint": canonical_state_fingerprint(validated_state),
        "state": validated_state,
    }
    if phase == "reset":
        payload["reset_verified"] = True
    else:
        assert failure_report is not None
        assert failure_file is not None
        assert reset_file is not None
        visible_failure = failure_report.get("visible_failure")
        if not isinstance(visible_failure, dict):
            raise ForgejoMigrationStateEvidenceError(
                "failure report omits the model-visible failure"
            )
        payload.update(
            {
                "reset_evidence_file_sha256": file_sha256(reset_file),
                "failure_report_file_sha256": file_sha256(failure_file),
                "surface_result": (
                    surface_result
                    if surface_result is not None
                    else failure_report.get("surface_result")
                ),
                "visible_failure": visible_failure,
                "boundary_validation_passed": True,
            }
        )
    return payload


def validate_forgejo_migration_boundary_replay(
    boundary: dict[str, Any],
    replay: dict[str, Any],
) -> dict[str, Any]:
    for label, payload in (("boundary", boundary), ("replay", replay)):
        if (
            not isinstance(payload, dict)
            or payload.get("schema_version") != "1.0"
            or payload.get("artifact_type")
            != "forgejo_migration_state_evidence"
            or payload.get("phase") != "boundary"
            or payload.get("boundary_validation_passed") is not True
            or not isinstance(payload.get("state"), dict)
            or payload.get("state_fingerprint")
            != canonical_state_fingerprint(payload["state"])
        ):
            raise ForgejoMigrationStateEvidenceError(
                f"{label} is not a validated migration boundary capture"
            )
    if boundary != replay:
        raise ForgejoMigrationStateEvidenceError(
            "migration boundary replay is not byte-equivalent JSON state"
        )
    return {
        "passed": True,
        "scenario_id": boundary["scenario_id"],
        "instance_id": boundary["instance_id"],
        "variant_id": boundary["variant_id"],
        "state_fingerprint": boundary["state_fingerprint"],
    }


__all__ = [
    "ForgejoMigrationStateEvidenceError",
    "build_forgejo_migration_state_evidence",
    "file_sha256",
    "validate_forgejo_migration_boundary_replay",
    "validate_migration_bundle_manifest",
]
