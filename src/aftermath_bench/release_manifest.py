from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .benchmark_matrix import (
    benchmark_family_index,
    benchmark_slots,
    load_benchmark_matrix,
    validate_benchmark_matrix,
)
from .hidden_test_eligibility import verify_hidden_test_eligibility
from .native_admission import validate_native_scenario
from .native_freeze import verify_frozen_bundle
from .native_scenario import (
    load_native_scenario,
    validate_native_scenario_document,
)
from .path_safety import safe_relative_path
from .runtime_gate import (
    load_runtime_manifest,
    runtime_manifest_paths,
    validate_runtime_manifest,
)
from .schema import repository_root
from .strict_json import load_json_strict

FORMAL_EVIDENCE_ROLES = frozenset(
    {
        "boundary_bundle",
        "reference_bundle",
        "tool_contract",
        "evaluator",
        "reset_evidence",
        "raw_run_archive",
        "execution_control",
    }
)
FORMAL_EVIDENCE_DEPENDENCIES = {
    "tool_contract": frozenset(),
    "evaluator": frozenset({"tool_contract"}),
    "reset_evidence": frozenset({"tool_contract"}),
    "boundary_bundle": frozenset({"tool_contract", "reset_evidence"}),
    "reference_bundle": frozenset(
        {"boundary_bundle", "tool_contract", "evaluator", "reset_evidence"}
    ),
    "raw_run_archive": frozenset(
        {"boundary_bundle", "tool_contract", "evaluator", "reset_evidence"}
    ),
    "execution_control": frozenset(
        {"raw_run_archive", "tool_contract", "evaluator"}
    ),
}
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_GIT_COMMIT = re.compile(r"^[0-9a-f]{40}$")
MIN_EXECUTION_CONTROL_PASS_RATE = 0.8


@dataclass(frozen=True)
class ReleaseManifestReport:
    benchmark_release_id: str
    passed: bool
    release_state: str
    checks: dict[str, bool]
    observed: dict[str, int]
    bindings: tuple[dict[str, Any], ...]

    @property
    def failures(self) -> tuple[str, ...]:
        return tuple(name for name, value in self.checks.items() if not value)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def default_release_manifest_path() -> Path:
    return repository_root() / "data" / "release_manifest.json"


def load_release_manifest(path: str | Path) -> dict[str, Any]:
    return load_json_strict(path)


def derive_release_state(
    *,
    required_slot_ids: Iterable[str],
    mapped_slot_ids: Iterable[str],
    verified_slot_ids: Iterable[str],
    release_stage: str,
    manifest_passed: bool,
) -> str:
    required = set(map(str, required_slot_ids))
    mapped = set(map(str, mapped_slot_ids))
    verified = set(map(str, verified_slot_ids))
    if not mapped:
        return "development_only"
    if (
        release_stage == "formal"
        and manifest_passed
        and mapped == required
        and verified == required
    ):
        return "full_release_ready"
    return "partial_release"


def _load_runtime_admission() -> dict[str, bool]:
    return {
        report.runtime_id: report.execution_admitted
        for report in (
            validate_runtime_manifest(load_runtime_manifest(path))
            for path in runtime_manifest_paths()
        )
    }


