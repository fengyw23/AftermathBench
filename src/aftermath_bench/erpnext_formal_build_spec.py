from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .erpnext_sales_return_state_evidence import (
    canonical_state_fingerprint,
    validate_bundle_manifest,
)
from .formal_evidence_builder import verify_formal_input_lock
from .integrations.erpnext_faults import ERP_NEXT_FAULT_VARIANTS
from .integrations.erpnext_sales_return_agent import (
    ERPNextSalesReturnEnvironment,
)
from .integrations.erpnext_sales_return_evaluator import (
    evaluate_sales_return_recovery,
)
from .integrations.erpnext_multiwarehouse_agent import (
    ERPNextMultiwarehouseEnvironment,
)
from .integrations.erpnext_multiwarehouse_evaluator import (
    evaluate_multiwarehouse_recovery,
)
from .native_admission import validate_native_scenario
from .native_formal_sources import (
    ExactFileManifest,
    NativeFormalSourceError,
    current_git_commit,
    load_exact_file_manifest,
    repository_directory,
    repository_file,
    require_identifier,
    require_sha256,
    sha256_file,
    strict_object,
    validate_output_directory,
    write_formal_build_spec,
)
from .native_formal_spec import (
    CompletionEvidenceSources,
    EvaluatorContractSources,
    FormalSource,
    InputEvidenceSources,
    NativeFormalSpecError,
    PublicToolContract,
    ToolContractSources,
    VariantCompletionEvidence,
    VariantInputEvidence,
    build_completion_roles,
    build_evaluator_role,
    build_input_evidence_roles,
    build_tool_contract_role,
    empty_completion_roles,
)
from .native_sales_family import SALES_RETURN_TOOL_DEFINITIONS
from .native_erpnext_multiwarehouse_family import (
    ERP_NEXT_MULTIWAREHOUSE_TOOLS,
)
from .native_scenario import (
    NativeScenario,
    load_native_scenario,
    validate_native_scenario_document,
)
from .release_manifest import MIN_EXECUTION_CONTROL_PASS_RATE

_GIT_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_FAMILY_ID = "erpnext-sales-return-exchange-reconciliation"
_DOMAIN_ID = "erpnext"
_RUNTIME_ID = "erpnext-v15"
_SPLIT = "public_dev"
_TIER = "hard"
_ADMISSION_STATUS = "validated_hard"
_VARIANTS = tuple(ERP_NEXT_FAULT_VARIANTS)
_EXPECTED_VARIANT_COUNT = len(_VARIANTS)
_CAPTURE_MODE = "simultaneous_service_quiescence"
_TOOL_DEFINITION_SOURCE = "src/aftermath_bench/native_sales_family.py"
_TOOL_IMPLEMENTATION_SOURCE = (
    "src/aftermath_bench/integrations/erpnext_sales_return_agent.py"
)
_TOOL_IMPLEMENTATION_DEPENDENCIES = (
    "src/aftermath_bench/integrations/erpnext_return_agent.py",
    "src/aftermath_bench/integrations/erpnext_sales_return_evidence.py",
    "src/aftermath_bench/integrations/erpnext_sales_return_prefix.py",
    "src/aftermath_bench/integrations/erpnext_faults.py",
    "src/aftermath_bench/integrations/erpnext_stack.py",
    "src/aftermath_bench/integrations/frappe.py",
)
_NATIVE_RUNTIME_CONTRACT_SOURCES = (
    "runtimes/erpnext/runtime.lock.json",
    "runtimes/erpnext/compose.yaml",
    "runtimes/erpnext/control/Containerfile",
    "runtimes/erpnext/bridge/aftermath_frappe_bridge.py",
    "runtimes/erpnext/patches/pin-python-base.patch",
    "runtimes/erpnext/patches/atomic-assets-link.patch",
    "scripts/build_erpnext_runtime.py",
    "scripts/manage_erpnext_stack.py",
    "scripts/run_erpnext_sales_return_failure.py",
    "scripts/run_erpnext_sales_return_control.py",
    "scripts/capture_erpnext_sales_return_state_evidence.py",
    "src/aftermath_bench/integrations/erpnext_runtime.py",
    "src/aftermath_bench/integrations/erpnext_faults.py",
    "src/aftermath_bench/runtime_services/gateway.py",
    "src/aftermath_bench/runtime_services/remittance.py",
)
_BOUNDARY_CONTRACT_SOURCES = (
    "scripts/run_erpnext_sales_return_failure.py",
    "scripts/capture_erpnext_sales_return_state_evidence.py",
    "src/aftermath_bench/erpnext_sales_return_state_evidence.py",
    "src/aftermath_bench/integrations/erpnext_faults.py",
    "src/aftermath_bench/integrations/erpnext_sales_return_evidence.py",
)
_RUNTIME_SOURCE_VERIFICATION = "runtime/source-verification.json"
_EVALUATOR_SOURCE = (
    "src/aftermath_bench/integrations/erpnext_sales_return_evaluator.py"
)
_SCORED_STATE_FIELDS = (
    "original_sales_order",
    "original_delivery_note",
    "quality_inspection",
    "affected_invoice",
    "unaffected_invoice",
    "shared_payment_entry",
    "sales_return",
    "credit_note",
    "replacement_sales_order",
    "replacement_delivery_note",
    "sales_returns",
    "credit_notes",
    "replacement_delivery_notes",
    "replacement_invoices",
    "stock_ledger_entries",
    "gl_entries",
    "rq_jobs",
    "pickup_delivery",
)


@dataclass(frozen=True)
class ERPNextFormalBuildProfile:
    family_id: str
    variants: tuple[str, ...]
    state_evidence_artifact_type: str
    failure_boundary_artifact_type: str
    reference_artifact_type: str
    raw_boundary_state_field: str
    raw_surface_failure_path: tuple[str, ...]
    accepted_failure_schema_versions: frozenset[str]
    accepted_reference_schema_versions: frozenset[str]
    tool_definition_source: str
    tool_implementation_source: str
    tool_implementation_dependencies: tuple[str, ...]
    native_runtime_contract_sources: tuple[str, ...]
    boundary_contract_sources: tuple[str, ...]
    evaluator_source: str
    scored_state_fields: tuple[str, ...]
    tool_definitions: tuple[Any, ...]
    environment_tool_names: tuple[str, ...]
    tool_definition_role_path: str
    tool_implementation_role_path: str
    tool_implementation_symbol: str
    evaluator_role_path: str
    evaluator_symbol: str
    evaluator: Callable[..., Any]
    boundary_state_projection: Callable[[dict[str, Any]], dict[str, Any]]


def _identity_state_projection(
    state: dict[str, Any],
) -> dict[str, Any]:
    return state


