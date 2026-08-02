from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from collections.abc import Callable, Iterable
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
from .integrations.erpnext_sales_return_evaluator import (
    evaluate_sales_return_recovery,
)
from .integrations.forgejo_publication_recovery import (
    evaluate_forgejo_publication_recovery,
)
from .integrations.kubernetes_interaction_recovery import (
    KubernetesInteractionEvaluation,
    evaluate_kubernetes_interaction_recovery,
)
from .native_admission import (
    NativeAdmissionReport,
    native_admission_report_payload,
    validate_native_scenario,
)
from .native_freeze import verify_frozen_bundle
from .native_scenario import (
    NativeScenario,
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
TRUSTED_FORMAL_EVALUATORS: dict[
    str,
    Callable[..., Any],
] = {
    "forgejo-release-package-publication": (
        evaluate_forgejo_publication_recovery
    ),
    "erpnext-sales-return-exchange-reconciliation": (
        evaluate_sales_return_recovery
    ),
    "k8s-constraint-interaction-recovery": (
        evaluate_kubernetes_interaction_recovery
    ),
}


def _invoke_trusted_formal_evaluator(
    evaluator: Callable[..., Any],
    *,
    family_id: str,
    evidence: dict[str, Any],
    prefix: dict[str, Any],
    root: Path | None = None,
    instance_spec_path: Path | None = None,
) -> Any:
    """Invoke the evaluator protocol frozen for each formal family.

    The Kubernetes interaction evaluator was input-locked before formal
    evaluators received a common ``prefix`` keyword. Preserve that exact
    evaluator rather than changing a frozen scientific input.
    """

    if (
        family_id == "k8s-constraint-interaction-recovery"
        and instance_spec_path is not None
    ):
        if root is None:
            raise ValueError("isolated evaluator requires a repository root")
        script = """
import json
from dataclasses import asdict
from aftermath_bench.integrations.kubernetes_interaction_recovery import (
    evaluate_kubernetes_interaction_recovery,
)
evidence = json.load(__import__('sys').stdin)
print(json.dumps(asdict(evaluate_kubernetes_interaction_recovery(evidence))))
"""
        environment = os.environ.copy()
        environment[
            "AFTERMATH_KUBERNETES_INTERACTION_INSTANCE_SPEC"
        ] = str(instance_spec_path)
        source_root = str(root / "src")
        environment["PYTHONPATH"] = os.pathsep.join(
            value
            for value in (source_root, environment.get("PYTHONPATH", ""))
            if value
        )
        try:
            process = subprocess.run(
                [sys.executable, "-c", script],
                cwd=root,
                env=environment,
                input=json.dumps(evidence, ensure_ascii=False),
                capture_output=True,
                text=True,
                check=True,
                timeout=30,
            )
            payload = json.loads(process.stdout)
            return KubernetesInteractionEvaluation(
                passed=bool(payload["passed"]),
                components=dict(payload["components"]),
                checks=dict(payload["checks"]),
                diagnostics=dict(payload["diagnostics"]),
            )
        except (
            OSError,
            subprocess.SubprocessError,
            json.JSONDecodeError,
            KeyError,
            TypeError,
        ) as error:
            raise ValueError(
                "isolated Kubernetes evaluator failed"
            ) from error
    if family_id == "k8s-constraint-interaction-recovery":
        return evaluator(evidence)
    return evaluator(evidence, prefix=prefix)


def _kubernetes_evaluator_instance_spec(
    *,
    root: Path,
    scenario: NativeScenario,
) -> Path | None:
    """Find the instance spec only when the active evaluator is mismatched."""

    if scenario.family_id != "k8s-constraint-interaction-recovery":
        return None
    from .integrations.kubernetes_interaction_instance import (
        ACTIVE_KUBERNETES_INTERACTION_INSTANCE,
        KubernetesInteractionInstanceSpec,
    )

    expected = str(scenario.raw.get("instance_spec_sha256", ""))
    if expected == ACTIVE_KUBERNETES_INTERACTION_INSTANCE.sha256:
        return None
    candidates: list[Path] = []
    spec_root = root / "data" / "instance_specs"
    if spec_root.is_dir():
        for path in sorted(spec_root.glob("*.json")):
            try:
                if KubernetesInteractionInstanceSpec.from_path(path).sha256 == expected:
                    candidates.append(path.resolve())
            except (OSError, TypeError, ValueError, json.JSONDecodeError):
                continue
    if len(candidates) != 1:
        raise ValueError(
            "Kubernetes formal scenario does not resolve one instance spec"
        )
    return candidates[0]


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


def bound_reset_snapshot_sha256(payload: dict[str, Any]) -> str | None:
    """Resolve the canonical or native name for the bound reset file hash."""

    digests = [
        payload[field]
        for field in ("reset_snapshot_sha256", "reset_evidence_file_sha256")
        if field in payload
    ]
    if (
        not digests
        or any(
            not isinstance(digest, str)
            or _SHA256.fullmatch(digest) is None
            for digest in digests
        )
        or len(set(digests)) != 1
    ):
        return None
    return digests[0]


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


def _payload_file_matches(
    entry: dict[str, Any],
    *,
    path_field: str,
    sha_field: str,
    file_hashes: dict[str, str],
) -> bool:
    relative = entry.get(path_field)
    expected_sha = entry.get(sha_field)
    return bool(
        isinstance(relative, str)
        and relative
        and isinstance(expected_sha, str)
        and _SHA256.fullmatch(expected_sha)
        and file_hashes.get(relative) == expected_sha
    )


def _validate_admission_release_binding(
    *,
    scenario: NativeScenario,
    admission: NativeAdmissionReport,
    declaration: dict[str, Any],
) -> dict[str, bool]:
    """Bind admission inputs, the derived report, and its release declaration.

    ``admission.artifact_sha256`` deliberately excludes ``admission.json``:
    that file is the output of admission, not one of its inputs.  The release
    manifest separately binds the output file and this function checks that
    its content is the canonical recomputation.
    """

    declared = dict(declaration.get("admission_artifact_sha256", {}))
    declared_inputs = {
        name: digest for name, digest in declared.items() if name != "admission"
    }
    try:
        actual = {
            str(name): file_sha256(scenario.resolve_artifact(str(name)))
            for name in scenario.raw.get("admission_artifacts", {})
        }
        stored = load_json_strict(scenario.resolve_artifact("admission"))
    except (KeyError, OSError, ValueError, json.JSONDecodeError):
        actual = {}
        stored = None

    input_hashes_match = declared_inputs == admission.artifact_sha256
    report_hash_matches = bool(
        "admission" in declared
        and declared.get("admission") == actual.get("admission")
    )
    all_artifact_hashes_match = declared == actual
    report_matches = stored == native_admission_report_payload(admission)
    return {
        "admission_input_artifact_sha256_match": input_hashes_match,
        "admission_report_sha256_match": report_hash_matches,
        "admission_artifact_sha256_match": all_artifact_hashes_match,
        "admission_report_matches_recomputed": report_matches,
    }


def _load_bound_json_payload(
    root: Path,
    entry: dict[str, Any],
    *,
    path_field: str,
    sha_field: str,
    file_hashes: dict[str, str],
) -> dict[str, Any] | None:
    if not _payload_file_matches(
        entry,
        path_field=path_field,
        sha_field=sha_field,
        file_hashes=file_hashes,
    ):
        return None
    try:
        path = safe_relative_path(
            root,
            str(entry[path_field]),
            required_prefix="data",
            must_exist=True,
            require_file=True,
        )
        payload = load_json_strict(path)
    except (KeyError, OSError, ValueError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _variant_payload_index(
    payload: dict[str, Any],
    *,
    variants: tuple[str, ...],
) -> dict[str, dict[str, Any]] | None:
    items = payload.get("variants")
    if not isinstance(items, list):
        return None
    indexed: dict[str, dict[str, Any]] = {}
    observed: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            return None
        variant_id = str(item.get("variant_id", ""))
        if not variant_id or variant_id in indexed:
            return None
        indexed[variant_id] = item
        observed.append(variant_id)
    if tuple(observed) != variants:
        return None
    return indexed


def _formal_payload_identity_matches(
    payload: dict[str, Any],
    *,
    role: str,
    envelope: dict[str, Any],
    benchmark_release_id: str,
    scenario_id: str,
    domain_id: str,
    family_id: str,
    instance_id: str,
    variants: tuple[str, ...],
) -> bool:
    return bool(
        payload.get("schema_version") == "1.0"
        and payload.get("artifact_type") == role
        and payload.get("benchmark_release_id") == benchmark_release_id
        and payload.get("scenario_id") == scenario_id
        and payload.get("domain_id") == domain_id
        and payload.get("family_id") == family_id
        and payload.get("instance_id") == instance_id
        and tuple(map(str, payload.get("variant_ids", ()))) == variants
        and payload.get("producer_commit") == envelope.get("producer_commit")
        and payload.get("input_envelope_sha256")
        == envelope.get("depends_on")
    )


def _formal_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _stored_evaluation_matches(
    stored: Any,
    recomputed: Any,
) -> bool:
    if not isinstance(stored, dict):
        return False
    expected = {
        "passed": recomputed.passed,
        "components": recomputed.components,
        "checks": recomputed.checks,
        "diagnostics": recomputed.diagnostics,
    }
    if any(stored.get(key) != value for key, value in expected.items()):
        return False
    failures = stored.get("failures")
    return failures is None or failures == list(recomputed.failures)


def _validate_completed_formal_chain(
    *,
    root: Path,
    declarations: dict[str, Any],
    benchmark_release_id: str,
    scenario_id: str,
    domain_id: str,
    family_id: str,
    instance_id: str,
    variants: tuple[str, ...],
    control_evidence_path: str,
    control_evidence_sha256: str,
    declarations_manifest_path: str,
    declarations_manifest_sha256: str,
    role_payloads: dict[str, dict[str, Any]],
    role_file_hashes: dict[str, dict[str, str]],
    envelopes: dict[str, dict[str, Any]],
    envelope_hashes: dict[str, str],
    require_trusted_evaluator: bool,
) -> bool:
    """Validate the immutable input lock through the raw control reports.

    This is deliberately independent of the evidence generator.  A caller
    cannot promote a release by presenting seven mutually consistent
    envelopes while omitting the completed declarations manifest, swapping
    the model-visible prefix, or replacing a raw trajectory with a summary
    wrapper.
    """

    try:
        manifest_path = safe_relative_path(
            root,
            declarations_manifest_path,
            required_prefix="data",
            must_exist=True,
            require_file=True,
        )
        if (
            _SHA256.fullmatch(declarations_manifest_sha256) is None
            or file_sha256(manifest_path) != declarations_manifest_sha256
        ):
            return False
        manifest = load_json_strict(manifest_path)
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return False
    manifest_fields = {
        "schema_version",
        "artifact_type",
        "benchmark_release_id",
        "scenario_id",
        "domain_id",
        "family_id",
        "instance_id",
        "variant_ids",
        "producer_commit",
        "scenario_path",
        "formal_input_lock",
        "formal_evidence",
        "control_evidence",
    }
    producer_commits = {
        str(envelope.get("producer_commit", ""))
        for envelope in envelopes.values()
    }
    if (
        not isinstance(manifest, dict)
        or set(manifest) != manifest_fields
        or manifest.get("schema_version") != "1.0"
        or manifest.get("artifact_type")
        != "formal_evidence_declarations"
        or (
            manifest.get("benchmark_release_id"),
            manifest.get("scenario_id"),
            manifest.get("domain_id"),
            manifest.get("family_id"),
            manifest.get("instance_id"),
        )
        != (
            benchmark_release_id,
            scenario_id,
            domain_id,
            family_id,
            instance_id,
        )
        or tuple(map(str, manifest.get("variant_ids", ()))) != variants
        or len(producer_commits) != 1
        or manifest.get("producer_commit") not in producer_commits
        or manifest.get("formal_evidence") != declarations
        or manifest.get("control_evidence")
        != {
            "path": control_evidence_path,
            "sha256": control_evidence_sha256,
            "minimum_task_pass_rate": (
                MIN_EXECUTION_CONTROL_PASS_RATE
            ),
        }
    ):
        return False

    lock_declaration = manifest.get("formal_input_lock")
    if (
        not isinstance(lock_declaration, dict)
        or set(lock_declaration) != {"path", "sha256"}
    ):
        return False
    try:
        lock_path = safe_relative_path(
            root,
            str(lock_declaration["path"]),
            required_prefix="data",
            must_exist=True,
            require_file=True,
        )
        lock_sha256 = file_sha256(lock_path)
        lock = load_json_strict(lock_path)
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return False
    lock_fields = {
        "schema_version",
        "artifact_type",
        "benchmark_release_id",
        "scenario_id",
        "domain_id",
        "family_id",
        "instance_id",
        "variant_ids",
        "producer_commit",
        "scenario_path",
        "scenario_sha256",
        "input_role_declarations",
        "input_projection_sha256",
    }
    input_roles = {
        role
        for role in FORMAL_EVIDENCE_ROLES
        if role not in {"raw_run_archive", "execution_control"}
    }
    if (
        not isinstance(lock, dict)
        or set(lock) != lock_fields
        or lock.get("schema_version") != "1.0"
        or lock.get("artifact_type") != "formal_input_lock"
        or (
            lock.get("benchmark_release_id"),
            lock.get("scenario_id"),
            lock.get("domain_id"),
            lock.get("family_id"),
            lock.get("instance_id"),
        )
        != (
            benchmark_release_id,
            scenario_id,
            domain_id,
            family_id,
            instance_id,
        )
        or tuple(map(str, lock.get("variant_ids", ()))) != variants
        or lock.get("producer_commit") != manifest.get("producer_commit")
        or lock.get("input_role_declarations")
        != {role: declarations[role] for role in input_roles}
        or lock_sha256 != lock_declaration.get("sha256")
    ):
        return False
    projection = {
        key: lock[key]
        for key in (
            "schema_version",
            "benchmark_release_id",
            "scenario_id",
            "domain_id",
            "family_id",
            "instance_id",
            "variant_ids",
            "producer_commit",
            "scenario_path",
            "scenario_sha256",
            "input_role_declarations",
        )
    }
    if (
        hashlib.sha256(_formal_json_bytes(projection)).hexdigest()
        != lock.get("input_projection_sha256")
    ):
        return False

    try:
        scenario_path = safe_relative_path(
            root,
            str(lock["scenario_path"]),
            required_prefix="data",
            must_exist=True,
            require_file=True,
        )
        scenario = load_native_scenario(scenario_path)
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return False
    if (
        str(manifest.get("scenario_path"))
        != scenario_path.relative_to(root).as_posix()
        or file_sha256(scenario_path) != lock.get("scenario_sha256")
        or (
            scenario.scenario_id,
            scenario.domain_id,
            scenario.family_id,
            scenario.instance_id,
            scenario.variants,
        )
        != (scenario_id, domain_id, family_id, instance_id, variants)
    ):
        return False
    try:
        evaluator_instance_spec = _kubernetes_evaluator_instance_spec(
            root=root,
            scenario=scenario,
        )
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return False

    reset_payload = role_payloads["reset_evidence"]
    reset_files = role_file_hashes["reset_evidence"]
    prefix_relative = str(reset_payload.get("prefix_path", ""))
    prefix_sha256 = str(reset_payload.get("prefix_sha256", ""))
    prefix = _load_bound_json_payload(
        root,
        reset_payload,
        path_field="prefix_path",
        sha_field="prefix_sha256",
        file_hashes=reset_files,
    )
    try:
        active_prefix = scenario.resolve_artifact("prefix")
    except (KeyError, OSError, ValueError):
        return False
    if (
        prefix is None
        or not prefix
        or _SHA256.fullmatch(prefix_sha256) is None
        or reset_files.get(prefix_relative) != prefix_sha256
        or not active_prefix.is_file()
        or file_sha256(active_prefix) != prefix_sha256
    ):
        return False

    resets = _variant_payload_index(reset_payload, variants=variants)
    boundaries = _variant_payload_index(
        role_payloads["boundary_bundle"],
        variants=variants,
    )
    references = _variant_payload_index(
        role_payloads["reference_bundle"],
        variants=variants,
    )
    if resets is None or boundaries is None or references is None:
        return False
    expected_locks: dict[str, dict[str, Any]] = {}
    for variant_id in variants:
        reset_snapshot = _load_bound_json_payload(
            root,
            resets[variant_id],
            path_field="reset_snapshot_path",
            sha_field="reset_snapshot_sha256",
            file_hashes=reset_files,
        )
        boundary = boundaries[variant_id]
        raw_failure = _load_bound_json_payload(
            root,
            boundary,
            path_field="raw_failure_report_path",
            sha_field="raw_failure_report_sha256",
            file_hashes=role_file_hashes["boundary_bundle"],
        )
        if (
            reset_snapshot is None
            or reset_snapshot.get("prefix_file_sha256") != prefix_sha256
            or raw_failure is None
            or not raw_failure
        ):
            return False
        expected_locks[variant_id] = {
            "lock_sha256": lock_sha256,
            "input_envelope_sha256": {
                role: envelope_hashes[role] for role in input_roles
            },
            "variant_id": variant_id,
            "boundary_state_sha256": boundary.get(
                "boundary_state_sha256"
            ),
            "failure_report_sha256": boundary.get(
                "raw_failure_report_sha256"
            ),
            "prefix_sha256": prefix_sha256,
        }

    evaluator = TRUSTED_FORMAL_EVALUATORS.get(family_id)
    if require_trusted_evaluator and evaluator is None:
        return False
    if evaluator is not None and require_trusted_evaluator:
        for variant_id in variants:
            terminal = _load_bound_json_payload(
                root,
                references[variant_id],
                path_field="terminal_state_path",
                sha_field="terminal_state_sha256",
                file_hashes=role_file_hashes["reference_bundle"],
            )
            if (
                terminal is None
                or not isinstance(terminal.get("final_evidence"), dict)
            ):
                return False
            try:
                recomputed = _invoke_trusted_formal_evaluator(
                    evaluator,
                    family_id=family_id,
                    evidence=terminal["final_evidence"],
                    prefix=prefix,
                    root=root,
                    instance_spec_path=evaluator_instance_spec,
                )
            except (KeyError, TypeError, ValueError):
                return False
            if (
                not _stored_evaluation_matches(
                    terminal.get("evaluation"),
                    recomputed,
                )
                or references[variant_id].get("evaluator_passed")
                is not recomputed.passed
            ):
                return False

    raw_payload = role_payloads["raw_run_archive"]
    raw_files = role_file_hashes["raw_run_archive"]
    runs = raw_payload.get("runs")
    if not isinstance(runs, list) or not runs:
        return False
    recomputed_runs: dict[str, tuple[dict[str, Any], bool]] = {}
    observed_variants: set[str] = set()
    for run in runs:
        if not isinstance(run, dict):
            return False
        run_id = str(run.get("run_id", ""))
        variant_id = str(run.get("variant_id", ""))
        wrapper = _load_bound_json_payload(
            root,
            run,
            path_field="run_path",
            sha_field="run_sha256",
            file_hashes=raw_files,
        )
        trajectory = _load_bound_json_payload(
            root,
            run,
            path_field="raw_trajectory_path",
            sha_field="raw_trajectory_sha256",
            file_hashes=raw_files,
        )
        pre_model_boundary = _load_bound_json_payload(
            root,
            run,
            path_field="pre_model_boundary_evidence_path",
            sha_field="pre_model_boundary_evidence_sha256",
            file_hashes=raw_files,
        )
        boundary_state = _load_bound_json_payload(
            root,
            boundaries.get(variant_id, {}),
            path_field="boundary_state_path",
            sha_field="boundary_state_sha256",
            file_hashes=role_file_hashes["boundary_bundle"],
        )
        evaluation = (
            trajectory.get("evaluation")
            if isinstance(trajectory, dict)
            else None
        )
        trajectory_pre_model = (
            trajectory.get("pre_model_boundary_evidence")
            if isinstance(trajectory, dict)
            else None
        )
        source_basename = (
            trajectory_pre_model.get("source_basename")
            if isinstance(trajectory_pre_model, dict)
            else None
        )
        pre_model_sha256 = run.get(
            "pre_model_boundary_evidence_sha256"
        )
        if (
            not run_id
            or run_id in recomputed_runs
            or variant_id not in expected_locks
            or variant_id in observed_variants
            or run.get("formal_input_lock_sha256") != lock_sha256
            or run.get("execution_control") is not True
            or wrapper is None
            or wrapper.get("scenario_id") != scenario_id
            or wrapper.get("variant_id") != variant_id
            or wrapper.get("run_id") != run_id
            or wrapper.get("formal_input_lock_sha256") != lock_sha256
            or wrapper.get("raw_trajectory_path")
            != run.get("raw_trajectory_path")
            or wrapper.get("raw_trajectory_sha256")
            != run.get("raw_trajectory_sha256")
            or wrapper.get("pre_model_boundary_evidence_path")
            != run.get("pre_model_boundary_evidence_path")
            or wrapper.get("pre_model_boundary_evidence_sha256")
            != pre_model_sha256
            or wrapper.get("execution_control") is not True
            or trajectory is None
            or trajectory.get("scenario_id") != scenario_id
            or trajectory.get("instance_id") != instance_id
            or trajectory.get("variant") != variant_id
            or trajectory.get("run_id") != run_id
            or trajectory.get("execution_control") is not True
            or not isinstance(evaluation, dict)
            or type(evaluation.get("passed")) is not bool
            or trajectory.get("formal_input_lock")
            != expected_locks[variant_id]
            or run.get("boundary_state_sha256")
            != expected_locks[variant_id]["boundary_state_sha256"]
            or pre_model_sha256 != run.get("boundary_state_sha256")
            or pre_model_boundary is None
            or boundary_state is None
            or pre_model_boundary != boundary_state
            or not isinstance(trajectory_pre_model, dict)
            or set(trajectory_pre_model)
            != {"variant_id", "source_basename", "sha256"}
            or trajectory_pre_model.get("variant_id") != variant_id
            or trajectory_pre_model.get("sha256")
            != pre_model_sha256
            or not isinstance(source_basename, str)
            or not source_basename
            or Path(source_basename).name != source_basename
            or run.get("summary_report_path")
            != run.get("raw_trajectory_path")
            or wrapper.get("summary_report_path")
            != run.get("raw_trajectory_path")
        ):
            return False
        instance_spec_sha256 = scenario.raw.get("instance_spec_sha256")
        if (
            isinstance(instance_spec_sha256, str)
            and instance_spec_sha256
            and trajectory.get("instance_spec_sha256")
            != instance_spec_sha256
        ):
            return False
        recomputed_passed = bool(evaluation["passed"])
        if evaluator is not None and require_trusted_evaluator:
            if not isinstance(trajectory.get("final_evidence"), dict):
                return False
            try:
                recomputed = _invoke_trusted_formal_evaluator(
                    evaluator,
                    family_id=family_id,
                    evidence=trajectory["final_evidence"],
                    prefix=prefix,
                    root=root,
                    instance_spec_path=evaluator_instance_spec,
                )
            except (KeyError, TypeError, ValueError):
                return False
            if not _stored_evaluation_matches(evaluation, recomputed):
                return False
            recomputed_passed = bool(recomputed.passed)
        if (
            run.get("passed") is not recomputed_passed
            or wrapper.get("passed") is not recomputed_passed
        ):
            return False
        recomputed_runs[run_id] = (run, recomputed_passed)
        observed_variants.add(variant_id)
    if observed_variants != set(variants):
        return False

    control = role_payloads["execution_control"]
    if control.get("formal_input_lock_sha256") != lock_sha256:
        return False
    run_ids = control.get("run_ids")
    if (
        not isinstance(run_ids, list)
        or len(run_ids) != len(variants)
        or len(set(map(str, run_ids))) != len(run_ids)
    ):
        return False
    selected: list[tuple[dict[str, Any], bool]] = []
    for run_id in map(str, run_ids):
        run = recomputed_runs.get(run_id)
        if run is None:
            return False
        selected.append(run)
    recomputed_passed_count = sum(passed for _, passed in selected)
    recomputed_rate = recomputed_passed_count / len(selected)
    try:
        completed_runs = int(control.get("completed_runs", -1))
        passed_runs = int(control.get("passed_runs", -1))
        task_pass_rate = float(control.get("task_pass_rate", -1))
    except (TypeError, ValueError):
        return False
    if (
        completed_runs != len(selected)
        or passed_runs != recomputed_passed_count
        or abs(task_pass_rate - recomputed_rate) > 1e-12
        or task_pass_rate < MIN_EXECUTION_CONTROL_PASS_RATE
    ):
        return False

    try:
        summary = load_json_strict(
            safe_relative_path(
                root,
                control_evidence_path,
                required_prefix="data",
                must_exist=True,
                require_file=True,
            )
        )
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return False
    if not isinstance(summary, dict):
        return False
    reports = summary.get("reports")
    if not isinstance(reports, list) or len(reports) != len(selected):
        return False
    by_variant = {
        str(run["variant_id"]): (run, passed)
        for run, passed in selected
    }
    observed_summary_variants: set[str] = set()
    for report in reports:
        if not isinstance(report, dict):
            return False
        variant_id = str(report.get("variant", ""))
        selected_run = by_variant.get(variant_id)
        if (
            selected_run is None
            or variant_id in observed_summary_variants
            or report.get("scenario_id") != scenario_id
            or report.get("path")
            != selected_run[0].get("raw_trajectory_path")
            or report.get("passed") is not selected_run[1]
        ):
            return False
        observed_summary_variants.add(variant_id)
    return observed_summary_variants == set(variants)


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
    control_evidence_path: str,
    control_evidence_sha256: str,
    declarations_manifest_path: str | None = None,
    declarations_manifest_sha256: str | None = None,
    require_trusted_evaluator: bool = False,
) -> bool:
    if (declarations_manifest_path is None) is not (
        declarations_manifest_sha256 is None
    ):
        return False
    if set(declarations) != FORMAL_EVIDENCE_ROLES:
        return False
    envelope_paths: list[str] = []
    payload_paths: list[str] = []
    envelopes: dict[str, dict[str, Any]] = {}
    envelope_hashes: dict[str, str] = {}
    role_payloads: dict[str, dict[str, Any]] = {}
    role_file_hashes: dict[str, dict[str, str]] = {}
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
        local_hashes: dict[str, str] = {}
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
            local_hashes[canonical_relative] = expected_sha
        if len(local_paths) != len(set(local_paths)):
            return False
        primary_relative = str(envelope.get("primary_payload_path", ""))
        if primary_relative not in local_hashes:
            return False
        try:
            primary_path = safe_relative_path(
                root,
                primary_relative,
                required_prefix="data",
                must_exist=True,
                require_file=True,
            )
            primary_payload = load_json_strict(primary_path)
        except (OSError, ValueError, json.JSONDecodeError):
            return False
        if not isinstance(primary_payload, dict):
            return False
        role_payloads[role] = primary_payload
        role_file_hashes[role] = local_hashes
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

    for role, payload in role_payloads.items():
        if not _formal_payload_identity_matches(
            payload,
            role=role,
            envelope=envelopes[role],
            benchmark_release_id=benchmark_release_id,
            scenario_id=scenario_id,
            domain_id=domain_id,
            family_id=family_id,
            instance_id=instance_id,
            variants=variants,
        ):
            return False

    tool_payload = role_payloads["tool_contract"]
    tools = tool_payload.get("tools")
    if not isinstance(tools, list) or not tools:
        return False
    tool_names: list[str] = []
    for tool in tools:
        if not isinstance(tool, dict):
            return False
        name = str(tool.get("name", ""))
        input_schema = _load_bound_json_payload(
            root,
            tool,
            path_field="input_schema_path",
            sha_field="input_schema_sha256",
            file_hashes=role_file_hashes["tool_contract"],
        )
        if (
            not name
            or input_schema is None
            or input_schema.get("type") != "object"
            or not isinstance(input_schema.get("properties"), dict)
            or not _payload_file_matches(
                tool,
                path_field="implementation_path",
                sha_field="implementation_sha256",
                file_hashes=role_file_hashes["tool_contract"],
            )
        ):
            return False
        tool_names.append(name)
    if len(tool_names) != len(set(tool_names)):
        return False

    evaluator_payload = role_payloads["evaluator"]
    checks = evaluator_payload.get("checks")
    scored_fields = evaluator_payload.get("scored_state_fields")
    if (
        not isinstance(checks, list)
        or not checks
        or not isinstance(scored_fields, list)
        or not scored_fields
        or not all(
            isinstance(value, str) and value for value in scored_fields
        )
    ):
        return False
    check_ids: list[str] = []
    for check in checks:
        if not isinstance(check, dict):
            return False
        check_id = str(check.get("id", ""))
        if (
            not check_id
            or not _payload_file_matches(
                check,
                path_field="implementation_path",
                sha_field="implementation_sha256",
                file_hashes=role_file_hashes["evaluator"],
            )
        ):
            return False
        check_ids.append(check_id)
    if len(check_ids) != len(set(check_ids)):
        return False

    reset_variants = _variant_payload_index(
        role_payloads["reset_evidence"],
        variants=variants,
    )
    boundary_variants = _variant_payload_index(
        role_payloads["boundary_bundle"],
        variants=variants,
    )
    reference_variants = _variant_payload_index(
        role_payloads["reference_bundle"],
        variants=variants,
    )
    if (
        reset_variants is None
        or boundary_variants is None
        or reference_variants is None
    ):
        return False
    for variant_id in variants:
        reset = reset_variants[variant_id]
        boundary = boundary_variants[variant_id]
        reference = reference_variants[variant_id]
        reset_snapshot = _load_bound_json_payload(
            root,
            reset,
            path_field="reset_snapshot_path",
            sha_field="reset_snapshot_sha256",
            file_hashes=role_file_hashes["reset_evidence"],
        )
        boundary_state = _load_bound_json_payload(
            root,
            boundary,
            path_field="boundary_state_path",
            sha_field="boundary_state_sha256",
            file_hashes=role_file_hashes["boundary_bundle"],
        )
        failure_surface = _load_bound_json_payload(
            root,
            boundary,
            path_field="failure_surface_path",
            sha_field="failure_surface_sha256",
            file_hashes=role_file_hashes["boundary_bundle"],
        )
        reference_start = _load_bound_json_payload(
            root,
            reference,
            path_field="reference_start_state_path",
            sha_field="reference_start_state_sha256",
            file_hashes=role_file_hashes["reference_bundle"],
        )
        reference_trace = _load_bound_json_payload(
            root,
            reference,
            path_field="reference_trace_path",
            sha_field="reference_trace_sha256",
            file_hashes=role_file_hashes["reference_bundle"],
        )
        terminal_state = _load_bound_json_payload(
            root,
            reference,
            path_field="terminal_state_path",
            sha_field="terminal_state_sha256",
            file_hashes=role_file_hashes["reference_bundle"],
        )
        if (
            reset.get("reset_verified") is not True
            or reset_snapshot is None
            or reset_snapshot.get("scenario_id") != scenario_id
            or reset_snapshot.get("variant_id") != variant_id
            or reset_snapshot.get("phase") != "reset"
            or reset_snapshot.get("reset_verified") is not True
            or boundary.get("boundary_validation_passed") is not True
            or boundary_state is None
            or boundary_state.get("scenario_id") != scenario_id
            or boundary_state.get("variant_id") != variant_id
            or boundary_state.get("phase") != "boundary"
            or bound_reset_snapshot_sha256(boundary_state)
            != reset.get("reset_snapshot_sha256")
            or failure_surface is None
            or failure_surface.get("scenario_id") != scenario_id
            or failure_surface.get("variant_id") != variant_id
            or failure_surface.get("phase") != "failure_surface"
            or not isinstance(failure_surface.get("operation"), str)
            or not failure_surface.get("operation")
            or not isinstance(
                failure_surface.get("surface_result"),
                str,
            )
            or not failure_surface.get("surface_result")
            or boundary.get("reset_snapshot_sha256")
            != reset.get("reset_snapshot_sha256")
            or reference.get("evaluator_passed") is not True
            or reference.get("boundary_state_sha256")
            != boundary.get("boundary_state_sha256")
            or reference.get("reference_start_state_sha256")
            != boundary.get("boundary_state_sha256")
            or reference_start is None
            or reference_start != boundary_state
            or reference_trace is None
            or reference_trace.get("scenario_id") != scenario_id
            or reference_trace.get("variant_id") != variant_id
            or reference_trace.get("phase") != "reference_trace"
            or reference_trace.get("boundary_state_sha256")
            != boundary.get("boundary_state_sha256")
            or reference_trace.get("input_envelope_sha256")
            != envelopes["reference_bundle"].get("depends_on")
            or not isinstance(reference_trace.get("steps"), list)
            or not reference_trace.get("steps")
            or terminal_state is None
            or terminal_state.get("scenario_id") != scenario_id
            or terminal_state.get("variant_id") != variant_id
            or terminal_state.get("phase") != "terminal"
            or terminal_state.get("boundary_state_sha256")
            != boundary.get("boundary_state_sha256")
            or terminal_state.get("evaluator_envelope_sha256")
            != envelope_hashes["evaluator"]
            or not isinstance(terminal_state.get("evaluation"), dict)
            or terminal_state["evaluation"].get("passed") is not True
        ):
            return False

    raw_payload = role_payloads["raw_run_archive"]
    runs = raw_payload.get("runs")
    if not isinstance(runs, list) or not runs:
        return False
    raw_runs: dict[str, dict[str, Any]] = {}
    observed_run_variants: set[str] = set()
    for run in runs:
        if not isinstance(run, dict):
            return False
        run_id = str(run.get("run_id", ""))
        variant_id = str(run.get("variant_id", ""))
        raw_run = _load_bound_json_payload(
            root,
            run,
            path_field="run_path",
            sha_field="run_sha256",
            file_hashes=role_file_hashes["raw_run_archive"],
        )
        if (
            not run_id
            or run_id in raw_runs
            or variant_id not in boundary_variants
            or type(run.get("execution_control")) is not bool
            or type(run.get("passed")) is not bool
            or run.get("boundary_state_sha256")
            != boundary_variants[variant_id].get("boundary_state_sha256")
            or not isinstance(run.get("summary_report_path"), str)
            or not run.get("summary_report_path")
            or raw_run is None
            or raw_run.get("scenario_id") != scenario_id
            or raw_run.get("variant_id") != variant_id
            or raw_run.get("run_id") != run_id
            or raw_run.get("boundary_state_sha256")
            != run.get("boundary_state_sha256")
            or raw_run.get("input_envelope_sha256")
            != envelopes["raw_run_archive"].get("depends_on")
            or raw_run.get("execution_control")
            is not run.get("execution_control")
            or raw_run.get("passed") is not run.get("passed")
            or raw_run.get("summary_report_path")
            != run.get("summary_report_path")
        ):
            return False
        raw_runs[run_id] = run
        observed_run_variants.add(variant_id)
    if observed_run_variants != set(variants):
        return False

    control_payload = role_payloads["execution_control"]
    run_ids = control_payload.get("run_ids")
    if (
        not isinstance(run_ids, list)
        or not run_ids
        or len(run_ids) != len(set(map(str, run_ids)))
    ):
        return False
    selected_runs: list[dict[str, Any]] = []
    for value in run_ids:
        run = raw_runs.get(str(value))
        if run is None or run.get("execution_control") is not True:
            return False
        selected_runs.append(run)
    if (
        len(selected_runs) != len(variants)
        or {str(run["variant_id"]) for run in selected_runs} != set(variants)
    ):
        return False
    try:
        completed_runs = int(control_payload.get("completed_runs", -1))
        passed_runs = int(control_payload.get("passed_runs", -1))
        task_pass_rate = float(control_payload.get("task_pass_rate", -1))
    except (TypeError, ValueError):
        return False
    computed_passed = sum(run.get("passed") is True for run in selected_runs)
    computed_rate = computed_passed / len(selected_runs)
    if (
        completed_runs != len(selected_runs)
        or passed_runs != computed_passed
        or abs(task_pass_rate - computed_rate) > 1e-12
        or task_pass_rate < MIN_EXECUTION_CONTROL_PASS_RATE
    ):
        return False

    declared_summary_path = str(
        control_payload.get("control_summary_path", "")
    )
    declared_summary_sha = str(
        control_payload.get("control_summary_sha256", "")
    )
    if (
        declared_summary_path != control_evidence_path
        or declared_summary_sha != control_evidence_sha256
        or not _payload_file_matches(
            control_payload,
            path_field="control_summary_path",
            sha_field="control_summary_sha256",
            file_hashes=role_file_hashes["execution_control"],
        )
    ):
        return False
    try:
        summary_path = safe_relative_path(
            root,
            declared_summary_path,
            required_prefix="data",
            must_exist=True,
            require_file=True,
        )
        summary = load_json_strict(summary_path)
    except (OSError, ValueError, json.JSONDecodeError):
        return False
    if not isinstance(summary, dict):
        return False
    reports = summary.get("reports")
    if not isinstance(reports, list):
        return False
    selected_by_summary_path = {
        str(run["summary_report_path"]): run for run in selected_runs
    }
    if (
        len(selected_by_summary_path) != len(selected_runs)
        or len(reports) != len(selected_runs)
    ):
        return False
    observed_summary_paths: set[str] = set()
    for report in reports:
        if not isinstance(report, dict):
            return False
        report_path = str(report.get("path", ""))
        run = selected_by_summary_path.get(report_path)
        if (
            run is None
            or report_path in observed_summary_paths
            or report.get("scenario_id") != scenario_id
            or report.get("variant") != run.get("variant_id")
            or report.get("passed") != run.get("passed")
        ):
            return False
        observed_summary_paths.add(report_path)
    try:
        summary_completed_runs = int(summary.get("completed_runs", -1))
        summary_task_pass_rate = float(
            summary.get("task_pass_rate", -1)
        )
        summary_control_runs = int(
            summary.get("execution_control_counts", {}).get("true", -1)
        )
    except (AttributeError, TypeError, ValueError):
        return False
    base_valid = not (
        summary_completed_runs != completed_runs
        or abs(summary_task_pass_rate - task_pass_rate) > 1e-12
        or summary.get("run_errors") != []
        or summary_control_runs != completed_runs
    )
    if not base_valid:
        return False
    if declarations_manifest_path is None:
        return True
    assert declarations_manifest_sha256 is not None
    return _validate_completed_formal_chain(
        root=root,
        declarations=declarations,
        benchmark_release_id=benchmark_release_id,
        scenario_id=scenario_id,
        domain_id=domain_id,
        family_id=family_id,
        instance_id=instance_id,
        variants=variants,
        control_evidence_path=control_evidence_path,
        control_evidence_sha256=control_evidence_sha256,
        declarations_manifest_path=declarations_manifest_path,
        declarations_manifest_sha256=declarations_manifest_sha256,
        role_payloads=role_payloads,
        role_file_hashes=role_file_hashes,
        envelopes=envelopes,
        envelope_hashes=envelope_hashes,
        require_trusted_evaluator=require_trusted_evaluator,
    )


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
                    "admission_input_artifact_sha256_match": False,
                    "admission_report_sha256_match": False,
                    "admission_artifact_sha256_match": False,
                    "admission_report_matches_recomputed": False,
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
            binding_checks.update(
                _validate_admission_release_binding(
                    scenario=scenario,
                    admission=admission,
                    declaration=declaration,
                )
            )
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
            control_evidence = dict(
                declaration.get("control_evidence", {})
            )
            formal_declarations = dict(
                declaration.get("formal_evidence_declarations", {})
            )
            formal_evidence_ready = validate_formal_evidence_roles(
                root=root,
                declarations=dict(declaration.get("formal_evidence", {})),
                benchmark_release_id=benchmark_release_id,
                scenario_id=declared_scenario_id,
                domain_id=domain_id,
                family_id=family_id,
                instance_id=instance_id,
                variants=variants,
                control_evidence_path=str(
                    control_evidence.get("path", "")
                ),
                control_evidence_sha256=str(
                    control_evidence.get("sha256", "")
                ),
                declarations_manifest_path=str(
                    formal_declarations.get("path", "")
                ),
                declarations_manifest_sha256=str(
                    formal_declarations.get("sha256", "")
                ),
                require_trusted_evaluator=True,
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
