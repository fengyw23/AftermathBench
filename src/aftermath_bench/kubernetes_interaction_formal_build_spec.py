from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .core import canonical_fingerprint
from .formal_evidence_builder import verify_formal_input_lock
from .integrations.kubernetes_interaction_instance import (
    KubernetesInteractionInstanceSpec,
)
from .integrations.kubernetes_interaction_recovery import (
    KubernetesInteractionEnvironment,
    evaluate_kubernetes_interaction_recovery,
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
from .native_kubernetes_migration_family import (
    KUBERNETES_MIGRATION_TOOL_DEFINITIONS,
)
from .native_scenario import (
    NativeScenario,
    load_native_scenario,
    validate_native_scenario_document,
)

_DOMAIN_ID = "kubernetes"
_FAMILY_ID = "k8s-constraint-interaction-recovery"
_RUNTIME_ID = "kubernetes-v1.34"
_SPLIT = "public_dev"
_TIER = "hard"
_ADMISSION_STATUS = "validated"
_VARIANTS = tuple(f"state_{index:02d}" for index in range(1, 14))
_MIN_CONTROL_PASS_RATE = 0.8
_INSTANCE_SPEC = "data/instance_specs/public-dev-slot-003.json"
_RUNTIME_SOURCE_VERIFICATION = "runtime/source-verification.json"

_TOOL_DEFINITION_SOURCE = "src/aftermath_bench/native_kubernetes_migration_family.py"
_TOOL_IMPLEMENTATION_SOURCE = (
    "src/aftermath_bench/integrations/kubernetes_interaction_recovery.py"
)
_TOOL_DEPENDENCIES = (
    "src/aftermath_bench/native_kubernetes_interaction_family.py",
    "src/aftermath_bench/native_model_runner.py",
    "src/aftermath_bench/integrations/kubernetes_migration_recovery.py",
    "src/aftermath_bench/integrations/kubernetes_api.py",
    "src/aftermath_bench/native_kubernetes_settlement_family.py",
    "src/aftermath_bench/model_runner.py",
)
_RUNTIME_CONTRACT_SOURCES = (
    "data/runtimes/kubernetes-v1.34/runtime.json",
    "data/runtimes/kubernetes-v1.34/source_audit.json",
    "data/runtimes/kubernetes-v1.34/migration_tool_provenance.json",
    "src/aftermath_bench/integrations/kubernetes_stack.py",
    "scripts/manage_kubernetes_stack.py",
    "src/aftermath_bench/runtime_services/webhook_sink.py",
)
_BOUNDARY_CONTRACT_SOURCES = (
    "scripts/run_kubernetes_interaction_boundary.py",
    "scripts/capture_kubernetes_interaction_state_evidence.py",
    "src/aftermath_bench/integrations/kubernetes_interaction_evidence.py",
    "src/aftermath_bench/integrations/kubernetes_interaction_faults.py",
    "src/aftermath_bench/integrations/kubernetes_interaction_prefix.py",
    "src/aftermath_bench/integrations/kubernetes_interaction_instance.py",
    "src/aftermath_bench/integrations/kubernetes_interaction_scope.py",
    "src/aftermath_bench/integrations/kubernetes_stack.py",
)
_EVALUATOR_SOURCE = (
    "src/aftermath_bench/integrations/kubernetes_interaction_recovery.py"
)
_SCORED_STATE_FIELDS = (
    "configmaps",
    "deployments",
    "services",
    "secrets",
    "serviceaccounts",
    "roles",
    "rolebindings",
    "jobs",
    "external_deliveries",
    "protocol_violations",
    "boundary_facts",
)


class KubernetesInteractionFormalBuildSpecError(ValueError):
    """Raised when Kubernetes evidence cannot support a formal package."""


@dataclass(frozen=True)
class _VariantEvidence:
    variant_id: str
    reset_path: Path
    reset_relative: str
    boundary_path: Path
    boundary_relative: str
    raw_boundary_path: Path
    raw_boundary_relative: str
    raw_reference_path: Path
    raw_reference_relative: str
    reference_start_path: Path
    reference_start_relative: str
    trajectory_path: Path | None
    trajectory_relative: str | None
    trajectory: dict[str, Any] | None
    pre_model_boundary_path: Path | None
    pre_model_boundary_relative: str | None


@dataclass(frozen=True)
class KubernetesInteractionFormalBuildSpecResult:
    spec: dict[str, Any]
    scenario_path: str
    runtime_manifest_path: str
    control_manifest_path: str | None
    capture_bundle_manifest_paths: tuple[str, ...]


def _error(error: Exception | str) -> KubernetesInteractionFormalBuildSpecError:
    return KubernetesInteractionFormalBuildSpecError(str(error))


def _repo_file(
    root: Path,
    value: str | Path,
    *,
    label: str,
) -> tuple[Path, str]:
    try:
        return repository_file(root, value, label=label)
    except NativeFormalSourceError as error:
        raise _error(error) from error


def _repo_directory(
    root: Path,
    value: str | Path,
    *,
    label: str,
) -> tuple[Path, str]:
    try:
        return repository_directory(root, value, label=label)
    except NativeFormalSourceError as error:
        raise _error(error) from error


def _exact_manifest(
    root: Path,
    value: str | Path,
    *,
    label: str,
) -> ExactFileManifest:
    try:
        return load_exact_file_manifest(root, value, label=label)
    except NativeFormalSourceError as error:
        raise _error(error) from error


def _json_state_sha256(state: dict[str, Any]) -> str:
    encoded = json.dumps(
        state,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _instance_spec_sha256(path: Path) -> str:
    """Return the semantic digest used by scenario instance bindings."""

    try:
        return KubernetesInteractionInstanceSpec.from_path(path).sha256
    except (OSError, TypeError, ValueError) as error:
        raise _error(f"invalid Kubernetes instance spec: {error}") from error


def _validate_active_scenario(
    root: Path,
    scenario_path: str | Path,
) -> tuple[NativeScenario, str, str]:
    path, relative = _repo_file(root, scenario_path, label="active Kubernetes scenario")
    scenario = load_native_scenario(path)
    document_failures = validate_native_scenario_document(scenario)
    if document_failures:
        raise _error(
            "active Kubernetes scenario document is invalid: "
            + ", ".join(document_failures)
        )
    raw = scenario.raw
    if (
        scenario.domain_id != _DOMAIN_ID
        or scenario.family_id != _FAMILY_ID
        or raw.get("runtime_id") != _RUNTIME_ID
        or scenario.split != _SPLIT
        or scenario.tier != _TIER
        or raw.get("admission_status") != _ADMISSION_STATUS
        or raw.get("implementation_status") != "native replay admitted"
        or raw.get("evaluation_status", {}).get("hidden_test_eligible") is not False
        or scenario.variants != _VARIANTS
    ):
        raise _error("active Kubernetes scenario is not the admitted public-dev slot")
    instance_path, _ = _repo_file(root, _INSTANCE_SPEC, label="Kubernetes instance spec")
    instance_sha = _instance_spec_sha256(instance_path)
    try:
        declared_sha = require_sha256(
            raw.get("instance_spec_sha256"),
            label="scenario instance_spec_sha256",
        )
    except NativeFormalSourceError as error:
        raise _error(error) from error
    if declared_sha != instance_sha:
        raise _error("scenario does not bind the active Kubernetes instance spec")
    prefix = strict_object(scenario.resolve_artifact("prefix"), label="scenario prefix")
    if prefix.get("scenario_id") != scenario.scenario_id:
        raise _error("scenario and prefix identities disagree")
    admission = validate_native_scenario(scenario)
    if (
        not admission.passed
        or admission.admitted_tier != _TIER
        or admission.scenario_id != scenario.scenario_id
    ):
        raise _error("active Kubernetes scenario does not recompute as hard-admitted")
    return scenario, relative, declared_sha


def _validate_runtime_contract(
    root: Path,
    manifest: ExactFileManifest,
) -> tuple[str, str]:
    runtime_path, _ = _repo_file(
        root,
        "data/runtimes/kubernetes-v1.34/runtime.json",
        label="Kubernetes runtime contract",
    )
    audit_path, _ = _repo_file(
        root,
        "data/runtimes/kubernetes-v1.34/source_audit.json",
        label="Kubernetes source audit",
    )
    runtime = strict_object(runtime_path, label="Kubernetes runtime contract")
    audit = strict_object(audit_path, label="Kubernetes source audit")
    if (
        runtime.get("runtime_id") != _RUNTIME_ID
        or audit.get("runtime_id") != _RUNTIME_ID
        or runtime.get("declared_status", {}).get("source_audit") != "passed"
    ):
        raise _error("Kubernetes runtime metadata is not admitted and source-audited")
    kubernetes_sources = [
        item
        for item in runtime.get("upstream_components", [])
        if isinstance(item, dict)
        and str(item.get("repository", "")).endswith("/kubernetes")
    ]
    if len(kubernetes_sources) != 1:
        raise _error("Kubernetes runtime must pin one upstream Kubernetes revision")
    revision = str(kubernetes_sources[0].get("revision", ""))
    if len(revision) != 40 or any(ch not in "0123456789abcdef" for ch in revision):
        raise _error("Kubernetes upstream revision is not a full Git commit")
    report_path = manifest.root / _RUNTIME_SOURCE_VERIFICATION
    if not report_path.is_file():
        raise _error("Kubernetes runtime source-verification report is missing")
    manifest.require_file(report_path, label="Kubernetes source-verification report")
    report = strict_object(report_path, label="Kubernetes source-verification report")
    expected_rows = {
        (str(source["repository"]), str(source["revision"]), str(item["path"])): str(
            item["sha256"]
        )
        for source in audit.get("sources", [])
        if isinstance(source, dict)
        for item in source.get("audited_paths", [])
        if isinstance(item, dict)
    }
    observed_rows: dict[tuple[str, str, str], str] = {}
    for row in report.get("checks", []):
        if not isinstance(row, dict) or row.get("passed") is not True:
            raise _error("Kubernetes source-verification contains a failed check")
        key = (
            str(row.get("repository", "")),
            str(row.get("revision", "")),
            str(row.get("path", "")),
        )
        if (
            row.get("expected_sha256") != row.get("actual_sha256")
            or key in observed_rows
        ):
            raise _error("Kubernetes source-verification is duplicated or drifted")
        observed_rows[key] = str(row.get("actual_sha256", ""))
    if report.get("runtime_id") != _RUNTIME_ID or report.get("passed") is not True:
        raise _error("Kubernetes source-verification report did not pass")
    if observed_rows != expected_rows:
        raise _error("Kubernetes source-verification does not match the source audit")
    return revision, report_path.relative_to(root).as_posix()


def _validate_bundle_manifest(payload: dict[str, Any], *, label: str) -> None:
    files = payload.get("files")
    if (
        set(payload)
        != {
            "schema_version",
            "capture_mode",
            "cluster_name",
            "node_image",
            "files",
        }
        or payload.get("schema_version") != "1.0"
        or payload.get("capture_mode")
        != "etcd_snapshot_and_quiesced_registry_sqlite"
        or payload.get("cluster_name") != "aftermath-kubernetes"
        or not str(payload.get("node_image", "")).startswith(
            "kindest/node:v1.34.0@sha256:"
        )
        or not isinstance(files, dict)
        or set(files) != {"etcd", "external_registry"}
    ):
        raise _error(f"{label} is not an exact Kubernetes bundle manifest")
    expected_paths = {
        "etcd": "etcd.snapshot.db",
        "external_registry": "webhook-sink.sqlite3",
    }
    for key, expected_path in expected_paths.items():
        item = files[key]
        try:
            digest = require_sha256(item.get("sha256"), label=f"{label} {key} sha256")
        except (AttributeError, NativeFormalSourceError) as error:
            raise _error(error) from error
        if (
            set(item) != {"path", "bytes", "sha256"}
            or item.get("path") != expected_path
            or type(item.get("bytes")) is not int
            or item["bytes"] <= 0
            or not digest
        ):
            raise _error(f"{label} has invalid {key} archive metadata")


def _load_bundle_manifests(
    root: Path,
    paths: Iterable[str | Path],
) -> dict[str, tuple[str, dict[str, Any]]]:
    result: dict[str, tuple[str, dict[str, Any]]] = {}
    for index, value in enumerate(paths):
        path, relative = _repo_file(
            root,
            value,
            label=f"Kubernetes bundle manifest {index + 1}",
        )
        payload = strict_object(path, label=f"Kubernetes bundle manifest {index + 1}")
        _validate_bundle_manifest(payload, label=f"Kubernetes bundle manifest {index + 1}")
        digest = sha256_file(path)
        if digest in result:
            raise _error("Kubernetes bundle manifest inputs must be byte-unique")
        result[digest] = (relative, payload)
    if len(result) != len(_VARIANTS) + 1:
        raise _error("formal Kubernetes evidence requires one reset and thirteen boundary bundles")
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
            label=f"{label} bundle manifest hash",
        )
    except NativeFormalSourceError as error:
        raise _error(error) from error
    selected = manifests.get(digest)
    if selected is None or capture.get("bundle") != selected[1]:
        raise _error(f"{label} references an undeclared or drifted bundle")
    return selected[0]


def _validate_capture_common(
    capture: dict[str, Any],
    *,
    scenario: NativeScenario,
    variant_id: str,
    phase: str,
    prefix_sha256: str,
) -> dict[str, Any]:
    state = capture.get("state")
    if (
        capture.get("schema_version") != "1.0"
        or capture.get("artifact_type")
        != "kubernetes_interaction_state_evidence"
        or capture.get("scenario_id") != scenario.scenario_id
        or capture.get("variant_id") != variant_id
        or capture.get("phase") != phase
        or capture.get("normalization_contract")
        != "kubernetes-interaction-boundary-v6"
        or capture.get("prefix_file_sha256") != prefix_sha256
        or not isinstance(state, dict)
        or capture.get("state_sha256") != _json_state_sha256(state)
    ):
        raise _error(f"Kubernetes {phase} capture {variant_id} is invalid")
    return state


def _validate_reset(
    capture: dict[str, Any],
    *,
    scenario: NativeScenario,
    variant_id: str,
    prefix_sha256: str,
    pre_snapshot_sha256: str,
    manifests: dict[str, tuple[str, dict[str, Any]]],
) -> str:
    _validate_capture_common(
        capture,
        scenario=scenario,
        variant_id=variant_id,
        phase="reset",
        prefix_sha256=prefix_sha256,
    )
    if capture.get("reset_verified") is not True:
        raise _error(f"Kubernetes reset capture {variant_id} is not verified")
    if capture.get("pre_snapshot_state_file_sha256") != pre_snapshot_sha256:
        raise _error(
            f"Kubernetes reset capture {variant_id} lacks exact replay evidence"
        )
    return _validate_capture_bundle(
        capture,
        manifests=manifests,
        label=f"Kubernetes reset capture {variant_id}",
    )


def _validate_raw_boundary(
    payload: dict[str, Any],
    *,
    scenario: NativeScenario,
    variant_id: str,
    prefix: dict[str, Any],
) -> None:
    checks = payload.get("checks")
    declared = payload.get("declared_counterfactual_facts")
    if (
        payload.get("schema_version") != "0.5"
        or payload.get("scenario_id") != scenario.scenario_id
        or payload.get("variant") != variant_id
        or payload.get("surface_result")
        != scenario.raw["ambiguous_operation"]["surface_result"]
        or payload.get("visible_failure")
        != {
            "ok": False,
            "error": scenario.raw["ambiguous_operation"]["surface_result"],
        }
        or payload.get("prefix_fingerprint") != prefix.get("fingerprint")
        or payload.get("prefix_trace") != prefix.get("trace")
        or not isinstance(checks, dict)
        or not checks
        or not all(value is True for value in checks.values())
        or payload.get("passed") is not True
        or not isinstance(declared, dict)
        or payload.get("counterfactual_facts") != declared
        or not isinstance(payload.get("failure_boundary_evidence"), dict)
    ):
        raise _error(f"Kubernetes raw boundary {variant_id} is not a passing ambiguous failure")


def _validate_boundary(
    capture: dict[str, Any],
    *,
    reset_path: Path,
    raw_boundary_path: Path,
    raw_boundary: dict[str, Any],
    scenario: NativeScenario,
    variant_id: str,
    prefix_sha256: str,
    pre_snapshot_sha256: str,
    manifests: dict[str, tuple[str, dict[str, Any]]],
) -> str:
    state = _validate_capture_common(
        capture,
        scenario=scenario,
        variant_id=variant_id,
        phase="boundary",
        prefix_sha256=prefix_sha256,
    )
    facts = state.get("boundary_facts")
    declared = raw_boundary["declared_counterfactual_facts"]
    if (
        capture.get("boundary_validation_passed") is not True
        or capture.get("reset_evidence_file_sha256") != sha256_file(reset_path)
        or capture.get("failure_report_file_sha256")
        != sha256_file(raw_boundary_path)
        or capture.get("surface_result") != raw_boundary.get("surface_result")
        or capture.get("visible_failure") != raw_boundary.get("visible_failure")
        or not isinstance(facts, dict)
        or any(facts.get(key) != value for key, value in declared.items())
        or capture.get("pre_snapshot_state_file_sha256")
        != pre_snapshot_sha256
    ):
        raise _error(f"Kubernetes boundary capture {variant_id} is not cross-bound")
    return _validate_capture_bundle(
        capture,
        manifests=manifests,
        label=f"Kubernetes boundary capture {variant_id}",
    )


def _evaluation_payload(evidence: dict[str, Any]) -> dict[str, Any]:
    evaluation = evaluate_kubernetes_interaction_recovery(evidence)
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
    scenario: NativeScenario,
    variant_id: str,
) -> tuple[str, ...]:
    trace = payload.get("reference_trace")
    final = payload.get("final_evidence")
    if (
        payload.get("schema_version") != "0.5"
        or payload.get("scenario_id") != scenario.scenario_id
        or payload.get("variant") != variant_id
        or payload.get("control")
        != "state_driven_reference_using_agent_visible_tools"
        or payload.get("control_error") is not None
        or not isinstance(trace, list)
        or not trace
        or not isinstance(final, dict)
        or payload.get("evaluation") != _evaluation_payload(final)
        or payload.get("evaluation", {}).get("passed") is not True
        or payload.get("semantic_recovery_direction")
        != payload.get("evaluation", {})
        .get("diagnostics", {})
        .get("semantic_recovery_direction")
    ):
        raise _error(f"Kubernetes reference {variant_id} is not a recomputed passing recovery")
    known_tools = set(KubernetesInteractionEnvironment.TOOL_NAMES)
    observed_names: list[str] = []
    for index, event in enumerate(trace):
        if (
            not isinstance(event, dict)
            or event.get("tool") not in known_tools
            or not isinstance(event.get("arguments"), dict)
            or "result" not in event
        ):
            raise _error(f"Kubernetes reference {variant_id} trace[{index}] is invalid")
        observed_names.append(str(event["tool"]))
    mutations = set(KubernetesInteractionEnvironment.MUTATION_TOOLS)
    if (
        payload.get("query_tools")
        != [name for name in observed_names if name not in mutations]
        or payload.get("mutation_tools")
        != [name for name in observed_names if name in mutations]
    ):
        raise _error(f"Kubernetes reference {variant_id} tool summaries drifted")
    return tuple(sorted(payload["evaluation"]["checks"]))