def _validate_control_summary(
    *,
    root: Path,
    declaration: dict[str, Any],
    scenario_id: str,
    variants: tuple[str, ...],
) -> dict[str, bool]:
    try:
        path = safe_relative_path(
            root,
            str(declaration.get("path", "")),
            required_prefix="data",
            must_exist=True,
            require_file=True,
        )
        payload = load_json_strict(path)
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return {
            "control_path_safe_and_readable": False,
            "control_sha256_matches": False,
            "control_variants_exact": False,
            "control_has_no_run_errors": False,
            "control_pass_rate_meets_threshold": False,
            "control_is_explicit_scope": False,
            "control_summary_recomputed": False,
        }
    reports = tuple(payload.get("reports", ()))
    report_variants = [
        str(item.get("variant", ""))
        for item in reports
        if isinstance(item, dict)
    ]
    report_scenarios = [
        str(item.get("scenario_id", ""))
        for item in reports
        if isinstance(item, dict)
    ]
    try:
        threshold = float(declaration.get("minimum_task_pass_rate", -1))
        declared_rate = float(payload.get("task_pass_rate", -1))
        completed_runs = int(payload.get("completed_runs", -1))
    except (TypeError, ValueError):
        threshold = -1
        declared_rate = -1
        completed_runs = -1
    execution_counts = payload.get("execution_control_counts", {})
    try:
        explicit_count = int(execution_counts.get("true", -1))
    except (AttributeError, TypeError, ValueError):
        explicit_count = -1
    passed_count = sum(
        item.get("passed") is True
        for item in reports
        if isinstance(item, dict)
    )
    computed_rate = passed_count / len(reports) if reports else 0.0
    threshold_valid = MIN_EXECUTION_CONTROL_PASS_RATE <= threshold <= 1.0
    summary_recomputed = bool(
        len(reports) == len(variants)
        and completed_runs == len(reports)
        and abs(declared_rate - computed_rate) <= 1e-12
        and explicit_count == len(reports)
    )
    return {
        "control_path_safe_and_readable": True,
        "control_sha256_matches": file_sha256(path)
        == str(declaration.get("sha256", "")),
        "control_variants_exact": len(report_variants) == len(variants)
        and set(report_variants) == set(variants)
        and len(report_variants) == len(set(report_variants))
        and all(value == scenario_id for value in report_scenarios),
        "control_has_no_run_errors": payload.get("run_errors") == [],
        "control_pass_rate_meets_threshold": threshold_valid
        and computed_rate >= threshold,
        "control_is_explicit_scope": explicit_count == len(variants),
        "control_summary_recomputed": summary_recomputed,
    }


def validate_formal_evidence_roles(
    *,
    root: Path,
    declarations: dict[str, Any],
    benchmark_release_id: str,
    scenario_id: str,
    domain_id: str,
    family_id: str,
    instance_id: str,
    variants: tuple[str, ...],
) -> bool:
    if set(declarations) != FORMAL_EVIDENCE_ROLES:
        return False
    envelope_paths: list[str] = []
    payload_paths: list[str] = []
    envelopes: dict[str, dict[str, Any]] = {}
    envelope_hashes: dict[str, str] = {}
    for role, value in declarations.items():
        if not isinstance(value, dict):
            return False
        try:
            path = safe_relative_path(
                root,
                str(value.get("path", "")),
                required_prefix="data",
                must_exist=True,
                require_file=True,
            )
            envelope = load_json_strict(path)
        except (OSError, ValueError, json.JSONDecodeError):
            return False
        if not isinstance(envelope, dict):
            return False
        envelope_relative = path.relative_to(root).as_posix()
        envelope_paths.append(envelope_relative)
        envelope_hash = file_sha256(path)
        if (
            _SHA256.fullmatch(str(value.get("sha256", ""))) is None
            or envelope_hash != str(value.get("sha256", ""))
            or envelope.get("schema_version") != "1.0"
            or envelope.get("artifact_type") != role
            or envelope.get("benchmark_release_id")
            != benchmark_release_id
            or envelope.get("scenario_id") != scenario_id
            or envelope.get("domain_id") != domain_id
            or envelope.get("family_id") != family_id
            or envelope.get("instance_id") != instance_id
            or tuple(map(str, envelope.get("variant_ids", ())))
            != variants
            or _GIT_COMMIT.fullmatch(
                str(envelope.get("producer_commit", ""))
            )
            is None
        ):
            return False
        envelopes[role] = envelope
        envelope_hashes[role] = envelope_hash
        files = envelope.get("files")
        if not isinstance(files, list) or not files:
            return False
        local_paths: list[str] = []
        for item in files:
            if not isinstance(item, dict):
                return False
            relative = str(item.get("path", ""))
            expected_sha = str(item.get("sha256", ""))
            try:
                payload_path = safe_relative_path(
                    root,
                    relative,
                    required_prefix="data",
                    must_exist=True,
                    require_file=True,
                )
            except (OSError, ValueError):
                return False
            if (
                _SHA256.fullmatch(expected_sha) is None
                or file_sha256(payload_path) != expected_sha
            ):
                return False
            canonical_relative = payload_path.relative_to(root).as_posix()
            local_paths.append(canonical_relative)
            payload_paths.append(canonical_relative)
        if len(local_paths) != len(set(local_paths)):
            return False
    if (
        len(envelope_paths) != len(set(envelope_paths))
        or len(payload_paths) != len(set(payload_paths))
        or set(envelope_paths) & set(payload_paths)
    ):
        return False
    for role, required_roles in FORMAL_EVIDENCE_DEPENDENCIES.items():
        dependencies = envelopes[role].get("depends_on")
        if not isinstance(dependencies, dict):
            return False
        if set(dependencies) != required_roles:
            return False
        if any(
            str(dependencies[dependency])
            != envelope_hashes[dependency]
            for dependency in required_roles
        ):
            return False
    return True


