from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .path_safety import safe_relative_path
from .schema import repository_root
from .strict_json import load_json_strict

SOURCE_REQUIREMENTS = (
    "server_implementation_source",
    "schema_migrations_source",
    "transaction_logic_source",
    "source_build_recipe",
    "redistributable_inputs",
    "fault_injection_without_business_logic_reimplementation",
)

EXECUTION_REQUIREMENTS = (
    "container_images_digest_pinned",
    "built_from_source",
    "deterministic_reset_verified",
    "fault_variants_replayed",
    "terminal_checks_replayed",
)


@dataclass(frozen=True)
class RuntimeAdmissionReport:
    runtime_id: str
    source_audit_passed: bool
    execution_admitted: bool
    source_checks: dict[str, bool]
    execution_checks: dict[str, bool]
    failures: tuple[str, ...]


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def runtime_manifest_paths() -> tuple[Path, ...]:
    return tuple(
        sorted((repository_root() / "data" / "runtimes").glob("*/runtime.json"))
    )


def load_runtime_manifest(path: str | Path) -> dict[str, Any]:
    return load_json_strict(path)


def _report_passed(
    report: dict[str, Any],
    fields: tuple[str, ...],
) -> bool:
    return bool(fields) and all(
        field in report and report[field] is True for field in fields
    )


_COMBINED_PHASE_FIELDS = {
    "boundary": (
        "boundary_file",
        "boundary_sha256",
        "boundary_validation_passed",
    ),
    "reference": (
        "reference_file",
        "reference_sha256",
        "reference_recovery_passed",
    ),
}
_STANDALONE_PHASE_FIELDS = {
    "boundary": ("file", "sha256", "boundary_validation_passed"),
    "reference": ("file", "sha256", "passed"),
}


def _manifest_phase_contract(
    manifest: dict[str, Any],
    phase: str,
) -> tuple[str, str, str, str] | None:
    if phase not in _COMBINED_PHASE_FIELDS:
        return None
    contract = manifest.get("evidence_contract")
    if not isinstance(contract, dict):
        return None
    scenario_id = contract.get("scenario_id")
    phases = contract.get("phases")
    if (
        contract.get("schema_version") != "1.0"
        or not isinstance(scenario_id, str)
        or not scenario_id
        or not isinstance(phases, dict)
        or phase not in phases
    ):
        return None
    declaration = phases[phase]
    if not isinstance(declaration, dict):
        return None
    fields = (
        declaration.get("file_field"),
        declaration.get("sha256_field"),
        declaration.get("pass_field"),
    )
    allowed = [_COMBINED_PHASE_FIELDS[phase]]
    if set(phases) == {phase}:
        allowed.append(_STANDALONE_PHASE_FIELDS[phase])
    if not any(fields == candidate for candidate in allowed):
        return None
    return scenario_id, *fields


def _payload_contract_matches(
    payload: dict[str, Any],
    *,
    scenario_id: str,
    variant_id: str,
    phase: str,
) -> bool:
    if (
        payload.get("scenario_id") != scenario_id
        or payload.get("variant") != variant_id
    ):
        return False
    if phase == "boundary":
        legacy_contract = (
            payload.get("passed") is True
            and isinstance(payload.get("surface_result"), str)
            and bool(payload["surface_result"])
            and isinstance(payload.get("checks"), dict)
            and bool(payload["checks"])
        )
        validation = payload.get("boundary_validation")
        visible_failure = payload.get("visible_failure")
        formal_native_contract = (
            payload.get("phase") == "boundary"
            and isinstance(payload.get("surface_result"), str)
            and bool(payload["surface_result"])
            and isinstance(visible_failure, dict)
            and visible_failure.get("ok") is False
            and isinstance(payload.get("failure_boundary_evidence"), dict)
            and bool(payload["failure_boundary_evidence"])
            and isinstance(validation, dict)
            and validation.get("passed") is True
            and isinstance(validation.get("checks"), dict)
            and bool(validation["checks"])
        )
        return legacy_contract or formal_native_contract
    if phase == "reference":
        evaluation = payload.get("evaluation")
        return (
            isinstance(payload.get("control"), str)
            and bool(payload["control"])
            and isinstance(payload.get("reference_trace"), list)
            and bool(payload["reference_trace"])
            and isinstance(evaluation, dict)
            and evaluation.get("passed") is True
        )
    return False