_SALES_RETURN_PROFILE = ERPNextFormalBuildProfile(
    family_id=_FAMILY_ID,
    variants=_VARIANTS,
    state_evidence_artifact_type="erpnext_sales_return_state_evidence",
    failure_boundary_artifact_type="erpnext_sales_return_failure_boundary",
    reference_artifact_type="erpnext_sales_return_reference_recovery",
    raw_boundary_state_field="failure_boundary_evidence",
    raw_surface_failure_path=("visible_failure",),
    accepted_failure_schema_versions=frozenset({"1.0"}),
    accepted_reference_schema_versions=frozenset({"1.0"}),
    tool_definition_source=_TOOL_DEFINITION_SOURCE,
    tool_implementation_source=_TOOL_IMPLEMENTATION_SOURCE,
    tool_implementation_dependencies=_TOOL_IMPLEMENTATION_DEPENDENCIES,
    native_runtime_contract_sources=_NATIVE_RUNTIME_CONTRACT_SOURCES,
    boundary_contract_sources=_BOUNDARY_CONTRACT_SOURCES,
    evaluator_source=_EVALUATOR_SOURCE,
    scored_state_fields=_SCORED_STATE_FIELDS,
    tool_definitions=tuple(SALES_RETURN_TOOL_DEFINITIONS),
    environment_tool_names=tuple(ERPNextSalesReturnEnvironment.TOOL_NAMES),
    tool_definition_role_path="sources/native_sales_family.py",
    tool_implementation_role_path="sources/erpnext_sales_return_agent.py",
    tool_implementation_symbol="ERPNextSalesReturnEnvironment.invoke",
    evaluator_role_path="sources/erpnext_sales_return_evaluator.py",
    evaluator_symbol="evaluate_sales_return_recovery",
    evaluator=evaluate_sales_return_recovery,
    boundary_state_projection=_identity_state_projection,
)

MULTIWAREHOUSE_FORMAL_PROFILE = ERPNextFormalBuildProfile(
    family_id="erpnext-multiwarehouse-transfer",
    variants=_VARIANTS,
    state_evidence_artifact_type="erpnext_multiwarehouse_state_evidence",
    failure_boundary_artifact_type="erpnext_multiwarehouse_failure_boundary",
    reference_artifact_type="erpnext_multiwarehouse_reference_recovery",
    raw_boundary_state_field="boundary_evidence",
    raw_surface_failure_path=("latest_attempt", "result"),
    accepted_failure_schema_versions=frozenset({"1.0"}),
    accepted_reference_schema_versions=frozenset({"1.0"}),
    tool_definition_source="src/aftermath_bench/native_erpnext_multiwarehouse_family.py",
    tool_implementation_source="src/aftermath_bench/integrations/erpnext_multiwarehouse_agent.py",
    tool_implementation_dependencies=(
        "src/aftermath_bench/integrations/erpnext_multiwarehouse_evidence.py",
        "src/aftermath_bench/integrations/erpnext_multiwarehouse_prefix.py",
        "src/aftermath_bench/integrations/erpnext_faults.py",
        "src/aftermath_bench/integrations/erpnext_stack.py",
        "src/aftermath_bench/integrations/frappe.py",
    ),
    native_runtime_contract_sources=(
        "runtimes/erpnext/runtime.lock.json",
        "runtimes/erpnext/compose.yaml",
        "runtimes/erpnext/control/Containerfile",
        "runtimes/erpnext/bridge/aftermath_frappe_bridge.py",
        "scripts/build_erpnext_runtime.py",
        "scripts/manage_erpnext_stack.py",
        "scripts/run_erpnext_multiwarehouse_failure.py",
        "scripts/run_erpnext_multiwarehouse_control.py",
        "scripts/capture_erpnext_multiwarehouse_state_evidence.py",
        "src/aftermath_bench/erpnext_multiwarehouse_state_evidence.py",
        "src/aftermath_bench/integrations/erpnext_runtime.py",
        "src/aftermath_bench/runtime_services/gateway.py",
    ),
    boundary_contract_sources=(
        "scripts/run_erpnext_multiwarehouse_failure.py",
        "scripts/capture_erpnext_multiwarehouse_state_evidence.py",
        "src/aftermath_bench/erpnext_multiwarehouse_state_evidence.py",
        "src/aftermath_bench/integrations/erpnext_multiwarehouse_evidence.py",
    ),
    evaluator_source="src/aftermath_bench/integrations/erpnext_multiwarehouse_evaluator.py",
    scored_state_fields=(
        "stock_seed", "material_request", "outgoing_stock_entry",
        "clinic_sales_order", "protected_sales_order", "protected_pick_list",
        "protected_reservation", "second_leg_stock_entries",
        "stock_reservation_entries", "clinic_pick_lists", "stock_ledger_entries",
        "bins", "batch", "serial_and_batch_bundles", "rq_jobs",
        "arrival_deliveries",
    ),
    tool_definitions=tuple(ERP_NEXT_MULTIWAREHOUSE_TOOLS),
    environment_tool_names=tuple(ERPNextMultiwarehouseEnvironment.TOOL_NAMES),
    tool_definition_role_path="sources/native_erpnext_multiwarehouse_family.py",
    tool_implementation_role_path="sources/erpnext_multiwarehouse_agent.py",
    tool_implementation_symbol="ERPNextMultiwarehouseEnvironment.invoke",
    evaluator_role_path="sources/erpnext_multiwarehouse_evaluator.py",
    evaluator_symbol="evaluate_multiwarehouse_recovery",
    evaluator=evaluate_multiwarehouse_recovery,
    boundary_state_projection=_identity_state_projection,
)


class ERPNextFormalBuildSpecError(ValueError):
    """Raised when ERPNext evidence cannot support a formal package."""


_MISSING = object()


def _value_at_path(payload: dict[str, Any], path: tuple[str, ...]) -> Any:
    current: Any = payload
    for field in path:
        if not isinstance(current, dict) or field not in current:
            return _MISSING
        current = current[field]
    return current


@dataclass(frozen=True)
class _VariantEvidence:
    variant_id: str
    reset_path: Path
    reset_relative: str
    reset: dict[str, Any]
    boundary_path: Path
    boundary_relative: str
    boundary: dict[str, Any]
    raw_boundary_path: Path
    raw_boundary_relative: str
    raw_boundary: dict[str, Any]
    raw_reference_path: Path
    raw_reference_relative: str
    raw_reference: dict[str, Any]
    reference_start_path: Path
    reference_start_relative: str
    reference_start: dict[str, Any]
    trajectory_path: Path | None
    trajectory_relative: str | None
    trajectory: dict[str, Any] | None
    pre_model_boundary_path: Path | None
    pre_model_boundary_relative: str | None


@dataclass(frozen=True)
class ERPNextFormalBuildSpecResult:
    spec: dict[str, Any]
    scenario_path: str
    runtime_manifest_path: str
    control_manifest_path: str | None
    capture_bundle_manifest_paths: tuple[str, ...]


def _source_error(error: Exception) -> ERPNextFormalBuildSpecError:
    return ERPNextFormalBuildSpecError(str(error))


def _repo_file(
    root: Path,
    value: str | Path,
    *,
    label: str,
) -> tuple[Path, str]:
    try:
        return repository_file(root, value, label=label)
    except NativeFormalSourceError as error:
        raise _source_error(error) from error


def _repo_directory(
    root: Path,
    value: str | Path,
    *,
    label: str,
) -> tuple[Path, str]:
    try:
        return repository_directory(root, value, label=label)
    except NativeFormalSourceError as error:
        raise _source_error(error) from error


def _exact_manifest(
    root: Path,
    value: str | Path,
    *,
    label: str,
) -> ExactFileManifest:
    try:
        return load_exact_file_manifest(root, value, label=label)
    except NativeFormalSourceError as error:
        raise _source_error(error) from error


