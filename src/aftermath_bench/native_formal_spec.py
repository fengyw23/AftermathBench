from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any


class NativeFormalSpecError(ValueError):
    """Raised when normalized native evidence cannot define formal roles."""


@dataclass(frozen=True)
class FormalSource:
    """A repository source and its relative destination inside one role."""

    source_path: str
    role_path: str


@dataclass(frozen=True)
class PublicToolContract:
    name: str
    description: str
    input_schema: dict[str, Any]
    implementation_symbol: str


@dataclass(frozen=True)
class ToolContractSources:
    definition: FormalSource
    implementation: FormalSource
    implementation_dependencies: tuple[FormalSource, ...]
    runtime_revision: str
    runtime_verification: FormalSource
    runtime_sources: tuple[FormalSource, ...]
    tools: tuple[PublicToolContract, ...]


@dataclass(frozen=True)
class EvaluatorContractSources:
    implementation: FormalSource
    implementation_symbol: str
    check_ids: tuple[str, ...]
    scored_state_fields: tuple[str, ...]


@dataclass(frozen=True)
class VariantInputEvidence:
    variant_id: str
    reset_source_path: str
    boundary_state_source_path: str
    raw_failure_report_source_path: str
    reference_start_state_source_path: str
    raw_reference_report_source_path: str


@dataclass(frozen=True)
class InputEvidenceSources:
    operation: str
    prefix_source_path: str
    runtime_manifest_source_path: str
    runtime_revision: str
    boundary_verification_source_path: str
    boundary_contract_sources: tuple[FormalSource, ...]
    reset_capture_manifest_sources: tuple[str, ...]
    boundary_capture_manifest_sources: tuple[str, ...]
    variants: tuple[VariantInputEvidence, ...]


@dataclass(frozen=True)
class VariantCompletionEvidence:
    variant_id: str
    run_id: str
    trajectory_source_path: str
    pre_model_boundary_source_path: str
    passed: bool


@dataclass(frozen=True)
class CompletionEvidenceSources:
    control_manifest_source_path: str
    model_input_lock_source_path: str
    variants: tuple[VariantCompletionEvidence, ...]


def role_root(output: str, role: str) -> str:
    if role in {
        "tool_contract",
        "evaluator",
        "reset_evidence",
        "boundary_bundle",
        "reference_bundle",
    }:
        return f"{output}/roles/{role}"
    if role in {"raw_run_archive", "execution_control"}:
        return f"{output}/completion/roles/{role}"
    raise NativeFormalSpecError(f"unknown formal role {role}")


def support_path(output: str, role: str, name: str) -> str:
    _canonical_relative(name, label=f"{role} support path")
    return f"{role_root(output, role)}/support/{name}"


def file_sha256(path: str) -> dict[str, str]:
    return {"$file_sha256": path}


def envelope_sha256(role: str) -> dict[str, str]:
    return {"$envelope_sha256": role}


def role_dependencies(role: str) -> dict[str, str]:
    return {"$role_dependencies": role}


def identity(field: str) -> dict[str, str]:
    return {"$identity": field}


def bound_json_field(path: str, field: str) -> dict[str, dict[str, str]]:
    return {"$bound_json_field": {"path": path, "field": field}}


def formal_input_lock_sha256() -> dict[str, bool]:
    return {"$formal_input_lock_sha256": True}


def source_support(path: str, source_path: str) -> dict[str, str]:
    _canonical_relative(path, label="formal support destination")
    _canonical_relative(source_path, label="formal support source")
    return {"path": path, "source_path": source_path}


def json_support(path: str, value: Any) -> dict[str, Any]:
    _canonical_relative(path, label="formal JSON support destination")
    return {"path": path, "json_content": value}


def _canonical_relative(value: str, *, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise NativeFormalSpecError(f"{label} must be non-empty")
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or ".." in path.parts
        or path.as_posix() != value
        or value.endswith("/")
    ):
        raise NativeFormalSpecError(
            f"{label} must be a canonical relative POSIX path"
        )
    return value


