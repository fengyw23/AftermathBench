from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from .erpnext_formal_build_spec import (
    ERPNextFormalBuildProfile,
    ERPNextFormalBuildSpecError,
    ERPNextFormalBuildSpecResult,
    discover_active_erpnext_public_dev_scenario,
    generate_erpnext_formal_build_spec,
    write_erpnext_formal_build_spec,
)
from .erpnext_manufacturing_state_evidence import (
    manufacturing_boundary_projection,
)
from .integrations.erpnext_faults import ERP_NEXT_FAULT_VARIANTS
from .integrations.erpnext_manufacturing_agent import (
    ERPNextManufacturingEnvironment,
)
from .integrations.erpnext_manufacturing_evaluator import (
    evaluate_manufacturing_rework_recovery,
)
from .native_erpnext_manufacturing_family import ERP_NEXT_MANUFACTURING_TOOLS


MANUFACTURING_FORMAL_PROFILE = ERPNextFormalBuildProfile(
    family_id="erpnext-manufacturing-rework",
    variants=tuple(ERP_NEXT_FAULT_VARIANTS),
    state_evidence_artifact_type="erpnext_manufacturing_state_evidence",
    failure_boundary_artifact_type="erpnext_manufacturing_failure_boundary",
    reference_artifact_type="erpnext_manufacturing_reference_recovery",
    raw_boundary_state_field="boundary_evidence",
    accepted_failure_schema_versions=frozenset({"0.1", "1.0"}),
    accepted_reference_schema_versions=frozenset({"0.1", "1.0"}),
    tool_definition_source=(
        "src/aftermath_bench/native_erpnext_manufacturing_family.py"
    ),
    tool_implementation_source=(
        "src/aftermath_bench/integrations/erpnext_manufacturing_agent.py"
    ),
    tool_implementation_dependencies=(
        "src/aftermath_bench/integrations/erpnext_manufacturing_evidence.py",
        "src/aftermath_bench/integrations/erpnext_manufacturing_prefix.py",
        "src/aftermath_bench/integrations/erpnext_return_agent.py",
        "src/aftermath_bench/integrations/erpnext_return_evidence.py",
        "src/aftermath_bench/integrations/erpnext_return_prefix.py",
        "src/aftermath_bench/integrations/erpnext_faults.py",
        "src/aftermath_bench/integrations/erpnext_stack.py",
        "src/aftermath_bench/integrations/frappe.py",
    ),
    native_runtime_contract_sources=(
        "runtimes/erpnext/runtime.lock.json",
        "runtimes/erpnext/compose.yaml",
        "runtimes/erpnext/control/Containerfile",
        "runtimes/erpnext/bridge/aftermath_frappe_bridge.py",
        "runtimes/erpnext/patches/pin-python-base.patch",
        "runtimes/erpnext/patches/atomic-assets-link.patch",
        "scripts/build_erpnext_runtime.py",
        "scripts/manage_erpnext_stack.py",
        "scripts/run_erpnext_manufacturing_failure.py",
        "scripts/run_erpnext_manufacturing_control.py",
        "scripts/capture_erpnext_manufacturing_state_evidence.py",
        "src/aftermath_bench/integrations/erpnext_runtime.py",
        "src/aftermath_bench/integrations/erpnext_faults.py",
        "src/aftermath_bench/runtime_services/gateway.py",
        "src/aftermath_bench/runtime_services/remittance.py",
    ),
    boundary_contract_sources=(
        "scripts/run_erpnext_manufacturing_failure.py",
        "scripts/capture_erpnext_manufacturing_state_evidence.py",
        "src/aftermath_bench/erpnext_manufacturing_state_evidence.py",
        "src/aftermath_bench/integrations/erpnext_faults.py",
        "src/aftermath_bench/integrations/erpnext_manufacturing_evidence.py",
    ),
    evaluator_source=(
        "src/aftermath_bench/integrations/erpnext_manufacturing_evaluator.py"
    ),
    scored_state_fields=(
        "work_order",
        "corrective_job_card",
        "accepted_manufacture_stock_entry",
        "accepted_job_card",
        "bom",
        "unrelated_stock_entry",
        "job_cards",
        "manufacture_stock_entries",
        "quality_inspections",
        "stock_ledger_entries",
        "gl_entries",
        "rq_jobs",
        "quality_release_delivery",
    ),
    tool_definitions=tuple(ERP_NEXT_MANUFACTURING_TOOLS),
    environment_tool_names=tuple(ERPNextManufacturingEnvironment.TOOL_NAMES),
    tool_definition_role_path=(
        "sources/native_erpnext_manufacturing_family.py"
    ),
    tool_implementation_role_path=(
        "sources/erpnext_manufacturing_agent.py"
    ),
    tool_implementation_symbol="ERPNextManufacturingEnvironment.invoke",
    evaluator_role_path="sources/erpnext_manufacturing_evaluator.py",
    evaluator_symbol="evaluate_manufacturing_rework_recovery",
    evaluator=evaluate_manufacturing_rework_recovery,
    boundary_state_projection=manufacturing_boundary_projection,
)


def discover_active_erpnext_manufacturing_public_dev_scenario(
    root: str | Path,
) -> str:
    return discover_active_erpnext_public_dev_scenario(
        root,
        profile=MANUFACTURING_FORMAL_PROFILE,
    )


def generate_erpnext_manufacturing_formal_build_spec(
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
) -> ERPNextFormalBuildSpecResult:
    return generate_erpnext_formal_build_spec(
        root=root,
        benchmark_release_id=benchmark_release_id,
        output_directory=output_directory,
        runtime_manifest_path=runtime_manifest_path,
        capture_directory=capture_directory,
        capture_bundle_manifest_paths=capture_bundle_manifest_paths,
        phase=phase,
        scenario_path=scenario_path,
        control_manifest_path=control_manifest_path,
        model_input_lock_path=model_input_lock_path,
        profile=MANUFACTURING_FORMAL_PROFILE,
    )


def write_erpnext_manufacturing_formal_build_spec(
    path: str | Path,
    spec: dict,
    *,
    root: str | Path,
) -> str:
    return write_erpnext_formal_build_spec(path, spec, root=root)


__all__ = [
    "ERPNextFormalBuildSpecError",
    "ERPNextFormalBuildSpecResult",
    "MANUFACTURING_FORMAL_PROFILE",
    "discover_active_erpnext_manufacturing_public_dev_scenario",
    "generate_erpnext_manufacturing_formal_build_spec",
    "write_erpnext_manufacturing_formal_build_spec",
]