def discover_active_erpnext_public_dev_scenario(
    root: str | Path,
    *,
    profile: ERPNextFormalBuildProfile = _SALES_RETURN_PROFILE,
) -> str:
    resolved_root = Path(root).resolve()
    candidates: list[str] = []
    for path in sorted((resolved_root / "data" / "scenarios").glob(
        "*/scenario.json"
    )):
        try:
            scenario = load_native_scenario(path)
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        raw = scenario.raw
        if (
            scenario.domain_id == _DOMAIN_ID
            and scenario.family_id == profile.family_id
            and scenario.split == _SPLIT
            and scenario.tier == _TIER
            and raw.get("admission_status") == _ADMISSION_STATUS
        ):
            candidates.append(path.relative_to(resolved_root).as_posix())
    if len(candidates) != 1:
        raise ERPNextFormalBuildSpecError(
            "expected exactly one admitted ERPNext sales-return public_dev "
            f"scenario, found {len(candidates)}"
        )
    return candidates[0]


def _validate_active_scenario(
    root: Path,
    scenario_path: str | Path | None,
    *,
    profile: ERPNextFormalBuildProfile = _SALES_RETURN_PROFILE,
) -> tuple[NativeScenario, str, str]:
    selected = (
        scenario_path
        if scenario_path is not None
        else discover_active_erpnext_public_dev_scenario(
            root,
            profile=profile,
        )
    )
    path, relative = _repo_file(
        root,
        selected,
        label="active ERPNext scenario",
    )
    scenario = load_native_scenario(path)
    document_failures = validate_native_scenario_document(scenario)
    if document_failures:
        raise ERPNextFormalBuildSpecError(
            "active ERPNext scenario document is invalid: "
            + ", ".join(document_failures)
        )
    raw = scenario.raw
    if (
        scenario.domain_id != _DOMAIN_ID
        or scenario.family_id != profile.family_id
        or raw.get("runtime_id") != _RUNTIME_ID
        or scenario.split != _SPLIT
        or scenario.tier != _TIER
        or raw.get("admission_status") != _ADMISSION_STATUS
        or raw.get("hidden_test_eligible") is not False
        or scenario.variants != profile.variants
    ):
        raise ERPNextFormalBuildSpecError(
            "active ERPNext scenario is not the admitted fresh public-dev slot"
        )
    try:
        instance_spec_sha256 = require_sha256(
            raw.get("instance_spec_sha256"),
            label="scenario instance_spec_sha256",
        )
    except NativeFormalSourceError as error:
        raise _source_error(error) from error
    prefix = strict_object(
        scenario.resolve_artifact("prefix"),
        label="scenario admission prefix",
    )
    if (
        prefix.get("scenario_id") != scenario.scenario_id
        or prefix.get("instance_spec_sha256") != instance_spec_sha256
    ):
        raise ERPNextFormalBuildSpecError(
            "scenario and prefix instance identities disagree"
        )
    admission = validate_native_scenario(scenario)
    if (
        not admission.passed
        or admission.admitted_tier != _TIER
        or admission.scenario_id != scenario.scenario_id
    ):
        raise ERPNextFormalBuildSpecError(
            "active ERPNext scenario does not recompute as hard-admitted"
        )
    return scenario, relative, instance_spec_sha256


def _validate_runtime_contract(
    root: Path,
    manifest: ExactFileManifest,
) -> tuple[str, str]:
    lock_path, _ = _repo_file(
        root,
        "runtimes/erpnext/runtime.lock.json",
        label="ERPNext runtime lock",
    )
    lock = strict_object(lock_path, label="ERPNext runtime lock")
    driver = lock.get("build_driver")
    driver_revision = (
        driver.get("revision") if isinstance(driver, dict) else None
    )
    if (
        lock.get("schema_version") != "0.3"
        or not isinstance(driver_revision, str)
        or _GIT_COMMIT.fullmatch(driver_revision) is None
        or not isinstance(lock.get("image"), str)
        or not lock["image"]
    ):
        raise ERPNextFormalBuildSpecError(
            "ERPNext runtime lock is not a pinned source-build contract"
        )
    locked_refs = []
    for key in ("frappe", "erpnext"):
        source = lock.get(key)
        if (
            not isinstance(source, dict)
            or _GIT_COMMIT.fullmatch(str(source.get("revision", "")))
            is None
        ):
            raise ERPNextFormalBuildSpecError(
                f"ERPNext runtime lock has an invalid {key} source"
            )
        locked_refs.append(
            (
                str(source.get("repository")),
                str(source.get("tag")),
                str(source.get("revision")),
            )
        )
    report_path = manifest.root / _RUNTIME_SOURCE_VERIFICATION
    if not report_path.is_file():
        raise ERPNextFormalBuildSpecError(
            "ERPNext runtime source-verification report is missing"
        )
    manifest.require_file(
        report_path,
        label="ERPNext runtime source-verification report",
    )
    report = strict_object(
        report_path,
        label="ERPNext runtime source-verification report",
    )
    plan = report.get("plan")
    verification = report.get("source_verification")
    image = report.get("image_build")
    observed_refs = ()
    if isinstance(verification, dict):
        rows = verification.get("source_refs")
        if isinstance(rows, list):
            observed_refs = tuple(
                (
                    str(row.get("repository")),
                    str(row.get("tag")),
                    str(row.get("revision")),
                )
                for row in rows
                if isinstance(row, dict) and row.get("passed") is True
            )
    if (
        not isinstance(plan, dict)
        or plan.get("expected_driver_revision") != driver_revision
        or plan.get("image") != lock["image"]
        or not isinstance(verification, dict)
        or verification.get("build_driver_revision") != driver_revision
        or verification.get("passed") is not True
        or observed_refs != tuple(locked_refs)
        or not isinstance(image, dict)
        or image.get("built_from_verified_revision") != driver_revision
        or image.get("image") != lock["image"]
        or not str(image.get("image_id", "")).startswith("sha256:")
    ):
        raise ERPNextFormalBuildSpecError(
            "ERPNext source-verification report disagrees with runtime.lock"
        )
    return driver_revision, report_path.relative_to(root).as_posix()


def _load_bundle_manifests(
    root: Path,
    values: Iterable[str | Path],
) -> dict[str, tuple[str, dict[str, Any]]]:
    result: dict[str, tuple[str, dict[str, Any]]] = {}
    for index, value in enumerate(values):
        path, relative = _repo_file(
            root,
            value,
            label=f"ERPNext capture bundle manifest[{index}]",
        )
        try:
            payload = validate_bundle_manifest(path)
        except ValueError as error:
            raise ERPNextFormalBuildSpecError(str(error)) from error
        if payload.get("capture_mode") != _CAPTURE_MODE:
            raise ERPNextFormalBuildSpecError(
                "ERPNext capture bundle did not use simultaneous quiescence"
            )
        digest = sha256_file(path)
        if digest in result:
            raise ERPNextFormalBuildSpecError(
                "ERPNext capture bundle manifests must have unique bytes"
            )
        result[digest] = (relative, payload)
    if not result:
        raise ERPNextFormalBuildSpecError(
            "at least one ERPNext capture bundle manifest is required"
        )
    return result