def _validate_output(output: str) -> None:
    _canonical_relative(output, label="formal output directory")
    if PurePosixPath(output).parts[0] != "data":
        raise NativeFormalSpecError("formal output directory must be below data/")


def _variant_tokens(variant_ids: tuple[str, ...]) -> dict[str, str]:
    if not variant_ids or len(variant_ids) != len(set(variant_ids)):
        raise NativeFormalSpecError(
            "formal evidence variants must be non-empty and unique"
        )
    for variant_id in variant_ids:
        if not isinstance(variant_id, str) or not variant_id:
            raise NativeFormalSpecError("formal variant ids must be non-empty")
    return {
        variant_id: f"v{index:02d}"
        for index, variant_id in enumerate(variant_ids, start=1)
    }


def build_tool_contract_role(
    *,
    output: str,
    sources: ToolContractSources,
) -> dict[str, Any]:
    _validate_output(output)
    if not sources.runtime_revision:
        raise NativeFormalSpecError("native runtime revision must be non-empty")
    tools = sources.tools
    names = tuple(tool.name for tool in tools)
    if not tools or len(names) != len(set(names)):
        raise NativeFormalSpecError(
            "public formal tools must be non-empty and uniquely named"
        )
    definition_output = support_path(
        output,
        "tool_contract",
        sources.definition.role_path,
    )
    implementation_output = support_path(
        output,
        "tool_contract",
        sources.implementation.role_path,
    )
    dependency_outputs = {
        item.source_path: support_path(
            output,
            "tool_contract",
            item.role_path,
        )
        for item in sources.implementation_dependencies
    }
    if len(dependency_outputs) != len(sources.implementation_dependencies):
        raise NativeFormalSpecError(
            "tool implementation dependencies must have unique sources"
        )
    runtime_outputs = {
        item.source_path: support_path(
            output,
            "tool_contract",
            item.role_path,
        )
        for item in sources.runtime_sources
    }
    if len(runtime_outputs) != len(sources.runtime_sources):
        raise NativeFormalSpecError("runtime sources must have unique paths")
    verification_output = support_path(
        output,
        "tool_contract",
        sources.runtime_verification.role_path,
    )
    schema_outputs = {
        tool.name: support_path(
            output,
            "tool_contract",
            f"schemas/{tool.name}.json",
        )
        for tool in tools
    }
    dependencies = [
        {
            "path": dependency_outputs[item.source_path],
            "sha256": file_sha256(dependency_outputs[item.source_path]),
        }
        for item in sources.implementation_dependencies
    ]
    return {
        "primary_payload": {
            "tool_count": len(tools),
            "definition_source_path": definition_output,
            "definition_source_sha256": file_sha256(definition_output),
            "implementation_dependencies": dependencies,
            "native_runtime_contract": {
                "revision": sources.runtime_revision,
                "source_verification_path": verification_output,
                "source_verification_sha256": file_sha256(
                    verification_output
                ),
                "files": [
                    {
                        "source_path": item.source_path,
                        "path": runtime_outputs[item.source_path],
                        "sha256": file_sha256(
                            runtime_outputs[item.source_path]
                        ),
                    }
                    for item in sources.runtime_sources
                ],
            },
            "tools": [
                {
                    "name": tool.name,
                    "description": tool.description,
                    "input_schema_path": schema_outputs[tool.name],
                    "input_schema_sha256": file_sha256(
                        schema_outputs[tool.name]
                    ),
                    "definition_source_path": definition_output,
                    "definition_source_sha256": file_sha256(
                        definition_output
                    ),
                    "implementation_path": implementation_output,
                    "implementation_sha256": file_sha256(
                        implementation_output
                    ),
                    "implementation_symbol": tool.implementation_symbol,
                    "implementation_dependencies": dependencies,
                }
                for tool in tools
            ],
        },
        "support_files": [
            source_support(
                definition_output,
                sources.definition.source_path,
            ),
            source_support(
                implementation_output,
                sources.implementation.source_path,
            ),
            *[
                source_support(
                    dependency_outputs[item.source_path],
                    item.source_path,
                )
                for item in sources.implementation_dependencies
            ],
            source_support(
                verification_output,
                sources.runtime_verification.source_path,
            ),
            *[
                source_support(
                    runtime_outputs[item.source_path],
                    item.source_path,
                )
                for item in sources.runtime_sources
            ],
            *[
                json_support(
                    schema_outputs[tool.name],
                    tool.input_schema,
                )
                for tool in tools
            ],
        ],
    }