def _evidence_manifest_consistent(
    path: Path | None,
    *,
    runtime_id: str,
    head_sha: str | None,
    workflow_run: str | None,
    phase: str,
) -> bool:
    if path is None or not path.is_file():
        return False
    try:
        manifest = load_json_strict(path)
    except (OSError, ValueError, json.JSONDecodeError):
        return False
    if not isinstance(manifest, dict):
        return False
    reports = manifest.get("reports", ())
    if not isinstance(reports, list) or len(reports) < 4:
        return False
    variants = [
        str(report.get("variant", ""))
        for report in reports
        if isinstance(report, dict)
    ]
    if (
        len(variants) != len(reports)
        or not all(variants)
        or len(variants) != len(set(variants))
        or not all(isinstance(report, dict) for report in reports)
    ):
        return False

    selected_contract = _manifest_phase_contract(manifest, phase)
    if selected_contract is None:
        return False
    scenario_id, file_field, sha256_field, pass_field = selected_contract

    phase_paths: dict[str, tuple[str, ...]] = {}
    evidence_contract = manifest["evidence_contract"]
    for declared_phase in evidence_contract["phases"]:
        phase_contract = _manifest_phase_contract(manifest, declared_phase)
        if phase_contract is None:
            return False
        _, declared_file_field, _, _ = phase_contract
        paths = tuple(
            str(report.get(declared_file_field, ""))
            for report in reports
        )
        if (
            not all(paths)
            or len(paths) != len(set(paths))
        ):
            return False
        phase_paths[declared_phase] = paths
    all_paths = tuple(
        relative
        for paths in phase_paths.values()
        for relative in paths
    )
    if len(all_paths) != len(set(all_paths)):
        return False

    def report_file_is_verified(report: dict[str, Any]) -> bool:
        passed = report.get(pass_field) is True
        relative = report.get(file_field)
        expected_sha = report.get(sha256_field)
        explicit_phase_pass_field = _COMBINED_PHASE_FIELDS[phase][2]
        if (
            explicit_phase_pass_field in report
            and report.get(explicit_phase_pass_field) is not True
        ):
            return False
        if (
            not passed
            or not isinstance(relative, str)
            or not relative
            or not isinstance(expected_sha, str)
            or len(expected_sha) != 64
        ):
            return False
        try:
            evidence_file = safe_relative_path(
                path.parent,
                relative,
                must_exist=True,
                require_file=True,
            )
        except (OSError, ValueError):
            return False
        if file_sha256(evidence_file) != expected_sha:
            return False
        try:
            payload = load_json_strict(evidence_file)
        except (OSError, ValueError, json.JSONDecodeError):
            return False
        if not isinstance(payload, dict) or not _payload_contract_matches(
            payload,
            scenario_id=scenario_id,
            variant_id=str(report.get("variant", "")),
            phase=phase,
        ):
            return False
        declared_bytes = report.get("bytes")
        if declared_bytes is None:
            return True
        try:
            return evidence_file.stat().st_size == int(declared_bytes)
        except (TypeError, ValueError):
            return False

    observed_head_sha = str(manifest.get("head_sha", ""))
    observed_workflow_run = str(manifest.get("workflow_run_url", ""))
    return bool(
        manifest.get("runtime_id") == runtime_id
        and len(observed_head_sha) == 40
        and (head_sha is None or observed_head_sha == head_sha)
        and observed_workflow_run.startswith("https://github.com/")
        and (
            workflow_run is None
            or observed_workflow_run == workflow_run
        )
        and manifest.get("credentials_present") is False
        and all(report_file_is_verified(report) for report in reports)
    )