def _validate_capture_bundle(
    capture: dict[str, Any],
    *,
    manifests: dict[str, tuple[str, dict[str, Any]]],
    label: str,
) -> str:
    try:
        digest = require_sha256(
            capture.get("bundle_manifest_file_sha256"),
            label=f"{label} bundle_manifest_file_sha256",
        )
    except NativeFormalSourceError as error:
        raise _source_error(error) from error
    selected = manifests.get(digest)
    if selected is None:
        raise ERPNextFormalBuildSpecError(
            f"{label} references an undeclared native bundle"
        )
    relative, expected = selected
    if capture.get("bundle") != expected:
        raise ERPNextFormalBuildSpecError(
            f"{label} embedded native bundle manifest drifted"
        )
    return relative


def _validate_identity(
    payload: dict[str, Any],
    *,
    scenario: NativeScenario,
    variant_id: str,
    label: str,
) -> None:
    if (
        payload.get("scenario_id") != scenario.scenario_id
        or payload.get("variant_id", payload.get("variant")) != variant_id
    ):
        raise ERPNextFormalBuildSpecError(
            f"{label} identity does not match the scenario"
        )


def _validate_reset(
    capture: dict[str, Any],
    *,
    scenario: NativeScenario,
    variant_id: str,
    prefix_sha256: str,
    bundle_manifests: dict[str, tuple[str, dict[str, Any]]],
    profile: ERPNextFormalBuildProfile = _SALES_RETURN_PROFILE,
) -> str:
    label = f"ERPNext reset capture {variant_id}"
    _validate_identity(
        capture,
        scenario=scenario,
        variant_id=variant_id,
        label=label,
    )
    state = capture.get("state")
    if (
        capture.get("schema_version") != "1.0"
        or capture.get("artifact_type")
        != profile.state_evidence_artifact_type
        or capture.get("instance_id") != scenario.instance_id
        or capture.get("phase") != "reset"
        or capture.get("reset_verified") is not True
        or capture.get("prefix_file_sha256") != prefix_sha256
        or not isinstance(state, dict)
        or capture.get("state_fingerprint")
        != canonical_state_fingerprint(state)
    ):
        raise ERPNextFormalBuildSpecError(
            f"{label} is not a verified exact reset"
        )
    return _validate_capture_bundle(
        capture,
        manifests=bundle_manifests,
        label=label,
    )


def _validate_raw_boundary(
    payload: dict[str, Any],
    *,
    scenario: NativeScenario,
    variant_id: str,
    profile: ERPNextFormalBuildProfile = _SALES_RETURN_PROFILE,
) -> dict[str, Any]:
    label = f"ERPNext raw boundary {variant_id}"
    _validate_identity(
        payload,
        scenario=scenario,
        variant_id=variant_id,
        label=label,
    )
    validation = payload.get("boundary_validation")
    latest_attempt = payload.get("latest_attempt")
    visible = payload.get("visible_failure")
    if visible is None and isinstance(latest_attempt, dict):
        visible = latest_attempt.get("result")
    if (
        payload.get("schema_version")
        not in profile.accepted_failure_schema_versions
        or payload.get("artifact_type")
        != profile.failure_boundary_artifact_type
        or payload.get("phase") != "boundary"
        or not isinstance(visible, dict)
        or visible.get("ok") is not False
        or not isinstance(validation, dict)
        or validation.get("passed") is not True
        or not isinstance(validation.get("checks"), dict)
        or not validation["checks"]
        or not all(value is True for value in validation["checks"].values())
        or not isinstance(
            payload.get(profile.raw_boundary_state_field),
            dict,
        )
    ):
        raise ERPNextFormalBuildSpecError(
            f"{label} is not a passing ambiguous native boundary"
        )
    return visible


def _validate_boundary(
    capture: dict[str, Any],
    *,
    path: Path,
    reset_path: Path,
    raw_boundary_path: Path,
    raw_boundary: dict[str, Any],
    scenario: NativeScenario,
    variant_id: str,
    prefix_sha256: str,
    bundle_manifests: dict[str, tuple[str, dict[str, Any]]],
    profile: ERPNextFormalBuildProfile = _SALES_RETURN_PROFILE,
) -> str:
    del path
    label = f"ERPNext boundary capture {variant_id}"
    _validate_identity(
        capture,
        scenario=scenario,
        variant_id=variant_id,
        label=label,
    )
    visible = _validate_raw_boundary(
        raw_boundary,
        scenario=scenario,
        variant_id=variant_id,
        profile=profile,
    )
    state = capture.get("state")
    raw_state = raw_boundary[profile.raw_boundary_state_field]
    if (
        capture.get("schema_version") != "1.0"
        or capture.get("artifact_type")
        != profile.state_evidence_artifact_type
        or capture.get("instance_id") != scenario.instance_id
        or capture.get("phase") != "boundary"
        or capture.get("boundary_validation_passed") is not True
        or capture.get("prefix_file_sha256") != prefix_sha256
        or capture.get("reset_evidence_file_sha256")
        != sha256_file(reset_path)
        or capture.get("failure_report_file_sha256")
        != sha256_file(raw_boundary_path)
        or capture.get("surface_result")
        != scenario.raw["ambiguous_operation"]["surface_result"]
        or capture.get("visible_failure") != visible
        or not isinstance(state, dict)
        or profile.boundary_state_projection(state)
        != profile.boundary_state_projection(raw_state)
        or capture.get("state_fingerprint")
        != canonical_state_fingerprint(state)
    ):
        raise ERPNextFormalBuildSpecError(
            f"{label} is not cross-bound to reset, failure, and native state"
        )
    return _validate_capture_bundle(
        capture,
        manifests=bundle_manifests,
        label=label,
    )


def _validate_boundary_replay_equivalence(
    boundary: dict[str, Any],
    replay: dict[str, Any],
    *,
    variant_id: str,
    profile: ERPNextFormalBuildProfile = _SALES_RETURN_PROFILE,
) -> None:
    """Require identical bindings and recovery-relevant boundary state.

    Both captures must first pass ``_validate_boundary`` independently.  This
    comparison then permits only exact-state drift that the selected native
    profile explicitly projects away.  The sales-return profile uses the
    identity projection, while manufacturing excludes terminal RQ audit rows
    but retains all pending work.
    """

    ignored = {"state", "state_fingerprint"}
    boundary_bindings = {
        key: value for key, value in boundary.items() if key not in ignored
    }
    replay_bindings = {
        key: value for key, value in replay.items() if key not in ignored
    }
    if boundary_bindings != replay_bindings:
        raise ERPNextFormalBuildSpecError(
            f"ERPNext reference-start capture {variant_id} does not "
            "preserve the admitted boundary bindings"
        )
    boundary_state = boundary.get("state")
    replay_state = replay.get("state")
    if (
        not isinstance(boundary_state, dict)
        or not isinstance(replay_state, dict)
        or profile.boundary_state_projection(boundary_state)
        != profile.boundary_state_projection(replay_state)
    ):
        raise ERPNextFormalBuildSpecError(
            f"ERPNext reference-start capture {variant_id} does not "
            "match the admitted recovery boundary"
        )


def _evaluation_payload(
    evidence: dict[str, Any],
    *,
    prefix: dict[str, Any],
    profile: ERPNextFormalBuildProfile = _SALES_RETURN_PROFILE,
) -> dict[str, Any]:
    evaluation = profile.evaluator(evidence, prefix=prefix)
    return {
        "passed": evaluation.passed,
        "components": evaluation.components,
        "checks": evaluation.checks,
        "diagnostics": evaluation.diagnostics,
        "failures": list(evaluation.failures),
    }