def _validate_control_trajectory(
    payload: dict[str, Any],
    *,
    root: Path,
    scenario: NativeScenario,
    instance_spec_sha256: str,
    variant_id: str,
    formal_input_lock_path: str,
    trusted_producer_commit: str,
    raw_boundary_path: Path,
    raw_boundary: dict[str, Any],
) -> str:
    turns = payload.get("turns")
    final = payload.get("final_evidence")
    if (
        payload.get("scenario_id") != scenario.scenario_id
        or payload.get("domain") != scenario.domain_id
        or payload.get("family") != scenario.family_id
        or payload.get("instance_id") != scenario.instance_id
        or payload.get("instance_spec_sha256") != instance_spec_sha256
        or payload.get("variant") != variant_id
        or payload.get("execution_control") is not True
        or not isinstance(payload.get("run_id"), str)
        or not payload["run_id"]
        or not isinstance(turns, list)
        or not turns
        or not isinstance(final, dict)
        or payload.get("final_state_sha256") != canonical_fingerprint(final)
        or payload.get("evaluation") != _evaluation_payload(final)
        or payload.get("surface_failure") != raw_boundary.get("visible_failure")
    ):
        raise _error(f"Kubernetes execution control {variant_id} is incomplete or forged")
    known_tools = set(KubernetesInteractionEnvironment.TOOL_NAMES)
    flattened: list[tuple[str, dict[str, Any], Any]] = []
    for turn in turns:
        if not isinstance(turn, dict):
            raise _error(f"Kubernetes execution control {variant_id} has an invalid turn")
        calls = turn.get("tool_calls")
        results = turn.get("tool_results")
        if not isinstance(calls, list) or not isinstance(results, list):
            raise _error(f"Kubernetes execution control {variant_id} lacks raw tool records")
        by_call = {
            str(item.get("call_id")): item
            for item in results
            if isinstance(item, dict)
        }
        if len(by_call) != len(results):
            raise _error(f"Kubernetes execution control {variant_id} duplicates tool results")
        for call in calls:
            if not isinstance(call, dict) or call.get("name") not in known_tools:
                raise _error(f"Kubernetes execution control {variant_id} used an unknown tool")
            result = by_call.get(str(call.get("call_id")))
            if result is None or result.get("name") != call.get("name"):
                raise _error(f"Kubernetes execution control {variant_id} has an unpaired tool call")
            flattened.append(
                (str(call["name"]), dict(call.get("arguments", {})), result.get("result"))
            )
    events = payload.get("environment_tool_events")
    if not isinstance(events, list) or len(events) != len(flattened):
        raise _error(f"Kubernetes execution control {variant_id} tool audit is incomplete")
    for expected, event in zip(flattened, events, strict=True):
        if not isinstance(event, dict) or expected != (
            event.get("tool"),
            event.get("arguments"),
            event.get("result"),
        ):
            raise _error(f"Kubernetes execution control {variant_id} tool audit drifted")
    recorded_lock = payload.get("formal_input_lock")
    if not isinstance(recorded_lock, dict):
        raise _error(f"Kubernetes execution control {variant_id} lacks an input lock")
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
        raise _error(f"Kubernetes execution control {variant_id} input lock drifted")
    return str(payload["run_id"])