def build_evaluator_role(
    *,
    output: str,
    sources: EvaluatorContractSources,
) -> dict[str, Any]:
    _validate_output(output)
    if not sources.check_ids or len(sources.check_ids) != len(
        set(sources.check_ids)
    ):
        raise NativeFormalSpecError(
            "formal evaluator checks must be non-empty and unique"
        )
    implementation_output = support_path(
        output,
        "evaluator",
        sources.implementation.role_path,
    )
    return {
        "primary_payload": {
            "implementation_symbol": sources.implementation_symbol,
            "checks": [
                {
                    "id": check_id,
                    "implementation_path": implementation_output,
                    "implementation_sha256": file_sha256(
                        implementation_output
                    ),
                }
                for check_id in sources.check_ids
            ],
            "scored_state_fields": list(sources.scored_state_fields),
        },
        "support_files": [
            source_support(
                implementation_output,
                sources.implementation.source_path,
            )
        ],
    }


def _manifest_supports(
    *,
    output: str,
    role: str,
    source_paths: tuple[str, ...],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    declarations: list[dict[str, Any]] = []
    supports: list[dict[str, Any]] = []
    if len(source_paths) != len(set(source_paths)):
        raise NativeFormalSpecError(
            f"{role} exact bundle manifest sources must be unique"
        )
    for index, source in enumerate(source_paths, start=1):
        destination = support_path(
            output,
            role,
            f"capture-bundles/bundle-{index:02d}.json",
        )
        declarations.append(
            {
                "path": destination,
                "sha256": file_sha256(destination),
            }
        )
        supports.append(source_support(destination, source))
    return declarations, supports


def build_input_evidence_roles(
    *,
    output: str,
    sources: InputEvidenceSources,
) -> dict[str, dict[str, Any]]:
    _validate_output(output)
    if not sources.operation:
        raise NativeFormalSpecError(
            "ambiguous native operation must be non-empty"
        )
    tokens = _variant_tokens(
        tuple(item.variant_id for item in sources.variants)
    )
    prefix_output = support_path(
        output,
        "reset_evidence",
        "common/prefix.json",
    )
    reset_manifest_declarations, reset_manifest_supports = _manifest_supports(
        output=output,
        role="reset_evidence",
        source_paths=sources.reset_capture_manifest_sources,
    )
    boundary_manifest_declarations, boundary_manifest_supports = (
        _manifest_supports(
            output=output,
            role="boundary_bundle",
            source_paths=sources.boundary_capture_manifest_sources,
        )
    )
    reset_outputs = {
        item.variant_id: support_path(
            output,
            "reset_evidence",
            f"variants/{tokens[item.variant_id]}-reset.json",
        )
        for item in sources.variants
    }
    boundary_outputs = {
        item.variant_id: support_path(
            output,
            "boundary_bundle",
            f"variants/{tokens[item.variant_id]}-boundary.json",
        )
        for item in sources.variants
    }
    failure_outputs = {
        item.variant_id: support_path(
            output,
            "boundary_bundle",
            f"failure-surfaces/{tokens[item.variant_id]}.json",
        )
        for item in sources.variants
    }
    raw_boundary_outputs = {
        item.variant_id: support_path(
            output,
            "boundary_bundle",
            f"raw/{tokens[item.variant_id]}-boundary.json",
        )
        for item in sources.variants
    }
    runtime_manifest_output = support_path(
        output,
        "boundary_bundle",
        "source-bundles/runtime-files.json",
    )
    boundary_verification_output = support_path(
        output,
        "boundary_bundle",
        "native-boundary/source-verification.json",
    )
    boundary_source_outputs = {
        item.source_path: support_path(
            output,
            "boundary_bundle",
            item.role_path,
        )
        for item in sources.boundary_contract_sources
    }
    if len(boundary_source_outputs) != len(sources.boundary_contract_sources):
        raise NativeFormalSpecError(
            "boundary contract sources must have unique paths"
        )
    raw_reference_outputs = {
        item.variant_id: support_path(
            output,
            "reference_bundle",
            f"raw/{tokens[item.variant_id]}-reference.json",
        )
        for item in sources.variants
    }
    reference_start_outputs = {
        item.variant_id: support_path(
            output,
            "reference_bundle",
            f"start-states/{tokens[item.variant_id]}.json",
        )
        for item in sources.variants
    }
    trace_outputs = {
        item.variant_id: support_path(
            output,
            "reference_bundle",
            f"traces/{tokens[item.variant_id]}.json",
        )
        for item in sources.variants
    }
    terminal_outputs = {
        item.variant_id: support_path(
            output,
            "reference_bundle",
            f"terminal/{tokens[item.variant_id]}.json",
        )
        for item in sources.variants
    }
    reset_role = {
        "primary_payload": {
            "prefix_path": prefix_output,
            "prefix_sha256": file_sha256(prefix_output),
            "exact_bundle_manifests": reset_manifest_declarations,
            "variants": [
                {
                    "variant_id": item.variant_id,
                    "reset_snapshot_path": reset_outputs[item.variant_id],
                    "reset_snapshot_sha256": file_sha256(
                        reset_outputs[item.variant_id]
                    ),
                    "reset_verified": True,
                }
                for item in sources.variants
            ],
        },
        "support_files": [
            source_support(prefix_output, sources.prefix_source_path),
            *reset_manifest_supports,
            *[
                source_support(
                    reset_outputs[item.variant_id],
                    item.reset_source_path,
                )
                for item in sources.variants
            ],
        ],
    }
    boundary_role = {
        "primary_payload": {
            "operation": sources.operation,
            "runtime_bundle_manifest_path": runtime_manifest_output,
            "runtime_bundle_manifest_sha256": file_sha256(
                runtime_manifest_output
            ),
            "failure_injection_contract": {
                "runtime_revision": sources.runtime_revision,
                "source_verification_path": boundary_verification_output,
                "source_verification_sha256": file_sha256(
                    boundary_verification_output
                ),
                "files": [
                    {
                        "source_path": item.source_path,
                        "path": boundary_source_outputs[item.source_path],
                        "sha256": file_sha256(
                            boundary_source_outputs[item.source_path]
                        ),
                    }
                    for item in sources.boundary_contract_sources
                ],
            },
            "exact_bundle_manifests": boundary_manifest_declarations,
            "variants": [
                {
                    "variant_id": item.variant_id,
                    "boundary_state_path": boundary_outputs[item.variant_id],
                    "boundary_state_sha256": file_sha256(
                        boundary_outputs[item.variant_id]
                    ),
                    "failure_surface_path": failure_outputs[item.variant_id],
                    "failure_surface_sha256": file_sha256(
                        failure_outputs[item.variant_id]
                    ),
                    "raw_failure_report_path": (
                        raw_boundary_outputs[item.variant_id]
                    ),
                    "raw_failure_report_sha256": file_sha256(
                        raw_boundary_outputs[item.variant_id]
                    ),
                    "reset_snapshot_sha256": file_sha256(
                        reset_outputs[item.variant_id]
                    ),
                    "boundary_validation_passed": True,
                }
                for item in sources.variants
            ],
        },
        "support_files": [
            source_support(
                runtime_manifest_output,
                sources.runtime_manifest_source_path,
            ),
            source_support(
                boundary_verification_output,
                sources.boundary_verification_source_path,
            ),
            *[
                source_support(
                    boundary_source_outputs[item.source_path],
                    item.source_path,
                )
                for item in sources.boundary_contract_sources
            ],
            *boundary_manifest_supports,
            *[
                source_support(
                    boundary_outputs[item.variant_id],
                    item.boundary_state_source_path,
                )
                for item in sources.variants
            ],
            *[
                source_support(
                    raw_boundary_outputs[item.variant_id],
                    item.raw_failure_report_source_path,
                )
                for item in sources.variants
            ],
            *[
                json_support(
                    failure_outputs[item.variant_id],
                    {
                        "scenario_id": identity("scenario_id"),
                        "variant_id": item.variant_id,
                        "phase": "failure_surface",
                        "operation": sources.operation,
                        "surface_result": bound_json_field(
                            boundary_outputs[item.variant_id],
                            "surface_result",
                        ),
                        "visible_failure": bound_json_field(
                            boundary_outputs[item.variant_id],
                            "visible_failure",
                        ),
                        "raw_failure_report_sha256": file_sha256(
                            raw_boundary_outputs[item.variant_id]
                        ),
                    },
                )
                for item in sources.variants
            ],
        ],
    }
    reference_role = {
        "primary_payload": {
            "variants": [
                {
                    "variant_id": item.variant_id,
                    "boundary_state_sha256": file_sha256(
                        boundary_outputs[item.variant_id]
                    ),
                    "raw_reference_report_path": (
                        raw_reference_outputs[item.variant_id]
                    ),
                    "raw_reference_report_sha256": file_sha256(
                        raw_reference_outputs[item.variant_id]
                    ),
                    "reference_start_state_path": (
                        reference_start_outputs[item.variant_id]
                    ),
                    "reference_start_state_sha256": file_sha256(
                        reference_start_outputs[item.variant_id]
                    ),
                    "reference_trace_path": trace_outputs[item.variant_id],
                    "reference_trace_sha256": file_sha256(
                        trace_outputs[item.variant_id]
                    ),
                    "terminal_state_path": terminal_outputs[item.variant_id],
                    "terminal_state_sha256": file_sha256(
                        terminal_outputs[item.variant_id]
                    ),
                    "evaluator_passed": True,
                }
                for item in sources.variants
            ]
        },
        "support_files": [
            *[
                source_support(
                    reference_start_outputs[item.variant_id],
                    item.reference_start_state_source_path,
                )
                for item in sources.variants
            ],
            *[
                source_support(
                    raw_reference_outputs[item.variant_id],
                    item.raw_reference_report_source_path,
                )
                for item in sources.variants
            ],
            *[
                json_support(
                    trace_outputs[item.variant_id],
                    {
                        "scenario_id": identity("scenario_id"),
                        "variant_id": item.variant_id,
                        "phase": "reference_trace",
                        "boundary_state_sha256": file_sha256(
                            boundary_outputs[item.variant_id]
                        ),
                        "input_envelope_sha256": role_dependencies(
                            "reference_bundle"
                        ),
                        "raw_reference_report_sha256": file_sha256(
                            raw_reference_outputs[item.variant_id]
                        ),
                        "steps": bound_json_field(
                            raw_reference_outputs[item.variant_id],
                            "reference_trace",
                        ),
                    },
                )
                for item in sources.variants
            ],
            *[
                json_support(
                    terminal_outputs[item.variant_id],
                    {
                        "scenario_id": identity("scenario_id"),
                        "variant_id": item.variant_id,
                        "phase": "terminal",
                        "boundary_state_sha256": file_sha256(
                            boundary_outputs[item.variant_id]
                        ),
                        "evaluator_envelope_sha256": envelope_sha256(
                            "evaluator"
                        ),
                        "raw_reference_report_sha256": file_sha256(
                            raw_reference_outputs[item.variant_id]
                        ),
                        "evaluation": bound_json_field(
                            raw_reference_outputs[item.variant_id],
                            "evaluation",
                        ),
                        "final_evidence": bound_json_field(
                            raw_reference_outputs[item.variant_id],
                            "final_evidence",
                        ),
                        "status": "complete",
                    },
                )
                for item in sources.variants
            ],
        ],
    }
    return {
        "reset_evidence": reset_role,
        "boundary_bundle": boundary_role,
        "reference_bundle": reference_role,
    }


def empty_completion_roles() -> dict[str, dict[str, Any]]:
    return {
        "raw_run_archive": {
            "primary_payload": {},
            "support_files": [],
        },
        "execution_control": {
            "primary_payload": {},
            "support_files": [],
        },
    }


def build_completion_roles(
    *,
    output: str,
    input_variant_ids: tuple[str, ...],
    sources: CompletionEvidenceSources,
) -> dict[str, dict[str, Any]]:
    _validate_output(output)
    tokens = _variant_tokens(input_variant_ids)
    completion_ids = tuple(item.variant_id for item in sources.variants)
    if completion_ids != input_variant_ids:
        raise NativeFormalSpecError(
            "completion variants must exactly match input variants in order"
        )
    run_ids = tuple(item.run_id for item in sources.variants)
    if any(not run_id for run_id in run_ids) or len(run_ids) != len(
        set(run_ids)
    ):
        raise NativeFormalSpecError(
            "completion run ids must be non-empty and unique"
        )
    boundary_outputs = {
        variant_id: support_path(
            output,
            "boundary_bundle",
            f"variants/{tokens[variant_id]}-boundary.json",
        )
        for variant_id in input_variant_ids
    }
    lock_output = support_path(
        output,
        "raw_run_archive",
        "formal-input-lock.json",
    )
    control_manifest_output = support_path(
        output,
        "raw_run_archive",
        "source-bundles/control-files.json",
    )
    raw_outputs = {
        item.variant_id: support_path(
            output,
            "raw_run_archive",
            f"trajectories/{tokens[item.variant_id]}.json",
        )
        for item in sources.variants
    }
    pre_model_outputs = {
        item.variant_id: support_path(
            output,
            "raw_run_archive",
            f"pre-model-boundaries/{tokens[item.variant_id]}.json",
        )
        for item in sources.variants
    }
    run_outputs = {
        item.variant_id: support_path(
            output,
            "raw_run_archive",
            f"run-records/{tokens[item.variant_id]}.json",
        )
        for item in sources.variants
    }
    summary_output = support_path(
        output,
        "execution_control",
        "summary.json",
    )
    passed_runs = sum(item.passed for item in sources.variants)
    task_pass_rate = passed_runs / len(sources.variants)
    raw_role = {
        "primary_payload": {
            "formal_input_lock_path": lock_output,
            "formal_input_lock_sha256": file_sha256(lock_output),
            "control_bundle_manifest_path": control_manifest_output,
            "control_bundle_manifest_sha256": file_sha256(
                control_manifest_output
            ),
            "runs": [
                {
                    "run_id": item.run_id,
                    "variant_id": item.variant_id,
                    "run_path": run_outputs[item.variant_id],
                    "run_sha256": file_sha256(
                        run_outputs[item.variant_id]
                    ),
                    "raw_trajectory_path": raw_outputs[item.variant_id],
                    "raw_trajectory_sha256": file_sha256(
                        raw_outputs[item.variant_id]
                    ),
                    "pre_model_boundary_evidence_path": (
                        pre_model_outputs[item.variant_id]
                    ),
                    "pre_model_boundary_evidence_sha256": file_sha256(
                        pre_model_outputs[item.variant_id]
                    ),
                    "summary_report_path": raw_outputs[item.variant_id],
                    "boundary_state_sha256": file_sha256(
                        boundary_outputs[item.variant_id]
                    ),
                    "formal_input_lock_sha256": formal_input_lock_sha256(),
                    "execution_control": True,
                    "passed": item.passed,
                }
                for item in sources.variants
            ],
        },
        "support_files": [
            source_support(
                lock_output,
                sources.model_input_lock_source_path,
            ),
            source_support(
                control_manifest_output,
                sources.control_manifest_source_path,
            ),
            *[
                source_support(
                    raw_outputs[item.variant_id],
                    item.trajectory_source_path,
                )
                for item in sources.variants
            ],
            *[
                source_support(
                    pre_model_outputs[item.variant_id],
                    item.pre_model_boundary_source_path,
                )
                for item in sources.variants
            ],
            *[
                json_support(
                    run_outputs[item.variant_id],
                    {
                        "scenario_id": identity("scenario_id"),
                        "variant_id": item.variant_id,
                        "run_id": item.run_id,
                        "boundary_state_sha256": file_sha256(
                            boundary_outputs[item.variant_id]
                        ),
                        "input_envelope_sha256": role_dependencies(
                            "raw_run_archive"
                        ),
                        "formal_input_lock_sha256": (
                            formal_input_lock_sha256()
                        ),
                        "raw_trajectory_path": raw_outputs[item.variant_id],
                        "raw_trajectory_sha256": file_sha256(
                            raw_outputs[item.variant_id]
                        ),
                        "pre_model_boundary_evidence_path": (
                            pre_model_outputs[item.variant_id]
                        ),
                        "pre_model_boundary_evidence_sha256": file_sha256(
                            pre_model_outputs[item.variant_id]
                        ),
                        "summary_report_path": raw_outputs[item.variant_id],
                        "execution_control": True,
                        "passed": item.passed,
                    },
                )
                for item in sources.variants
            ],
        ],
    }
    summary = {
        "schema_version": "1.0",
        "completed_runs": len(sources.variants),
        "run_errors": [],
        "task_pass_rate": task_pass_rate,
        "execution_control_counts": {"true": len(sources.variants)},
        "reports": [
            {
                "scenario_id": identity("scenario_id"),
                "variant": item.variant_id,
                "passed": item.passed,
                "path": raw_outputs[item.variant_id],
            }
            for item in sources.variants
        ],
    }
    control_role = {
        "primary_payload": {
            "formal_input_lock_sha256": formal_input_lock_sha256(),
            "run_ids": [item.run_id for item in sources.variants],
            "completed_runs": len(sources.variants),
            "passed_runs": passed_runs,
            "task_pass_rate": task_pass_rate,
            "control_summary_path": summary_output,
            "control_summary_sha256": file_sha256(summary_output),
        },
        "support_files": [
            json_support(summary_output, summary),
        ],
    }
    return {
        "raw_run_archive": raw_role,
        "execution_control": control_role,
    }


__all__ = [
    "CompletionEvidenceSources",
    "EvaluatorContractSources",
    "FormalSource",
    "InputEvidenceSources",
    "NativeFormalSpecError",
    "PublicToolContract",
    "ToolContractSources",
    "VariantCompletionEvidence",
    "VariantInputEvidence",
    "bound_json_field",
    "build_completion_roles",
    "build_evaluator_role",
    "build_input_evidence_roles",
    "build_tool_contract_role",
    "empty_completion_roles",
    "envelope_sha256",
    "file_sha256",
    "formal_input_lock_sha256",
    "identity",
    "json_support",
    "role_dependencies",
    "role_root",
    "source_support",
    "support_path",
]