def _validate_reference(
    payload: dict[str, Any],
    *,
    prefix: dict[str, Any],
    scenario: NativeScenario,
    variant_id: str,
    profile: ERPNextFormalBuildProfile = _SALES_RETURN_PROFILE,
) -> tuple[str, ...]:
    label = f"ERPNext reference report {variant_id}"
    _validate_identity(
        payload,
        scenario=scenario,
        variant_id=variant_id,
        label=label,
    )
    trace = payload.get("reference_trace")
    final = payload.get("final_evidence")
    if (
        payload.get("schema_version")
        not in profile.accepted_reference_schema_versions
        or payload.get("artifact_type")
        != profile.reference_artifact_type
        or payload.get("phase") != "reference"
        or payload.get("control_error") is not None
        or not isinstance(trace, list)
        or not trace
        or not isinstance(final, dict)
        or payload.get("evaluation")
        != _evaluation_payload(final, prefix=prefix, profile=profile)
    ):
        raise ERPNextFormalBuildSpecError(
            f"{label} is not a complete recomputed passing recovery"
        )
    if payload["evaluation"]["passed"] is not True:
        raise ERPNextFormalBuildSpecError(f"{label} did not pass")
    known_tools = set(profile.environment_tool_names)
    for index, event in enumerate(trace):
        if (
            not isinstance(event, dict)
            or event.get("tool") not in known_tools
            or not isinstance(event.get("arguments"), dict)
            or "result" not in event
        ):
            raise ERPNextFormalBuildSpecError(
                f"{label} trace[{index}] is not a public-tool event"
            )
    return tuple(sorted(payload["evaluation"]["checks"]))


def _validate_control_trajectory(
    payload: dict[str, Any],
    *,
    root: Path,
    prefix: dict[str, Any],
    scenario: NativeScenario,
    instance_spec_sha256: str,
    variant_id: str,
    formal_input_lock_path: str,
    trusted_producer_commit: str,
    raw_boundary_path: Path,
    raw_boundary: dict[str, Any],
    profile: ERPNextFormalBuildProfile = _SALES_RETURN_PROFILE,
) -> str:
    label = f"ERPNext execution-control trajectory {variant_id}"
    _validate_identity(
        payload,
        scenario=scenario,
        variant_id=variant_id,
        label=label,
    )
    final = payload.get("final_evidence")
    if (
        payload.get("domain") != scenario.domain_id
        or payload.get("family") != scenario.family_id
        or payload.get("instance_id") != scenario.instance_id
        or payload.get("instance_spec_sha256") != instance_spec_sha256
        or payload.get("execution_control") is not True
        or not isinstance(payload.get("run_id"), str)
        or not payload["run_id"]
        or not isinstance(payload.get("turns"), list)
        or not payload["turns"]
        or not isinstance(final, dict)
        or payload.get("evaluation")
        != _evaluation_payload(final, prefix=prefix, profile=profile)
        or payload.get("surface_failure")
        != _value_at_path(
            raw_boundary,
            profile.raw_surface_failure_path,
        )
    ):
        raise ERPNextFormalBuildSpecError(
            f"{label} is not a complete recomputed execution control"
        )
    recorded_lock = payload.get("formal_input_lock")
    if not isinstance(recorded_lock, dict):
        raise ERPNextFormalBuildSpecError(
            f"{label} lacks a verified formal input lock"
        )
    expected_lock = verify_formal_input_lock(
        formal_input_lock_path,
        root=root,
        scenario_id=scenario.scenario_id,
        domain_id=scenario.domain_id,
        family_id=scenario.family_id,
        instance_id=scenario.instance_id,
        variant_id=variant_id,
        failure_report_path=raw_boundary_path,
        prefix_path=scenario.resolve_artifact("prefix"),
        trusted_producer_commit=trusted_producer_commit,
    ).as_dict()
    if recorded_lock != expected_lock:
        raise ERPNextFormalBuildSpecError(
            f"{label} formal input lock does not match the boundary"
        )
    return str(payload["run_id"])


def _validate_control_summary(
    payload: dict[str, Any],
    *,
    scenario: NativeScenario,
    trajectories: dict[str, dict[str, Any]],
    profile: ERPNextFormalBuildProfile = _SALES_RETURN_PROFILE,
) -> None:
    reports = payload.get("reports")
    counts = payload.get("execution_control_counts")
    if (
        not isinstance(reports, list)
        or len(reports) != len(profile.variants)
        or payload.get("completed_runs") != len(profile.variants)
        or payload.get("run_errors") != []
        or not isinstance(counts, dict)
        or counts.get("true") != len(profile.variants)
    ):
        raise ERPNextFormalBuildSpecError(
            "ERPNext execution-control summary is incomplete"
        )
    passed = sum(
        item.get("evaluation", {}).get("passed") is True
        for item in trajectories.values()
    )
    observed_rate = payload.get("task_pass_rate")
    if (
        not isinstance(observed_rate, (int, float))
        or abs(float(observed_rate) - passed / len(profile.variants))
        > 1e-12
        or observed_rate < MIN_EXECUTION_CONTROL_PASS_RATE
    ):
        raise ERPNextFormalBuildSpecError(
            "ERPNext execution-control pass rate is invalid or too low"
        )
    observed: set[str] = set()
    for report in reports:
        if not isinstance(report, dict):
            raise ERPNextFormalBuildSpecError(
                "ERPNext execution-control summary report is invalid"
            )
        variant_id = str(report.get("variant", ""))
        trajectory = trajectories.get(variant_id)
        if (
            variant_id not in scenario.variants
            or variant_id in observed
            or report.get("scenario_id") != scenario.scenario_id
            or trajectory is None
            or report.get("passed")
            is not trajectory.get("evaluation", {}).get("passed")
            or Path(str(report.get("path", ""))).name
            != f"{variant_id}.json"
        ):
            raise ERPNextFormalBuildSpecError(
                "ERPNext execution-control summary identity drifted"
            )
        observed.add(variant_id)
    if observed != set(scenario.variants):
        raise ERPNextFormalBuildSpecError(
            "ERPNext execution-control summary lacks full variant coverage"
        )


