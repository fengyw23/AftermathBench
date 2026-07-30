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
    ):
        return False

    def report_file_is_verified(report: dict[str, Any]) -> bool:
        if phase == "boundary":
            passed = report.get("boundary_validation_passed") is True
            relative = report.get("boundary_file", report.get("file"))
            expected_sha = report.get(
                "boundary_sha256",
                report.get("sha256"),
            )
        elif phase == "reference":
            passed = (
                report.get("reference_recovery_passed") is True
                or report.get("passed") is True
            )
            relative = report.get("reference_file", report.get("file"))
            expected_sha = report.get(
                "reference_sha256",
                report.get("sha256"),
            )
        else:
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