def _validate_variant_semantics(
    *,
    scenario: Any,
    family: dict[str, Any] | None,
    boundary_taxonomy_ids: set[str],
) -> dict[str, bool]:
    items = tuple(scenario.raw.get("matched_variants", ()))
    boundaries: list[str] = []
    signatures: list[str] = []
    complete = len(items) == len(scenario.variants)
    for item in items:
        if not isinstance(item, dict):
            complete = False
            continue
        boundary = item.get("boundary_class_id")
        signature = item.get("recovery_signature_class")
        if not isinstance(boundary, str) or not boundary:
            complete = False
        else:
            boundaries.append(boundary)
        if not isinstance(signature, str) or not signature:
            complete = False
        else:
            signatures.append(signature)

    family = family or {}
    profile = dict(family.get("variant_profile", {}))
    allowed_signatures = set(
        map(str, family.get("required_recovery_signatures", ()))
    )
    minimum_signatures = int(
        profile.get("minimum_recovery_signatures", 0)
    )
    minimum_boundaries = int(profile.get("minimum_boundary_classes", 0))
    declared_directions = scenario.raw.get(
        "required_semantic_recovery_directions"
    )
    declared_directions_match = (
        True
        if declared_directions is None
        else set(map(str, declared_directions)) == set(signatures)
    )
    return {
        "variant_semantics_complete": complete,
        "variant_boundary_classes_known": complete
        and set(boundaries) <= boundary_taxonomy_ids,
        "variant_recovery_signatures_known": complete
        and set(signatures) <= allowed_signatures,
        "variant_boundary_coverage_meets_profile": complete
        and len(set(boundaries)) >= minimum_boundaries,
        "variant_recovery_coverage_meets_profile": complete
        and len(set(signatures)) >= minimum_signatures,
        "scenario_semantic_direction_declaration_matches": (
            declared_directions_match
        ),
    }


def _validate_hidden_bundle(
    *,
    root: Path,
    scenario_path: Path,
    declaration: dict[str, Any],
) -> bool:
    required = {
        "bundle_root",
        "private_attestation",
        "private_attestation_sha256",
        "public_commitment",
        "public_commitment_file_sha256",
        "usage_ledger",
        "usage_ledger_sha256",
    }
    if set(declaration) != required:
        return False
    try:
        bundle_root = safe_relative_path(
            root,
            str(declaration["bundle_root"]),
            required_prefix="data",
            must_exist=True,
        )
        private_path = safe_relative_path(
            root,
            str(declaration["private_attestation"]),
            required_prefix="data",
            must_exist=True,
            require_file=True,
        )
        public_path = safe_relative_path(
            root,
            str(declaration["public_commitment"]),
            required_prefix="data",
            must_exist=True,
            require_file=True,
        )
        ledger_path = safe_relative_path(
            root,
            str(declaration["usage_ledger"]),
            required_prefix="data",
            must_exist=True,
            require_file=True,
        )
        if (
            file_sha256(private_path)
            != str(declaration["private_attestation_sha256"])
            or file_sha256(public_path)
            != str(declaration["public_commitment_file_sha256"])
            or file_sha256(ledger_path)
            != str(declaration["usage_ledger_sha256"])
        ):
            return False
        private = load_json_strict(private_path)
        scenario = load_json_strict(scenario_path)
        if (
            str(private.get("scenario_id", ""))
            != str(scenario.get("scenario_id", ""))
            or str(private.get("scenario_sha256", ""))
            != file_sha256(scenario_path)
            or str(
                private.get("instance_spec_semantic_sha256", "")
            )
            != str(scenario.get("instance_spec_sha256", ""))
        ):
            return False
        allowed: tuple[str, ...] = ()
        try:
            allowed = (ledger_path.relative_to(bundle_root).as_posix(),)
        except ValueError:
            pass
        verify_frozen_bundle(
            bundle_root=bundle_root,
            private_attestation_path=private_path,
            public_commitment_path=public_path,
            allowed_unbound_relative_paths=allowed,
        )
        verify_hidden_test_eligibility(
            scenario_path=scenario_path,
            freeze_path=private_path,
            usage_ledger_path=ledger_path,
        )
    except (
        KeyError,
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
    ):
        return False
    return True