def _collect_variant_evidence(
    *,
    root: Path,
    scenario: NativeScenario,
    instance_spec_sha256: str,
    runtime_manifest: ExactFileManifest,
    control_manifest: ExactFileManifest | None,
    formal_input_lock_path: str | None,
    trusted_producer_commit: str,
    capture_directory: Path,
    bundle_manifests: dict[str, tuple[str, dict[str, Any]]],
    profile: ERPNextFormalBuildProfile = _SALES_RETURN_PROFILE,
) -> tuple[
    tuple[_VariantEvidence, ...],
    tuple[str, ...],
    dict[str, tuple[str, ...]],
]:
    prefix_path = scenario.resolve_artifact("prefix")
    prefix = strict_object(prefix_path, label="scenario prefix")
    prefix_sha256 = sha256_file(prefix_path)
    evidence: list[_VariantEvidence] = []
    evaluator_check_ids: tuple[str, ...] | None = None
    used_manifests = {"reset": set(), "boundary": set()}
    run_ids: set[str] = set()
    trajectories: dict[str, dict[str, Any]] = {}
    for variant_id in scenario.variants:
        reset_path, reset_relative = _repo_file(
            root,
            capture_directory / f"{variant_id}-reset.json",
            label=f"ERPNext reset capture {variant_id}",
        )
        boundary_path, boundary_relative = _repo_file(
            root,
            capture_directory / f"{variant_id}-boundary.json",
            label=f"ERPNext boundary capture {variant_id}",
        )
        reference_start_path, reference_start_relative = _repo_file(
            root,
            capture_directory / f"{variant_id}-reference-start.json",
            label=f"ERPNext reference-start capture {variant_id}",
        )
        raw_boundary_path = (
            runtime_manifest.root / "runtime" / f"{variant_id}-boundary.json"
        )
        raw_reference_path = (
            runtime_manifest.root / "runtime" / f"{variant_id}-reference.json"
        )
        for selected, label in (
            (raw_boundary_path, f"ERPNext raw boundary {variant_id}"),
            (raw_reference_path, f"ERPNext raw reference {variant_id}"),
            (
                reference_start_path,
                f"ERPNext reference-start capture {variant_id}",
            ),
        ):
            if not selected.is_file():
                raise ERPNextFormalBuildSpecError(f"{label} is missing")
            runtime_manifest.require_file(selected, label=label)
        reset = strict_object(
            reset_path,
            label=f"ERPNext reset capture {variant_id}",
        )
        boundary = strict_object(
            boundary_path,
            label=f"ERPNext boundary capture {variant_id}",
        )
        raw_boundary = strict_object(
            raw_boundary_path,
            label=f"ERPNext raw boundary {variant_id}",
        )
        raw_reference = strict_object(
            raw_reference_path,
            label=f"ERPNext raw reference {variant_id}",
        )
        reference_start = strict_object(
            reference_start_path,
            label=f"ERPNext reference-start capture {variant_id}",
        )
        reset_manifest = _validate_reset(
            reset,
            scenario=scenario,
            variant_id=variant_id,
            prefix_sha256=prefix_sha256,
            bundle_manifests=bundle_manifests,
            profile=profile,
        )
        boundary_manifest = _validate_boundary(
            boundary,
            path=boundary_path,
            reset_path=reset_path,
            raw_boundary_path=raw_boundary_path,
            raw_boundary=raw_boundary,
            scenario=scenario,
            variant_id=variant_id,
            prefix_sha256=prefix_sha256,
            bundle_manifests=bundle_manifests,
            profile=profile,
        )
        reference_start_manifest = _validate_boundary(
            reference_start,
            path=reference_start_path,
            reset_path=reset_path,
            raw_boundary_path=raw_boundary_path,
            raw_boundary=raw_boundary,
            scenario=scenario,
            variant_id=variant_id,
            prefix_sha256=prefix_sha256,
            bundle_manifests=bundle_manifests,
            profile=profile,
        )
        _validate_boundary_replay_equivalence(
            boundary,
            reference_start,
            variant_id=variant_id,
            profile=profile,
        )
        if reference_start_manifest != boundary_manifest:
            raise ERPNextFormalBuildSpecError(
                f"ERPNext reference-start capture {variant_id} changed "
                "the native snapshot bundle"
            )
        used_manifests["reset"].add(reset_manifest)
        used_manifests["boundary"].add(boundary_manifest)
        check_ids = _validate_reference(
            raw_reference,
            prefix=prefix,
            scenario=scenario,
            variant_id=variant_id,
            profile=profile,
        )
        if evaluator_check_ids is None:
            evaluator_check_ids = check_ids
        elif evaluator_check_ids != check_ids:
            raise ERPNextFormalBuildSpecError(
                "ERPNext references do not expose one evaluator check set"
            )

        trajectory_path: Path | None = None
        trajectory_relative: str | None = None
        trajectory: dict[str, Any] | None = None
        pre_model_path: Path | None = None
        pre_model_relative: str | None = None
        if control_manifest is not None:
            trajectory_path = (
                control_manifest.root
                / "model-runs"
                / "repetition-01"
                / f"{variant_id}.json"
            )
            pre_model_path = (
                control_manifest.root
                / "pre-model-boundaries"
                / f"{variant_id}-boundary.json"
            )
            for selected, label in (
                (
                    trajectory_path,
                    f"ERPNext execution-control trajectory {variant_id}",
                ),
                (
                    pre_model_path,
                    f"ERPNext pre-model boundary {variant_id}",
                ),
            ):
                if not selected.is_file():
                    raise ERPNextFormalBuildSpecError(f"{label} is missing")
                control_manifest.require_file(selected, label=label)
            pre_model = strict_object(
                pre_model_path,
                label=f"ERPNext pre-model boundary {variant_id}",
            )
            pre_model_manifest = _validate_boundary(
                pre_model,
                path=pre_model_path,
                reset_path=reset_path,
                raw_boundary_path=raw_boundary_path,
                raw_boundary=raw_boundary,
                scenario=scenario,
                variant_id=variant_id,
                prefix_sha256=prefix_sha256,
                bundle_manifests=bundle_manifests,
                profile=profile,
            )
            _validate_boundary_replay_equivalence(
                boundary,
                pre_model,
                variant_id=variant_id,
                profile=profile,
            )
            if pre_model_manifest != boundary_manifest:
                raise ERPNextFormalBuildSpecError(
                    f"ERPNext pre-model boundary {variant_id} changed "
                    "the native snapshot bundle"
                )
            trajectory_relative = trajectory_path.relative_to(root).as_posix()
            pre_model_relative = pre_model_path.relative_to(root).as_posix()
            trajectory = strict_object(
                trajectory_path,
                label=f"ERPNext execution-control trajectory {variant_id}",
            )
            pre_model_sha256 = sha256_file(pre_model_path)
            recorded = trajectory.get("pre_model_boundary_evidence")
            if (
                not isinstance(recorded, dict)
                or recorded.get("variant_id") != variant_id
                or recorded.get("source_basename") != pre_model_path.name
                or recorded.get("sha256") != pre_model_sha256
            ):
                raise ERPNextFormalBuildSpecError(
                    f"ERPNext trajectory {variant_id} does not bind its "
                    "persisted pre-model boundary"
                )
            if formal_input_lock_path is None:
                raise ERPNextFormalBuildSpecError(
                    "ERPNext completion requires a formal input lock"
                )
            run_id = _validate_control_trajectory(
                trajectory,
                root=root,
                prefix=prefix,
                scenario=scenario,
                instance_spec_sha256=instance_spec_sha256,
                variant_id=variant_id,
                formal_input_lock_path=formal_input_lock_path,
                trusted_producer_commit=trusted_producer_commit,
                raw_boundary_path=raw_boundary_path,
                raw_boundary=raw_boundary,
                profile=profile,
            )
            if run_id in run_ids:
                raise ERPNextFormalBuildSpecError(
                    "ERPNext execution-control run IDs must be unique"
                )
            run_ids.add(run_id)
            trajectories[variant_id] = trajectory
        evidence.append(
            _VariantEvidence(
                variant_id=variant_id,
                reset_path=reset_path,
                reset_relative=reset_relative,
                reset=reset,
                boundary_path=boundary_path,
                boundary_relative=boundary_relative,
                boundary=boundary,
                raw_boundary_path=raw_boundary_path,
                raw_boundary_relative=raw_boundary_path.relative_to(
                    root
                ).as_posix(),
                raw_boundary=raw_boundary,
                raw_reference_path=raw_reference_path,
                raw_reference_relative=raw_reference_path.relative_to(
                    root
                ).as_posix(),
                raw_reference=raw_reference,
                reference_start_path=reference_start_path,
                reference_start_relative=reference_start_relative,
                reference_start=reference_start,
                trajectory_path=trajectory_path,
                trajectory_relative=trajectory_relative,
                trajectory=trajectory,
                pre_model_boundary_path=pre_model_path,
                pre_model_boundary_relative=pre_model_relative,
            )
        )

    if control_manifest is not None:
        summary_path = control_manifest.root / "model-runs" / "summary.json"
        if not summary_path.is_file():
            raise ERPNextFormalBuildSpecError(
                "ERPNext execution-control summary is missing"
            )
        control_manifest.require_file(
            summary_path,
            label="ERPNext execution-control summary",
        )
        _validate_control_summary(
            strict_object(
                summary_path,
                label="ERPNext execution-control summary",
            ),
            scenario=scenario,
            trajectories=trajectories,
            profile=profile,
        )
    if evaluator_check_ids is None:
        raise ERPNextFormalBuildSpecError(
            "ERPNext evidence has no evaluator checks"
        )
    declared = {relative for relative, _ in bundle_manifests.values()}
    used = used_manifests["reset"] | used_manifests["boundary"]
    if used != declared:
        raise ERPNextFormalBuildSpecError(
            "ERPNext capture bundle inputs must all be used"
        )
    return (
        tuple(evidence),
        evaluator_check_ids,
        {
            phase: tuple(sorted(paths))
            for phase, paths in used_manifests.items()
        },
    )