def _validate_control_summary(
    payload: dict[str, Any],
    *,
    scenario: NativeScenario,
    trajectories: dict[str, dict[str, Any]],
) -> None:
    reports = payload.get("reports")
    counts = payload.get("execution_control_counts")
    if (
        not isinstance(reports, list)
        or len(reports) != len(_VARIANTS)
        or payload.get("completed_runs") != len(_VARIANTS)
        or payload.get("run_errors") != []
        or not isinstance(counts, dict)
        or counts.get("true") != len(_VARIANTS)
    ):
        raise _error("Kubernetes execution-control summary is incomplete")
    passed = sum(
        item.get("evaluation", {}).get("passed") is True
        for item in trajectories.values()
    )
    rate = payload.get("task_pass_rate")
    if (
        not isinstance(rate, (int, float))
        or abs(float(rate) - passed / len(_VARIANTS)) > 1e-12
        or float(rate) < _MIN_CONTROL_PASS_RATE
    ):
        raise _error("Kubernetes execution-control pass rate is invalid or below 80%")
    observed: set[str] = set()
    for report in reports:
        if not isinstance(report, dict):
            raise _error("Kubernetes execution-control summary report is invalid")
        variant = str(report.get("variant", ""))
        trajectory = trajectories.get(variant)
        if (
            variant not in scenario.variants
            or variant in observed
            or report.get("scenario_id") != scenario.scenario_id
            or trajectory is None
            or report.get("passed")
            is not trajectory.get("evaluation", {}).get("passed")
            or Path(str(report.get("path", ""))).name != f"{variant}.json"
        ):
            raise _error("Kubernetes execution-control summary identity drifted")
        observed.add(variant)
    if observed != set(scenario.variants):
        raise _error("Kubernetes execution-control summary lacks full coverage")


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
) -> tuple[
    tuple[_VariantEvidence, ...],
    tuple[str, ...],
    dict[str, tuple[str, ...]],
]:
    prefix_path = scenario.resolve_artifact("prefix")
    prefix = strict_object(prefix_path, label="Kubernetes scenario prefix")
    prefix_sha = sha256_file(prefix_path)
    runtime_prefix = runtime_manifest.root / "runtime" / "prefix.json"
    runtime_manifest.require_file(runtime_prefix, label="Kubernetes runtime prefix")
    if runtime_prefix.read_bytes() != prefix_path.read_bytes():
        raise _error("Kubernetes scenario prefix differs from the native runtime prefix")
    reset_pre_snapshot = capture_directory / "reset-pre-snapshot.json"
    if not reset_pre_snapshot.is_file():
        raise _error("Kubernetes reset pre-snapshot evidence is missing")
    runtime_manifest.require_file(
        reset_pre_snapshot,
        label="Kubernetes reset pre-snapshot evidence",
    )
    reset_pre_snapshot_sha = sha256_file(reset_pre_snapshot)
    evidence: list[_VariantEvidence] = []
    check_ids: tuple[str, ...] | None = None
    used = {"reset": set(), "boundary": set()}
    run_ids: set[str] = set()
    trajectories: dict[str, dict[str, Any]] = {}
    for variant_id in scenario.variants:
        reset_path, reset_relative = _repo_file(
            root,
            capture_directory / f"{variant_id}-reset.json",
            label=f"Kubernetes reset capture {variant_id}",
        )
        boundary_path, boundary_relative = _repo_file(
            root,
            capture_directory / f"{variant_id}-boundary.json",
            label=f"Kubernetes boundary capture {variant_id}",
        )
        reference_start_path, reference_start_relative = _repo_file(
            root,
            capture_directory / f"{variant_id}-reference-start.json",
            label=f"Kubernetes reference-start capture {variant_id}",
        )
        raw_boundary_path = runtime_manifest.root / "runtime" / f"{variant_id}-boundary.json"
        raw_reference_path = runtime_manifest.root / "runtime" / f"{variant_id}-reference.json"
        boundary_pre_snapshot = capture_directory / f"{variant_id}-pre-snapshot.json"
        for selected, label in (
            (raw_boundary_path, f"Kubernetes raw boundary {variant_id}"),
            (raw_reference_path, f"Kubernetes raw reference {variant_id}"),
            (reference_start_path, f"Kubernetes reference-start capture {variant_id}"),
            (boundary_pre_snapshot, f"Kubernetes boundary pre-snapshot {variant_id}"),
        ):
            if not selected.is_file():
                raise _error(f"{label} is missing")
            runtime_manifest.require_file(selected, label=label)
        if reference_start_path.read_bytes() != boundary_path.read_bytes():
            raise _error(f"Kubernetes reference start {variant_id} differs from its boundary")
        reset = strict_object(reset_path, label=f"Kubernetes reset capture {variant_id}")
        boundary = strict_object(
            boundary_path,
            label=f"Kubernetes boundary capture {variant_id}",
        )
        raw_boundary = strict_object(
            raw_boundary_path,
            label=f"Kubernetes raw boundary {variant_id}",
        )
        raw_reference = strict_object(
            raw_reference_path,
            label=f"Kubernetes raw reference {variant_id}",
        )
        _validate_raw_boundary(
            raw_boundary,
            scenario=scenario,
            variant_id=variant_id,
            prefix=prefix,
        )
        used["reset"].add(
            _validate_reset(
                reset,
                scenario=scenario,
                variant_id=variant_id,
                prefix_sha256=prefix_sha,
                pre_snapshot_sha256=reset_pre_snapshot_sha,
                manifests=bundle_manifests,
            )
        )
        used["boundary"].add(
            _validate_boundary(
                boundary,
                reset_path=reset_path,
                raw_boundary_path=raw_boundary_path,
                raw_boundary=raw_boundary,
                scenario=scenario,
                variant_id=variant_id,
                prefix_sha256=prefix_sha,
                pre_snapshot_sha256=sha256_file(boundary_pre_snapshot),
                manifests=bundle_manifests,
            )
        )
        observed_checks = _validate_reference(
            raw_reference,
            scenario=scenario,
            variant_id=variant_id,
        )
        if check_ids is None:
            check_ids = observed_checks
        elif check_ids != observed_checks:
            raise _error("Kubernetes references expose inconsistent evaluator checks")

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
                (trajectory_path, f"Kubernetes execution control {variant_id}"),
                (pre_model_path, f"Kubernetes pre-model boundary {variant_id}"),
            ):
                if not selected.is_file():
                    raise _error(f"{label} is missing")
                control_manifest.require_file(selected, label=label)
            if pre_model_path.read_bytes() != boundary_path.read_bytes():
                raise _error(f"Kubernetes pre-model boundary {variant_id} drifted")
            trajectory = strict_object(
                trajectory_path,
                label=f"Kubernetes execution control {variant_id}",
            )
            recorded = trajectory.get("pre_model_boundary_evidence")
            if (
                not isinstance(recorded, dict)
                or recorded.get("variant_id") != variant_id
                or recorded.get("source_basename") != pre_model_path.name
                or recorded.get("sha256") != sha256_file(pre_model_path)
            ):
                raise _error(f"Kubernetes execution control {variant_id} lacks boundary binding")
            if formal_input_lock_path is None:
                raise _error("Kubernetes completion requires a formal input lock")
            run_id = _validate_control_trajectory(
                trajectory,
                root=root,
                scenario=scenario,
                instance_spec_sha256=instance_spec_sha256,
                variant_id=variant_id,
                formal_input_lock_path=formal_input_lock_path,
                trusted_producer_commit=trusted_producer_commit,
                raw_boundary_path=raw_boundary_path,
                raw_boundary=raw_boundary,
            )
            if run_id in run_ids:
                raise _error("Kubernetes execution-control run IDs must be unique")
            run_ids.add(run_id)
            trajectories[variant_id] = trajectory
            trajectory_relative = trajectory_path.relative_to(root).as_posix()
            pre_model_relative = pre_model_path.relative_to(root).as_posix()
        evidence.append(
            _VariantEvidence(
                variant_id=variant_id,
                reset_path=reset_path,
                reset_relative=reset_relative,
                boundary_path=boundary_path,
                boundary_relative=boundary_relative,
                raw_boundary_path=raw_boundary_path,
                raw_boundary_relative=raw_boundary_path.relative_to(root).as_posix(),
                raw_reference_path=raw_reference_path,
                raw_reference_relative=raw_reference_path.relative_to(root).as_posix(),
                reference_start_path=reference_start_path,
                reference_start_relative=reference_start_relative,
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
            raise _error("Kubernetes execution-control summary is missing")
        control_manifest.require_file(summary_path, label="Kubernetes control summary")
        _validate_control_summary(
            strict_object(summary_path, label="Kubernetes control summary"),
            scenario=scenario,
            trajectories=trajectories,
        )
    if check_ids is None:
        raise _error("Kubernetes formal evidence has no evaluator checks")
    declared = {relative for relative, _ in bundle_manifests.values()}
    if used["reset"] | used["boundary"] != declared:
        raise _error("Kubernetes capture bundle inputs are not all used")
    if len(used["reset"]) != 1 or len(used["boundary"]) != len(_VARIANTS):
        raise _error("Kubernetes reset and boundary captures do not bind the expected bundles")
    return (
        tuple(evidence),
        check_ids,
        {phase: tuple(sorted(paths)) for phase, paths in used.items()},
    )


def _formal_source(root: Path, path: str, *, label: str) -> str:
    return _repo_file(root, path, label=label)[1]


def _tool_role(
    *,
    root: Path,
    output: str,
    runtime_revision: str,
    source_verification_relative: str,
) -> dict[str, Any]:
    tools = tuple(KUBERNETES_MIGRATION_TOOL_DEFINITIONS)
    if (
        len(tools) != len(KubernetesInteractionEnvironment.TOOL_NAMES)
        or {tool.name for tool in tools}
        != set(KubernetesInteractionEnvironment.TOOL_NAMES)
    ):
        raise _error("Kubernetes public tool definitions and implementation disagree")
    try:
        return build_tool_contract_role(
            output=output,
            sources=ToolContractSources(
                definition=FormalSource(
                    _formal_source(root, _TOOL_DEFINITION_SOURCE, label="tool definitions"),
                    "sources/native_kubernetes_migration_family.py",
                ),
                implementation=FormalSource(
                    _formal_source(
                        root,
                        _TOOL_IMPLEMENTATION_SOURCE,
                        label="tool implementation",
                    ),
                    "sources/kubernetes_interaction_recovery.py",
                ),
                implementation_dependencies=tuple(
                    FormalSource(
                        _formal_source(root, path, label=f"tool dependency {path}"),
                        f"sources/dependencies/{index:02d}-{Path(path).name}",
                    )
                    for index, path in enumerate(_TOOL_DEPENDENCIES, start=1)
                ),
                runtime_revision=runtime_revision,
                runtime_verification=FormalSource(
                    source_verification_relative,
                    "native-runtime/source-verification.json",
                ),
                runtime_sources=tuple(
                    FormalSource(
                        _formal_source(root, path, label=f"runtime source {path}"),
                        f"native-runtime/{index:02d}-{Path(path).name}",
                    )
                    for index, path in enumerate(_RUNTIME_CONTRACT_SOURCES, start=1)
                ),
                tools=tuple(
                    PublicToolContract(
                        name=tool.name,
                        description=tool.description,
                        input_schema=tool.input_schema,
                        implementation_symbol="KubernetesInteractionEnvironment.invoke",
                    )
                    for tool in tools
                ),
            ),
        )
    except NativeFormalSpecError as error:
        raise _error(error) from error


def _evaluator_role(*, root: Path, output: str, check_ids: tuple[str, ...]) -> dict[str, Any]:
    try:
        return build_evaluator_role(
            output=output,
            sources=EvaluatorContractSources(
                implementation=FormalSource(
                    _formal_source(root, _EVALUATOR_SOURCE, label="Kubernetes evaluator"),
                    "sources/kubernetes_interaction_recovery.py",
                ),
                implementation_symbol="evaluate_kubernetes_interaction_recovery",
                check_ids=check_ids,
                scored_state_fields=_SCORED_STATE_FIELDS,
            ),
        )
    except NativeFormalSpecError as error:
        raise _error(error) from error


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
) -> dict[str, dict[str, Any]]:
    boundary_sources = tuple(
        _formal_source(root, path, label=f"boundary source {path}")
        for path in _BOUNDARY_CONTRACT_SOURCES
    )
    try:
        return build_input_evidence_roles(
            output=output,
            sources=InputEvidenceSources(
                operation=scenario.raw["ambiguous_operation"]["operation"],
                prefix_source_path=scenario.resolve_artifact("prefix").relative_to(root).as_posix(),
                runtime_manifest_source_path=runtime_manifest_relative,
                runtime_revision=runtime_revision,
                boundary_verification_source_path=source_verification_relative,
                boundary_contract_sources=tuple(
                    FormalSource(
                        source,
                        f"native-boundary/{index:02d}-{Path(source).name}",
                    )
                    for index, source in enumerate(boundary_sources, start=1)
                ),
                reset_capture_manifest_sources=capture_usage["reset"],
                boundary_capture_manifest_sources=capture_usage["boundary"],
                variants=tuple(
                    VariantInputEvidence(
                        variant_id=item.variant_id,
                        reset_source_path=item.reset_relative,
                        boundary_state_source_path=item.boundary_relative,
                        raw_failure_report_source_path=item.raw_boundary_relative,
                        reference_start_state_source_path=item.reference_start_relative,
                        raw_reference_report_source_path=item.raw_reference_relative,
                    )
                    for item in evidence
                ),
            ),
        )
    except NativeFormalSpecError as error:
        raise _error(error) from error


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
        raise _error("complete phase requires all thirteen execution controls")
    try:
        return build_completion_roles(
            output=output,
            input_variant_ids=tuple(item.variant_id for item in evidence),
            sources=CompletionEvidenceSources(
                control_manifest_source_path=control_manifest_relative,
                model_input_lock_source_path=model_input_lock_relative,
                variants=tuple(
                    VariantCompletionEvidence(
                        variant_id=item.variant_id,
                        run_id=str(item.trajectory["run_id"]),
                        trajectory_source_path=str(item.trajectory_relative),
                        pre_model_boundary_source_path=str(
                            item.pre_model_boundary_relative
                        ),
                        passed=item.trajectory["evaluation"]["passed"] is True,
                    )
                    for item in evidence
                    if item.trajectory is not None
                ),
            ),
        )
    except NativeFormalSpecError as error:
        raise _error(error) from error


def generate_kubernetes_interaction_formal_build_spec(
    *,
    root: str | Path,
    benchmark_release_id: str,
    output_directory: str,
    runtime_manifest_path: str | Path,
    capture_directory: str | Path,
    capture_bundle_manifest_paths: Iterable[str | Path],
    phase: str,
    scenario_path: str | Path,
    control_manifest_path: str | Path | None = None,
    model_input_lock_path: str | Path | None = None,
) -> KubernetesInteractionFormalBuildSpecResult:
    """Generate a strict seven-role spec from exact Kubernetes evidence."""

    resolved_root = Path(root).resolve()
    if not resolved_root.is_dir():
        raise _error("repository root must be an existing directory")
    if phase not in {"inputs", "complete"}:
        raise _error("phase must be inputs or complete")
    if phase == "inputs" and (
        control_manifest_path is not None or model_input_lock_path is not None
    ):
        raise _error("inputs phase must not receive completion evidence")
    if phase == "complete" and (
        control_manifest_path is None or model_input_lock_path is None
    ):
        raise _error("complete phase requires control manifest and input lock")
    try:
        release_id = require_identifier(
            benchmark_release_id,
            label="benchmark_release_id",
        )
        output = validate_output_directory(resolved_root, output_directory)
    except NativeFormalSourceError as error:
        raise _error(error) from error
    scenario, scenario_relative, instance_sha = _validate_active_scenario(
        resolved_root,
        scenario_path,
    )
    runtime_manifest = _exact_manifest(
        resolved_root,
        runtime_manifest_path,
        label="Kubernetes runtime exact manifest",
    )
    runtime_revision, source_verification_relative = _validate_runtime_contract(
        resolved_root,
        runtime_manifest,
    )
    capture_dir, _ = _repo_directory(
        resolved_root,
        capture_directory,
        label="Kubernetes state capture directory",
    )
    bundle_manifests = _load_bundle_manifests(
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
            label="Kubernetes control exact manifest",
        )
        control_relative = control_manifest.relative_path
        lock_path, lock_relative = _repo_file(
            resolved_root,
            model_input_lock_path,
            label="Kubernetes formal input lock",
        )
        if lock_path != (resolved_root / output / "formal-input-lock.json").resolve():
            raise _error("complete phase input lock must be the frozen formal lock")
    try:
        producer_commit = current_git_commit(resolved_root)
    except NativeFormalSourceError as error:
        raise _error(error) from error
    evidence, check_ids, capture_usage = _collect_variant_evidence(
        root=resolved_root,
        scenario=scenario,
        instance_spec_sha256=instance_sha,
        runtime_manifest=runtime_manifest,
        control_manifest=control_manifest,
        formal_input_lock_path=lock_relative,
        trusted_producer_commit=producer_commit,
        capture_directory=capture_dir,
        bundle_manifests=bundle_manifests,
    )
    roles: dict[str, dict[str, Any]] = {
        "tool_contract": _tool_role(
            root=resolved_root,
            output=output,
            runtime_revision=runtime_revision,
            source_verification_relative=source_verification_relative,
        ),
        "evaluator": _evaluator_role(
            root=resolved_root,
            output=output,
            check_ids=check_ids,
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
    return KubernetesInteractionFormalBuildSpecResult(
        spec=spec,
        scenario_path=scenario_relative,
        runtime_manifest_path=runtime_manifest.relative_path,
        control_manifest_path=control_relative,
        capture_bundle_manifest_paths=tuple(
            sorted(relative for relative, _ in bundle_manifests.values())
        ),
    )


def write_kubernetes_interaction_formal_build_spec(
    path: str | Path,
    spec: dict[str, Any],
    *,
    root: str | Path,
) -> str:
    try:
        return write_formal_build_spec(path, spec, root=root)
    except NativeFormalSourceError as error:
        raise _error(error) from error


__all__ = [
    "KubernetesInteractionFormalBuildSpecError",
    "KubernetesInteractionFormalBuildSpecResult",
    "generate_kubernetes_interaction_formal_build_spec",
    "write_kubernetes_interaction_formal_build_spec",
]
