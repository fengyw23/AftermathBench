from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .schema import repository_root


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


def runtime_manifest_paths() -> tuple[Path, ...]:
    return tuple(
        sorted((repository_root() / "data" / "runtimes").glob("*/runtime.json"))
    )


def load_runtime_manifest(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


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
    evidence_path = (
        repository_root() / str(evidence_manifest)
        if evidence_manifest
        else None
    )
    recovery_manifest = admission_evidence.get(
        "recovery_control_evidence_manifest"
    )
    recovery_evidence_path = (
        repository_root() / str(recovery_manifest)
        if recovery_manifest
        else None
    )
    execution_checks["admission_evidence_recorded"] = bool(
        admission_evidence.get("validated_at")
        and len(str(admission_evidence.get("head_sha", ""))) == 40
        and str(admission_evidence.get("workflow_run", "")).startswith(
            "https://github.com/"
        )
        and evidence_path is not None
        and evidence_path.is_file()
        and (
            recovery_evidence_path is None
            or recovery_evidence_path.is_file()
        )
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
        runtime_id=str(raw["runtime_id"]),
        source_audit_passed=source_passed,
        execution_admitted=execution_admitted,
        source_checks=source_checks,
        execution_checks=execution_checks,
        failures=failures,
    )