def _tool_role(
    *,
    root: Path,
    output: str,
    runtime_revision: str,
    source_verification_relative: str,
    profile: ERPNextFormalBuildProfile = _SALES_RETURN_PROFILE,
) -> dict[str, Any]:
    _, definition = _repo_file(
        root,
        profile.tool_definition_source,
        label="ERPNext tool-definition source",
    )
    _, implementation = _repo_file(
        root,
        profile.tool_implementation_source,
        label="ERPNext tool-implementation source",
    )
    dependencies = tuple(
        _repo_file(
            root,
            path,
            label=f"ERPNext tool dependency {path}",
        )[1]
        for path in profile.tool_implementation_dependencies
    )
    runtime_sources = tuple(
        _repo_file(
            root,
            path,
            label=f"ERPNext runtime source {path}",
        )[1]
        for path in profile.native_runtime_contract_sources
    )
    tools = profile.tool_definitions
    if tuple(tool.name for tool in tools) != profile.environment_tool_names:
        raise ERPNextFormalBuildSpecError(
            "ERPNext public tool definitions and implementation disagree"
        )
    try:
        return build_tool_contract_role(
            output=output,
            sources=ToolContractSources(
                definition=FormalSource(
                    source_path=definition,
                    role_path=profile.tool_definition_role_path,
                ),
                implementation=FormalSource(
                    source_path=implementation,
                    role_path=profile.tool_implementation_role_path,
                ),
                implementation_dependencies=tuple(
                    FormalSource(
                        source_path=source,
                        role_path=(
                            f"sources/dependencies/{index:02d}-"
                            f"{Path(source).name}"
                        ),
                    )
                    for index, source in enumerate(
                        dependencies,
                        start=1,
                    )
                ),
                runtime_revision=runtime_revision,
                runtime_verification=FormalSource(
                    source_path=source_verification_relative,
                    role_path="native-runtime/source-verification.json",
                ),
                runtime_sources=tuple(
                    FormalSource(
                        source_path=source,
                        role_path=(
                            f"native-runtime/{index:02d}-"
                            f"{Path(source).name}"
                        ),
                    )
                    for index, source in enumerate(
                        runtime_sources,
                        start=1,
                    )
                ),
                tools=tuple(
                    PublicToolContract(
                        name=tool.name,
                        description=tool.description,
                        input_schema=tool.input_schema,
                        implementation_symbol=(
                            profile.tool_implementation_symbol
                        ),
                    )
                    for tool in tools
                ),
            ),
        )
    except NativeFormalSpecError as error:
        raise ERPNextFormalBuildSpecError(str(error)) from error


def _evaluator_role(
    *,
    root: Path,
    output: str,
    check_ids: tuple[str, ...],
    profile: ERPNextFormalBuildProfile = _SALES_RETURN_PROFILE,
) -> dict[str, Any]:
    _, source = _repo_file(
        root,
        profile.evaluator_source,
        label="ERPNext evaluator source",
    )
    try:
        return build_evaluator_role(
            output=output,
            sources=EvaluatorContractSources(
                implementation=FormalSource(
                    source_path=source,
                    role_path=profile.evaluator_role_path,
                ),
                implementation_symbol=profile.evaluator_symbol,
                check_ids=check_ids,
                scored_state_fields=profile.scored_state_fields,
            ),
        )
    except NativeFormalSpecError as error:
        raise ERPNextFormalBuildSpecError(str(error)) from error


def _input_roles(
    *,
    root: Path,
    scenario: NativeScenario,
    output: str,
    evidence: tuple[_VariantEvidence, ...],
    capture_usage: dict[str, tuple[str, ...]],
    runtime_manifest_relative: str,
    runtime_revision: str,
    source_verification_relative: str,
    profile: ERPNextFormalBuildProfile = _SALES_RETURN_PROFILE,
) -> dict[str, dict[str, Any]]:
    _, prefix_relative = _repo_file(
        root,
        scenario.resolve_artifact("prefix"),
        label="ERPNext scenario prefix",
    )
    boundary_sources = tuple(
        _repo_file(
            root,
            source,
            label=f"ERPNext boundary source {source}",
        )[1]
        for source in profile.boundary_contract_sources
    )
    try:
        return build_input_evidence_roles(
            output=output,
            sources=InputEvidenceSources(
                operation=scenario.raw["ambiguous_operation"]["operation"],
                prefix_source_path=prefix_relative,
                runtime_manifest_source_path=runtime_manifest_relative,
                runtime_revision=runtime_revision,
                boundary_verification_source_path=(
                    source_verification_relative
                ),
                boundary_contract_sources=tuple(
                    FormalSource(
                        source_path=source,
                        role_path=(
                            f"native-boundary/{index:02d}-"
                            f"{Path(source).name}"
                        ),
                    )
                    for index, source in enumerate(
                        boundary_sources,
                        start=1,
                    )
                ),
                reset_capture_manifest_sources=capture_usage["reset"],
                boundary_capture_manifest_sources=capture_usage[
                    "boundary"
                ],
                variants=tuple(
                    VariantInputEvidence(
                        variant_id=item.variant_id,
                        reset_source_path=item.reset_relative,
                        boundary_state_source_path=item.boundary_relative,
                        raw_failure_report_source_path=(
                            item.raw_boundary_relative
                        ),
                        reference_start_state_source_path=(
                            item.reference_start_relative
                        ),
                        raw_reference_report_source_path=(
                            item.raw_reference_relative
                        ),
                    )
                    for item in evidence
                ),
            ),
        )
    except NativeFormalSpecError as error:
        raise ERPNextFormalBuildSpecError(str(error)) from error