def validate_release_manifest(
    raw: dict[str, Any],
    *,
    root: Path | None = None,
) -> ReleaseManifestReport:
    root = (root or repository_root()).resolve()
    benchmark_release_id = str(raw.get("benchmark_release_id", ""))
    release_stage = str(raw.get("release_stage", ""))
    checks: dict[str, bool] = {
        "schema_version_is_1.0": raw.get("schema_version") == "1.0",
        "benchmark_release_id_present": bool(benchmark_release_id),
        "release_stage_valid": release_stage in {"development", "formal"},
    }

    try:
        matrix_path = safe_relative_path(
            root,
            str(raw.get("benchmark_matrix_path", "")),
            required_prefix="data",
            must_exist=True,
            require_file=True,
        )
        matrix = load_benchmark_matrix(matrix_path)
        matrix_report = validate_benchmark_matrix(matrix)
        matrix_hash_matches = file_sha256(matrix_path) == str(
            raw.get("benchmark_matrix_sha256", "")
        )
    except (OSError, ValueError, json.JSONDecodeError):
        matrix = {}
        matrix_report = validate_benchmark_matrix({})
        matrix_hash_matches = False
    checks["benchmark_matrix_valid"] = matrix_report.passed
    checks["benchmark_matrix_sha256_matches"] = matrix_hash_matches

    family_index = benchmark_family_index(matrix)
    boundary_taxonomy_ids = {
        str(item.get("id", ""))
        for item in matrix.get("boundary_taxonomy", ())
        if isinstance(item, dict)
    }
    slots = {str(slot["slot_id"]): slot for slot in benchmark_slots(matrix)}
    runtime_admission = _load_runtime_admission()
    binding_declarations = raw.get("scenario_bindings", ())
    if not isinstance(binding_declarations, list):
        binding_declarations = ()
    binding_rows: list[dict[str, Any]] = []
    scenario_ids: list[str] = []
    scenario_paths: list[str] = []
    mapped_slot_ids: list[str] = []
    verified_slot_ids: list[str] = []
    candidate_case_count = 0

    for declaration in binding_declarations:
        if not isinstance(declaration, dict):
            binding_rows.append(
                {
                    "scenario_id": "",
                    "passed": False,
                    "checks": {"binding_is_object": False},
                }
            )
            continue
        binding_checks: dict[str, bool] = {"binding_is_object": True}
        declared_scenario_id = str(declaration.get("scenario_id", ""))
        declared_path = str(declaration.get("scenario_path", ""))
        scenario_ids.append(declared_scenario_id)
        scenario_paths.append(declared_path)
        try:
            scenario_path = safe_relative_path(
                root,
                declared_path,
                required_prefix="data",
                must_exist=True,
                require_file=True,
            )
            relative_parts = scenario_path.relative_to(root).parts
            binding_checks["scenario_path_is_active_data_scenario"] = (
                len(relative_parts) >= 4
                and relative_parts[:2] == ("data", "scenarios")
                and relative_parts[-1] == "scenario.json"
            )
            scenario = load_native_scenario(scenario_path)
            document_failures = validate_native_scenario_document(scenario)
            admission = validate_native_scenario(scenario)
        except (KeyError, OSError, ValueError, json.JSONDecodeError):
            scenario = None
            admission = None
            document_failures = ("scenario_load_failed",)
            binding_checks["scenario_path_is_active_data_scenario"] = False

        if scenario is None or admission is None:
            binding_checks.update(
                {
                    "scenario_document_valid": False,
                    "scenario_sha256_matches": False,
                    "scenario_identity_matches": False,
                    "variant_ids_match": False,
                    "family_exists_in_matrix": False,
                    "family_variant_profile_matches": False,
                    "hard_admission_passes": False,
                    "runtime_execution_admitted": False,
                    "admission_artifact_sha256_match": False,
                    "execution_control_passes": False,
                }
            )
            variants: tuple[str, ...] = ()
            domain_id = str(declaration.get("domain_id", ""))
            family_id = str(declaration.get("family_id", ""))
            instance_id = str(declaration.get("instance_id", ""))
            split = str(declaration.get("split", ""))
        else:
            variants = scenario.variants
            domain_id = scenario.domain_id
            family_id = scenario.family_id
            instance_id = scenario.instance_id
            split = scenario.split
            binding_checks["scenario_document_valid"] = not document_failures
            binding_checks["scenario_sha256_matches"] = file_sha256(
                scenario.path
            ) == str(declaration.get("scenario_sha256", ""))
            binding_checks["scenario_identity_matches"] = all(
                (
                    scenario.scenario_id == declared_scenario_id,
                    domain_id == str(declaration.get("domain_id", "")),
                    family_id == str(declaration.get("family_id", "")),
                    instance_id == str(declaration.get("instance_id", "")),
                    split == str(declaration.get("split", "")),
                )
            )
            binding_checks["variant_ids_match"] = tuple(
                map(str, declaration.get("variant_ids", ()))
            ) == variants
            family = family_index.get((domain_id, family_id))
            binding_checks["family_exists_in_matrix"] = family is not None
            required_variant_count = int(
                (family or {})
                .get("variant_profile", {})
                .get("required_variant_count", 0)
            )
            binding_checks["family_variant_profile_matches"] = (
                required_variant_count == len(variants)
            )
            binding_checks.update(
                _validate_variant_semantics(
                    scenario=scenario,
                    family=family,
                    boundary_taxonomy_ids=boundary_taxonomy_ids,
                )
            )
            binding_checks["hard_admission_passes"] = bool(
                admission.passed and admission.admitted_tier == "hard"
            )
            binding_checks["runtime_execution_admitted"] = bool(
                runtime_admission.get(str(scenario.raw["runtime_id"]), False)
            )
            binding_checks["admission_artifact_sha256_match"] = dict(
                declaration.get("admission_artifact_sha256", {})
            ) == admission.artifact_sha256
            control_checks = _validate_control_summary(
                root=root,
                declaration=dict(declaration.get("control_evidence", {})),
                scenario_id=scenario.scenario_id,
                variants=variants,
            )
            binding_checks["execution_control_passes"] = all(
                control_checks.values()
            )
            binding_checks.update(control_checks)

        quality_role = str(declaration.get("quality_role", ""))
        binding_checks["quality_role_valid"] = quality_role in {
            "hard_development_candidate",
            "release_slot",
        }
        if quality_role == "hard_development_candidate":
            binding_checks["candidate_split_is_nonformal"] = split not in {
                "public_dev",
                "hidden_test",
            }
        else:
            binding_checks["candidate_split_is_nonformal"] = True

        formal_slot_id = (
            f"{domain_id}/{family_id}/{instance_id}"
            if split in {"public_dev", "hidden_test"}
            else ""
        )
        formal_mapping = bool(
            formal_slot_id
            and formal_slot_id in slots
            and slots[formal_slot_id]["split"] == split
        )
        binding_checks["formal_slot_mapping_matches"] = (
            formal_mapping if quality_role == "release_slot" else not formal_slot_id
        )
        if quality_role == "release_slot" and scenario is not None:
            formal_evidence_ready = validate_formal_evidence_roles(
                root=root,
                declarations=dict(declaration.get("formal_evidence", {})),
                benchmark_release_id=benchmark_release_id,
                scenario_id=declared_scenario_id,
                domain_id=domain_id,
                family_id=family_id,
                instance_id=instance_id,
                variants=variants,
            )
        else:
            formal_evidence_ready = quality_role != "release_slot"
        binding_checks["formal_evidence_requirement_satisfied"] = (
            formal_evidence_ready
        )
        hidden_ready = (
            _validate_hidden_bundle(
                root=root,
                scenario_path=scenario.path,
                declaration=dict(
                    declaration.get("hidden_test_evidence", {})
                ),
            )
            if split == "hidden_test" and scenario is not None
            else split != "hidden_test"
        )
        binding_checks["hidden_test_lifecycle_requirement_satisfied"] = (
            hidden_ready
        )

        binding_passed = all(binding_checks.values())
        if quality_role == "hard_development_candidate" and binding_passed:
            candidate_case_count += len(variants)
        if formal_mapping:
            mapped_slot_ids.append(formal_slot_id)
            if binding_passed:
                verified_slot_ids.append(formal_slot_id)
        binding_rows.append(
            {
                "scenario_id": declared_scenario_id,
                "domain_id": domain_id,
                "family_id": family_id,
                "instance_id": instance_id,
                "split": split,
                "quality_role": quality_role,
                "variant_count": len(variants),
                "formal_slot_id": formal_slot_id or None,
                "formal_evidence_ready": (
                    formal_evidence_ready
                    if quality_role == "release_slot"
                    else False
                ),
                "hidden_test_eligible": (
                    hidden_ready if split == "hidden_test" else False
                ),
                "passed": binding_passed,
                "checks": binding_checks,
            }
        )

    checks["scenario_bindings_nonempty"] = bool(binding_rows)
    checks["scenario_ids_unique"] = len(scenario_ids) == len(set(scenario_ids))
    checks["scenario_paths_unique"] = len(scenario_paths) == len(
        set(scenario_paths)
    )
    checks["formal_slot_bindings_unique"] = len(mapped_slot_ids) == len(
        set(mapped_slot_ids)
    )
    checks["all_declared_bindings_verify"] = bool(binding_rows) and all(
        bool(row["passed"]) for row in binding_rows
    )
    manifest_passed = all(checks.values())
    required_slot_ids = set(slots)
    release_state = derive_release_state(
        required_slot_ids=required_slot_ids,
        mapped_slot_ids=mapped_slot_ids,
        verified_slot_ids=verified_slot_ids,
        release_stage=release_stage,
        manifest_passed=manifest_passed,
    )
    return ReleaseManifestReport(
        benchmark_release_id=benchmark_release_id,
        passed=manifest_passed,
        release_state=release_state,
        checks=checks,
        observed={
            **matrix_report.observed,
            "declared_binding_count": len(binding_rows),
            "verified_binding_count": sum(
                bool(row["passed"]) for row in binding_rows
            ),
            "hard_development_candidate_count": sum(
                row.get("quality_role") == "hard_development_candidate"
                and row.get("passed") is True
                for row in binding_rows
            ),
            "hard_development_candidate_case_count": candidate_case_count,
            "formal_mapped_slot_count": len(set(mapped_slot_ids)),
            "formal_verified_slot_count": len(set(verified_slot_ids)),
            "missing_formal_slot_count": len(
                required_slot_ids - set(verified_slot_ids)
            ),
        },
        bindings=tuple(binding_rows),
    )


__all__ = [
    "FORMAL_EVIDENCE_DEPENDENCIES",
    "FORMAL_EVIDENCE_ROLES",
    "ReleaseManifestReport",
    "default_release_manifest_path",
    "derive_release_state",
    "file_sha256",
    "load_release_manifest",
    "validate_formal_evidence_roles",
    "validate_release_manifest",
]