def validate_runtime_manifest(raw: dict[str, Any]) -> RuntimeAdmissionReport:
    capabilities = raw.get("open_runtime_evidence", {})
    source_checks = {
        name: bool(capabilities.get(name)) for name in SOURCE_REQUIREMENTS
    }
    source_checks["pinned_components"] = bool(raw.get("upstream_components")) and all(
        component.get("repository")
        and component.get("revision")
        and component.get("license")
        for component in raw.get("upstream_components", [])
    )
    source_checks["documented_fault_seam"] = any(
        seam.get("source_path")
        and seam.get("symbol")
        and len(seam.get("observable_outcomes", [])) >= 2
        for seam in raw.get("fault_seams", [])
    )

    execution = raw.get("execution_validation", {})
    execution_checks = {
        name: bool(execution.get(name)) for name in EXECUTION_REQUIREMENTS
    }
    admission_evidence = raw.get("admission_evidence", {})
    evidence_manifest = admission_evidence.get("evidence_manifest")
    try:
        evidence_path = (
            safe_relative_path(
                repository_root(),
                str(evidence_manifest),
                required_prefix="data",
            )
            if evidence_manifest
            else None
        )
    except ValueError:
        evidence_path = None
    recovery_manifest = admission_evidence.get(
        "recovery_control_evidence_manifest"
    )
    try:
        recovery_evidence_path = (
            safe_relative_path(
                repository_root(),
                str(recovery_manifest),
                required_prefix="data",
            )
            if recovery_manifest
            else None
        )
    except ValueError:
        recovery_evidence_path = None
    runtime_id = str(raw["runtime_id"])
    head_sha = str(admission_evidence.get("head_sha", ""))
    workflow_run = str(admission_evidence.get("workflow_run", ""))
    boundary_manifest_valid = _evidence_manifest_consistent(
        evidence_path,
        runtime_id=runtime_id,
        head_sha=head_sha,
        workflow_run=workflow_run,
        phase="boundary",
    )
    recovery_evidence_source = recovery_evidence_path or evidence_path
    recovery_manifest_valid = _evidence_manifest_consistent(
        recovery_evidence_source,
        runtime_id=runtime_id,
        head_sha=None,
        workflow_run=None,
        phase="reference",
    )
    execution_checks["boundary_evidence_files_verified"] = (
        boundary_manifest_valid
    )
    execution_checks["reference_evidence_files_verified"] = (
        recovery_manifest_valid
    )
    execution_checks["admission_evidence_recorded"] = bool(
        admission_evidence.get("validated_at")
        and len(head_sha) == 40
        and workflow_run.startswith(
            "https://github.com/"
        )
        and evidence_path is not None
        and evidence_path.is_file()
        and boundary_manifest_valid
        and recovery_manifest_valid
    )
    source_passed = all(source_checks.values())
    execution_admitted = source_passed and all(execution_checks.values())

    declared_source = raw.get("declared_status", {}).get("source_audit")
    declared_execution = raw.get("declared_status", {}).get("execution")
    declaration_checks = {
        "source_status_truthful": declared_source
        == ("passed" if source_passed else "rejected"),
        "execution_status_truthful": declared_execution
        == ("admitted" if execution_admitted else "pending_or_rejected"),
    }
    failures = tuple(
        name
        for name, passed in {
            **source_checks,
            **execution_checks,
            **declaration_checks,
        }.items()
        if not passed
    )
    return RuntimeAdmissionReport(
        runtime_id=runtime_id,
        source_audit_passed=source_passed,
        execution_admitted=execution_admitted,
        source_checks=source_checks,
        execution_checks=execution_checks,
        failures=failures,
    )