def _completion_roles(
    *,
    output: str,
    evidence: tuple[_VariantEvidence, ...],
    control_manifest_relative: str,
    model_input_lock_relative: str,
) -> dict[str, dict[str, Any]]:
    if any(
        item.trajectory is None
        or item.trajectory_relative is None
        or item.pre_model_boundary_relative is None
        for item in evidence
    ):
        raise ERPNextFormalBuildSpecError(
            "ERPNext complete phase requires every trajectory"
        )
    try:
        return build_completion_roles(
            output=output,
            input_variant_ids=tuple(
                item.variant_id for item in evidence
            ),
            sources=CompletionEvidenceSources(
                control_manifest_source_path=control_manifest_relative,
                model_input_lock_source_path=model_input_lock_relative,
                variants=tuple(
                    VariantCompletionEvidence(
                        variant_id=item.variant_id,
                        run_id=str((item.trajectory or {})["run_id"]),
                        trajectory_source_path=str(
                            item.trajectory_relative
                        ),
                        pre_model_boundary_source_path=str(
                            item.pre_model_boundary_relative
                        ),
                        passed=(
                            (item.trajectory or {})
                            .get("evaluation", {})
                            .get("passed")
                            is True
                        ),
                    )
                    for item in evidence
                ),
            ),
        )
    except NativeFormalSpecError as error:
        raise ERPNextFormalBuildSpecError(str(error)) from error


def generate_erpnext_formal_build_spec(
    *,
    root: str | Path,
    benchmark_release_id: str,
    output_directory: str,
    runtime_manifest_path: str | Path,
    capture_directory: str | Path,
    capture_bundle_manifest_paths: Iterable[str | Path],
    phase: str,
    scenario_path: str | Path | None = None,
    control_manifest_path: str | Path | None = None,
    model_input_lock_path: str | Path | None = None,
    profile: ERPNextFormalBuildProfile = _SALES_RETURN_PROFILE,
) -> ERPNextFormalBuildSpecResult:
    """Generate a strict seven-role spec from native ERPNext evidence."""

    resolved_root = Path(root).resolve()
    if not resolved_root.is_dir():
        raise ERPNextFormalBuildSpecError(
            "repository root must be an existing directory"
        )
    if phase not in {"inputs", "complete"}:
        raise ERPNextFormalBuildSpecError(
            "phase must be inputs or complete"
        )
    try:
        release_id = require_identifier(
            benchmark_release_id,
            label="benchmark_release_id",
        )
        output = validate_output_directory(
            resolved_root,
            output_directory,
        )
    except NativeFormalSourceError as error:
        raise _source_error(error) from error
    scenario, scenario_relative, instance_spec_sha256 = (
        _validate_active_scenario(
            resolved_root,
            scenario_path,
            profile=profile,
        )
    )
    if phase == "inputs":
        if (
            control_manifest_path is not None
            or model_input_lock_path is not None
        ):
            raise ERPNextFormalBuildSpecError(
                "inputs phase must not receive completion evidence"
            )
    elif (
        control_manifest_path is None
        or model_input_lock_path is None
    ):
        raise ERPNextFormalBuildSpecError(
            "complete phase requires control manifest and input lock"
        )

    runtime_manifest = _exact_manifest(
        resolved_root,
        runtime_manifest_path,
        label="ERPNext runtime exact bundle manifest",
    )
    runtime_revision, source_verification_relative = (
        _validate_runtime_contract(resolved_root, runtime_manifest)
    )
    capture_dir, _ = _repo_directory(
        resolved_root,
        capture_directory,
        label="ERPNext state capture directory",
    )
    capture_manifests = _load_bundle_manifests(
        resolved_root,
        capture_bundle_manifest_paths,
    )
    control_manifest: ExactFileManifest | None = None
    control_relative: str | None = None
    lock_relative: str | None = None
    if phase == "complete":
        assert control_manifest_path is not None
        assert model_input_lock_path is not None
        control_manifest = _exact_manifest(
            resolved_root,
            control_manifest_path,
            label="ERPNext control exact bundle manifest",
        )
        control_relative = control_manifest.relative_path
        lock_path, lock_relative = _repo_file(
            resolved_root,
            model_input_lock_path,
            label="ERPNext formal input lock",
        )
        if (
            lock_path
            != (resolved_root / output / "formal-input-lock.json").resolve()
        ):
            raise ERPNextFormalBuildSpecError(
                "complete phase input lock must be the frozen formal lock"
            )
    try:
        producer_commit = current_git_commit(resolved_root)
    except NativeFormalSourceError as error:
        raise _source_error(error) from error
    evidence, check_ids, capture_usage = _collect_variant_evidence(
        root=resolved_root,
        scenario=scenario,
        instance_spec_sha256=instance_spec_sha256,
        runtime_manifest=runtime_manifest,
        control_manifest=control_manifest,
        formal_input_lock_path=lock_relative,
        trusted_producer_commit=producer_commit,
        capture_directory=capture_dir,
        bundle_manifests=capture_manifests,
        profile=profile,
    )
    roles: dict[str, dict[str, Any]] = {
        "tool_contract": _tool_role(
            root=resolved_root,
            output=output,
            runtime_revision=runtime_revision,
            source_verification_relative=source_verification_relative,
            profile=profile,
        ),
        "evaluator": _evaluator_role(
            root=resolved_root,
            output=output,
            check_ids=check_ids,
            profile=profile,
        ),
        **_input_roles(
            root=resolved_root,
            scenario=scenario,
            output=output,
            evidence=evidence,
            capture_usage=capture_usage,
            runtime_manifest_relative=runtime_manifest.relative_path,
            runtime_revision=runtime_revision,
            source_verification_relative=source_verification_relative,
            profile=profile,
        ),
    }
    if phase == "inputs":
        roles.update(empty_completion_roles())
    else:
        assert control_relative is not None
        assert lock_relative is not None
        roles.update(
            _completion_roles(
                output=output,
                evidence=evidence,
                control_manifest_relative=control_relative,
                model_input_lock_relative=lock_relative,
            )
        )
    spec = {
        "schema_version": "1.0",
        "benchmark_release_id": release_id,
        "scenario_path": scenario_relative,
        "scenario_id": scenario.scenario_id,
        "domain_id": scenario.domain_id,
        "family_id": scenario.family_id,
        "instance_id": scenario.instance_id,
        "variant_ids": list(scenario.variants),
        "producer_commit": producer_commit,
        "output_directory": output,
        "roles": roles,
    }
    return ERPNextFormalBuildSpecResult(
        spec=spec,
        scenario_path=scenario_relative,
        runtime_manifest_path=runtime_manifest.relative_path,
        control_manifest_path=control_relative,
        capture_bundle_manifest_paths=tuple(
            sorted(relative for relative, _ in capture_manifests.values())
        ),
    )


def write_erpnext_formal_build_spec(
    path: str | Path,
    spec: dict[str, Any],
    *,
    root: str | Path,
) -> str:
    try:
        return write_formal_build_spec(path, spec, root=root)
    except NativeFormalSourceError as error:
        raise _source_error(error) from error


__all__ = [
    "ERPNextFormalBuildProfile",
    "ERPNextFormalBuildSpecError",
    "ERPNextFormalBuildSpecResult",
    "MULTIWAREHOUSE_FORMAL_PROFILE",
    "discover_active_erpnext_public_dev_scenario",
    "generate_erpnext_formal_build_spec",
    "write_erpnext_formal_build_spec",
]
