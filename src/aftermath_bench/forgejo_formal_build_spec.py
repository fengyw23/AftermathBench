from __future__ import annotations

import hashlib
import json
import re
import subprocess
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .forgejo_publication_state_evidence import (
    canonical_state_fingerprint,
    deterministic_state_projection,
)
from .formal_evidence_builder import verify_formal_input_lock
from .integrations.forgejo_publication_faults import (
    FORGEJO_PUBLICATION_VARIANTS,
)
from .integrations.forgejo_publication_recovery import (
    ForgejoPublicationEnvironment,
)
from .native_admission import validate_native_scenario
from .native_forgejo_publication_family import (
    FORGEJO_PUBLICATION_TOOL_DEFINITIONS,
)
from .native_scenario import (
    NativeScenario,
    load_native_scenario,
    validate_native_scenario_document,
)
from .release_manifest import MIN_EXECUTION_CONTROL_PASS_RATE
from .strict_json import load_json_strict

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_GIT_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_IDENTIFIER = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
_FAMILY_ID = "forgejo-release-package-publication"
_DOMAIN_ID = "forgejo"
_RUNTIME_ID = "forgejo-main"
_SPLIT = "public_dev"
_TIER = "hard"
_ADMISSION_STATUS = "validated_hard"
_EXPECTED_VARIANT_COUNT = 8
_EXACT_MANIFEST_FIELDS = frozenset(
    {
        "schema_version",
        "excluded_files",
        "file_count",
        "total_bytes",
        "files",
    }
)
_EXACT_MANIFEST_ENTRY_FIELDS = frozenset({"path", "bytes", "sha256"})
_CAPTURE_BUNDLE_FIELDS = frozenset(
    {
        "schema_version",
        "capture_mode",
        "forgejo_sha256",
        "webhook_sink_sha256",
    }
)
_CAPTURE_MODE = "simultaneous_service_quiescence"
_TOOL_DEFINITION_SOURCE = "src/aftermath_bench/native_forgejo_publication_family.py"
_TOOL_IMPLEMENTATION_SOURCE = (
    "src/aftermath_bench/integrations/forgejo_publication_recovery.py"
)
_TOOL_IMPLEMENTATION_DEPENDENCIES = (
    "src/aftermath_bench/integrations/forgejo_api.py",
    "src/aftermath_bench/integrations/forgejo_web.py",
)
_NATIVE_RUNTIME_CONTRACT_SOURCES = (
    "runtimes/forgejo/runtime.lock.json",
    "runtimes/forgejo/compose.yaml",
    "runtimes/forgejo/control/Containerfile",
    "src/aftermath_bench/runtime_services/__init__.py",
    "src/aftermath_bench/runtime_services/gateway.py",
    "src/aftermath_bench/runtime_services/webhook_sink.py",
    "scripts/build_forgejo_runtime.py",
    "scripts/manage_forgejo_stack.py",
    "scripts/run_forgejo_publication_boundary.py",
    "scripts/capture_forgejo_publication_state_evidence.py",
    "src/aftermath_bench/integrations/forgejo_publication_faults.py",
)
_BOUNDARY_CONTRACT_SOURCES = (
    "scripts/run_forgejo_publication_boundary.py",
    "scripts/capture_forgejo_publication_state_evidence.py",
    "src/aftermath_bench/integrations/forgejo_publication_faults.py",
)
_RUNTIME_SOURCE_VERIFICATION = "runtime/source-verification.json"
_EVALUATOR_SOURCE = _TOOL_IMPLEMENTATION_SOURCE
_SCORED_STATE_FIELDS = (
    "releases",
    "target_release_assets",
    "coordinator_history",
    "provenance_history",
    "external_deliveries",
    "target_pull",
    "linked_issue",
    "release_milestone",
    "base_branch",
    "protected_pull",
    "protected_issue",
    "protected_release_assets",
    "branch_protections",
    "hooks",
)


class ForgejoFormalBuildSpecError(ValueError):
    """Raised when source evidence cannot support a formal build spec."""


@dataclass(frozen=True)
class _ExactManifest:
    path: Path
    relative_path: str
    root: Path
    entries: dict[str, dict[str, Any]]

    def require_file(self, path: Path, *, label: str) -> dict[str, Any]:
        try:
            relative = path.relative_to(self.root).as_posix()
        except ValueError as error:
            raise ForgejoFormalBuildSpecError(
                f"{label} is outside its exact bundle"
            ) from error
        entry = self.entries.get(relative)
        if entry is None:
            raise ForgejoFormalBuildSpecError(
                f"{label} is not bound by {self.relative_path}"
            )
        return entry


@dataclass(frozen=True)
class _VariantEvidence:
    variant_id: str
    reset_path: Path
    reset_relative: str
    reset: dict[str, Any]
    boundary_capture_path: Path
    boundary_capture_relative: str
    boundary_capture: dict[str, Any]
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
    pre_model_boundary: dict[str, Any] | None


@dataclass(frozen=True)
class ForgejoFormalBuildSpecResult:
    spec: dict[str, Any]
    scenario_path: str
    runtime_manifest_path: str
    control_manifest_path: str | None
    capture_bundle_manifest_paths: tuple[str, ...]


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _strict_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        value = load_json_strict(path)
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as error:
        raise ForgejoFormalBuildSpecError(
            f"{label} must be strict readable JSON"
        ) from error
    if not isinstance(value, dict):
        raise ForgejoFormalBuildSpecError(f"{label} must be a JSON object")
    return value


def _repo_file(
    root: Path,
    value: str | Path,
    *,
    label: str,
) -> tuple[Path, str]:
    source = Path(value)
    candidate = source if source.is_absolute() else root / source
    if ".." in source.parts:
        raise ForgejoFormalBuildSpecError(f"{label} must not contain parent traversal")
    try:
        resolved = candidate.resolve(strict=True)
        relative = resolved.relative_to(root).as_posix()
    except (OSError, ValueError) as error:
        raise ForgejoFormalBuildSpecError(
            f"{label} must be an existing file inside the repository root"
        ) from error
    if not resolved.is_file():
        raise ForgejoFormalBuildSpecError(f"{label} must be a regular file")
    for parent in (resolved, *resolved.parents):
        if parent == root.parent:
            break
        if parent.is_symlink():
            raise ForgejoFormalBuildSpecError(
                f"{label} must not traverse a symbolic link"
            )
        if parent == root:
            break
    return resolved, relative


def _repo_directory(
    root: Path,
    value: str | Path,
    *,
    label: str,
) -> tuple[Path, str]:
    source = Path(value)
    candidate = source if source.is_absolute() else root / source
    if ".." in source.parts:
        raise ForgejoFormalBuildSpecError(f"{label} must not contain parent traversal")
    try:
        resolved = candidate.resolve(strict=True)
        relative = resolved.relative_to(root).as_posix()
    except (OSError, ValueError) as error:
        raise ForgejoFormalBuildSpecError(
            f"{label} must be an existing directory inside the repository root"
        ) from error
    if not resolved.is_dir():
        raise ForgejoFormalBuildSpecError(f"{label} must be a directory")
    return resolved, relative


def _require_sha256(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise ForgejoFormalBuildSpecError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _require_identifier(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
        raise ForgejoFormalBuildSpecError(
            f"{label} must be a canonical lowercase identifier"
        )
    return value


def _current_git_commit(root: Path) -> str:
    try:
        process = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise ForgejoFormalBuildSpecError(
            "cannot determine the producer commit"
        ) from error
    commit = process.stdout.strip()
    if _GIT_COMMIT.fullmatch(commit) is None:
        raise ForgejoFormalBuildSpecError("repository HEAD is not a full Git commit")
    return commit


def _canonical_manifest_path(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ForgejoFormalBuildSpecError(f"{label} must be non-empty")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or path.as_posix() != value:
        raise ForgejoFormalBuildSpecError(
            f"{label} must be a canonical relative POSIX path"
        )
    return value


def _load_exact_manifest(
    root: Path,
    value: str | Path,
    *,
    label: str,
) -> _ExactManifest:
    path, relative = _repo_file(root, value, label=label)
    payload = _strict_object(path, label=label)
    if set(payload) != _EXACT_MANIFEST_FIELDS:
        raise ForgejoFormalBuildSpecError(f"{label} fields are not exact")
    if payload["schema_version"] != "0.1":
        raise ForgejoFormalBuildSpecError(f"{label} schema_version must be 0.1")
    excluded = payload["excluded_files"]
    files = payload["files"]
    if (
        not isinstance(excluded, list)
        or len(excluded) != len(set(map(str, excluded)))
        or not isinstance(files, list)
    ):
        raise ForgejoFormalBuildSpecError(f"{label} has an invalid file inventory")
    excluded_paths = {
        _canonical_manifest_path(item, label=f"{label} excluded_files[]")
        for item in excluded
    }
    manifest_relative = path.relative_to(path.parent).as_posix()
    if manifest_relative not in excluded_paths:
        raise ForgejoFormalBuildSpecError(f"{label} must explicitly exclude itself")

    entries: dict[str, dict[str, Any]] = {}
    ordered_paths: list[str] = []
    observed_total = 0
    for index, item in enumerate(files):
        if not isinstance(item, dict) or set(item) != _EXACT_MANIFEST_ENTRY_FIELDS:
            raise ForgejoFormalBuildSpecError(
                f"{label} files[{index}] fields are not exact"
            )
        item_path = _canonical_manifest_path(
            item["path"],
            label=f"{label} files[{index}].path",
        )
        if item_path in entries or item_path in excluded_paths:
            raise ForgejoFormalBuildSpecError(
                f"{label} contains duplicate or excluded file {item_path}"
            )
        try:
            size = int(item["bytes"])
        except (TypeError, ValueError) as error:
            raise ForgejoFormalBuildSpecError(
                f"{label} has an invalid byte length"
            ) from error
        digest = _require_sha256(
            item["sha256"],
            label=f"{label} files[{index}].sha256",
        )
        source = path.parent / item_path
        if not source.is_file():
            raise ForgejoFormalBuildSpecError(
                f"{label} is missing declared file {item_path}"
            )
        if source.stat().st_size != size or _sha256_file(source) != digest:
            raise ForgejoFormalBuildSpecError(
                f"{label} file bytes drifted for {item_path}"
            )
        entries[item_path] = {
            "path": item_path,
            "bytes": size,
            "sha256": digest,
        }
        ordered_paths.append(item_path)
        observed_total += size

    if ordered_paths != sorted(ordered_paths):
        raise ForgejoFormalBuildSpecError(f"{label} file paths must be sorted")
    actual = {
        candidate.relative_to(path.parent).as_posix()
        for candidate in path.parent.rglob("*")
        if candidate.is_file()
        and candidate.relative_to(path.parent).as_posix() not in excluded_paths
    }
    if actual != set(entries):
        raise ForgejoFormalBuildSpecError(
            f"{label} is not an exact inventory of its bundle"
        )
    try:
        declared_count = int(payload["file_count"])
        declared_total = int(payload["total_bytes"])
    except (TypeError, ValueError) as error:
        raise ForgejoFormalBuildSpecError(
            f"{label} aggregate fields are invalid"
        ) from error
    if declared_count != len(entries) or declared_total != observed_total:
        raise ForgejoFormalBuildSpecError(
            f"{label} aggregate fields do not match its files"
        )
    return _ExactManifest(
        path=path,
        relative_path=relative,
        root=path.parent,
        entries=entries,
    )


def _validate_native_runtime_contract(
    root: Path,
    runtime_manifest: _ExactManifest,
) -> tuple[str, str]:
    lock_path, _ = _repo_file(
        root,
        "runtimes/forgejo/runtime.lock.json",
        label="Forgejo runtime lock",
    )
    lock = _strict_object(lock_path, label="Forgejo runtime lock")
    source = lock.get("source")
    revision = source.get("revision") if isinstance(source, dict) else None
    if (
        not isinstance(revision, str)
        or _GIT_COMMIT.fullmatch(revision) is None
        or lock.get("base_image_digest_status") != "resolved"
        or lock.get("execution_status") != "source_checkout_with_pinned_build_plan"
    ):
        raise ForgejoFormalBuildSpecError(
            "Forgejo runtime lock is not a pinned source-build contract"
        )
    report_path = runtime_manifest.root / _RUNTIME_SOURCE_VERIFICATION
    if not report_path.is_file():
        raise ForgejoFormalBuildSpecError(
            "runtime source-verification report is missing"
        )
    runtime_manifest.require_file(
        report_path,
        label="runtime source-verification report",
    )
    report = _strict_object(
        report_path,
        label="runtime source-verification report",
    )
    plan = report.get("plan")
    verification = report.get("source_verification")
    image_build = report.get("image_build")
    if (
        not isinstance(plan, dict)
        or not isinstance(verification, dict)
        or not isinstance(image_build, dict)
        or plan.get("revision") != revision
        or plan.get("image") != lock.get("image")
        or verification.get("revision") != revision
        or verification.get("expected_revision") != revision
        or verification.get("passed") is not True
        or image_build.get("built_from_verified_revision") != revision
        or image_build.get("image") != lock.get("image")
    ):
        raise ForgejoFormalBuildSpecError(
            "runtime source-verification report disagrees with runtime.lock"
        )
    checks = verification.get("checks")
    actual_hashes = verification.get("actual_hashes")
    expected_hashes = plan.get("expected_hashes")
    if (
        not isinstance(checks, dict)
        or not checks
        or any(value is not True for value in checks.values())
        or not isinstance(actual_hashes, dict)
        or not isinstance(expected_hashes, list)
    ):
        raise ForgejoFormalBuildSpecError("runtime source verification is incomplete")
    expected_by_path: dict[str, str] = {}
    for item in expected_hashes:
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("path"), str)
            or _SHA256.fullmatch(str(item.get("sha256", ""))) is None
            or item["path"] in expected_by_path
        ):
            raise ForgejoFormalBuildSpecError(
                "runtime source expected hashes are invalid"
            )
        expected_by_path[item["path"]] = item["sha256"]
    if actual_hashes != expected_by_path:
        raise ForgejoFormalBuildSpecError(
            "runtime source hashes do not match the verified build plan"
        )
    pinned = verification.get("pinned_containerfile")
    if (
        not isinstance(pinned, dict)
        or pinned.get("all_digests_pinned") is not True
        or pinned.get("semantic_version_pinned") is not True
    ):
        raise ForgejoFormalBuildSpecError(
            "runtime source build did not pin its containerfile"
        )
    locked_images = {
        (str(item.get("reference")), str(item.get("digest")))
        for item in (
            lock.get("base_images", {}).values()
            if isinstance(lock.get("base_images"), dict)
            else ()
        )
        if isinstance(item, dict)
    }
    planned_images = {
        (str(item.get("reference")), str(item.get("digest")))
        for item in plan.get("base_images", [])
        if isinstance(item, dict)
    }
    if not locked_images or planned_images != locked_images:
        raise ForgejoFormalBuildSpecError(
            "runtime source build base images disagree with runtime.lock"
        )
    return revision, report_path.relative_to(root).as_posix()


def discover_active_forgejo_public_dev_scenario(
    root: str | Path,
) -> Path:
    resolved_root = Path(root).resolve()
    candidates: list[Path] = []
    for path in sorted((resolved_root / "data" / "scenarios").glob("*/scenario.json")):
        try:
            payload = load_json_strict(path)
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        if (
            payload.get("domain_id") == _DOMAIN_ID
            and payload.get("family") == _FAMILY_ID
            and payload.get("benchmark_split") == _SPLIT
            and payload.get("benchmark_tier") == _TIER
            and payload.get("admission_status") == _ADMISSION_STATUS
        ):
            candidates.append(path)
    if len(candidates) != 1:
        raise ForgejoFormalBuildSpecError(
            "expected exactly one active admitted Forgejo public_dev "
            f"scenario, found {len(candidates)}"
        )
    return candidates[0]


def _validate_active_scenario(
    root: Path,
    scenario_value: str | Path | None,
) -> tuple[NativeScenario, str, str]:
    scenario_source = (
        discover_active_forgejo_public_dev_scenario(root)
        if scenario_value is None
        else scenario_value
    )
    scenario_path, scenario_relative = _repo_file(
        root,
        scenario_source,
        label="scenario",
    )
    if (
        Path(scenario_relative).parts[:2] != ("data", "scenarios")
        or Path(scenario_relative).name != "scenario.json"
        or len(Path(scenario_relative).parts) != 4
    ):
        raise ForgejoFormalBuildSpecError(
            "scenario must be an active data/scenarios entry"
        )
    scenario = load_native_scenario(scenario_path)
    document_failures = validate_native_scenario_document(scenario)
    if document_failures:
        raise ForgejoFormalBuildSpecError(
            "scenario document is invalid: " + ", ".join(document_failures)
        )
    if (
        scenario.domain_id != _DOMAIN_ID
        or scenario.family_id != _FAMILY_ID
        or scenario.raw.get("runtime_id") != _RUNTIME_ID
        or scenario.split != _SPLIT
        or scenario.tier != _TIER
        or scenario.raw.get("admission_status") != _ADMISSION_STATUS
    ):
        raise ForgejoFormalBuildSpecError(
            "scenario is not the active admitted Forgejo public_dev family"
        )
    if scenario.path.parent.name != scenario.scenario_id:
        raise ForgejoFormalBuildSpecError(
            "active scenario directory must equal scenario_id"
        )
    if (
        len(scenario.variants) != _EXPECTED_VARIANT_COUNT
        or scenario.variants != tuple(FORGEJO_PUBLICATION_VARIANTS)
        or len(set(scenario.variants)) != _EXPECTED_VARIANT_COUNT
    ):
        raise ForgejoFormalBuildSpecError(
            "Forgejo public_dev must contain the canonical eight variants"
        )
    admission = validate_native_scenario(scenario)
    if (
        not admission.passed
        or admission.admitted_tier != _TIER
        or admission.scenario_id != scenario.scenario_id
    ):
        raise ForgejoFormalBuildSpecError(
            "scenario does not pass replay-derived hard admission"
        )
    instance_spec_sha256 = _require_sha256(
        scenario.raw.get("instance_spec_sha256"),
        label="scenario instance_spec_sha256",
    )
    return scenario, scenario_relative, instance_spec_sha256


def _variant_identity(
    payload: dict[str, Any],
    *,
    label: str,
) -> str:
    legacy = payload.get("variant")
    canonical = payload.get("variant_id")
    if legacy is not None and canonical is not None and legacy != canonical:
        raise ForgejoFormalBuildSpecError(f"{label} has conflicting variant identities")
    value = canonical if canonical is not None else legacy
    if not isinstance(value, str) or not value:
        raise ForgejoFormalBuildSpecError(f"{label} has no variant identity")
    return value


def _validate_identity(
    payload: dict[str, Any],
    *,
    scenario: NativeScenario,
    instance_spec_sha256: str,
    variant_id: str,
    label: str,
    require_instance: bool = True,
) -> None:
    if (
        payload.get("scenario_id") != scenario.scenario_id
        or _variant_identity(payload, label=label) != variant_id
    ):
        raise ForgejoFormalBuildSpecError(
            f"{label} identity does not match the scenario variant"
        )
    observed_instance = payload.get("instance_spec_sha256")
    if require_instance and observed_instance != instance_spec_sha256:
        raise ForgejoFormalBuildSpecError(
            f"{label} instance_spec_sha256 does not match the scenario"
        )
    if observed_instance is not None and observed_instance != instance_spec_sha256:
        raise ForgejoFormalBuildSpecError(
            f"{label} has a conflicting instance_spec_sha256"
        )


def _validate_true_checks(value: Any, *, label: str) -> dict[str, bool]:
    if (
        not isinstance(value, dict)
        or not value
        or any(
            not isinstance(key, str) or not key or passed is not True
            for key, passed in value.items()
        )
    ):
        raise ForgejoFormalBuildSpecError(
            f"{label} must contain only passing deterministic checks"
        )
    return value


def _validate_boolean_checks(
    value: Any,
    *,
    label: str,
) -> dict[str, bool]:
    if (
        not isinstance(value, dict)
        or not value
        or any(
            not isinstance(key, str) or not key or not isinstance(passed, bool)
            for key, passed in value.items()
        )
    ):
        raise ForgejoFormalBuildSpecError(
            f"{label} must contain deterministic boolean checks"
        )
    return value


def _load_capture_bundle_manifests(
    root: Path,
    values: Iterable[str | Path],
) -> dict[str, tuple[str, dict[str, Any]]]:
    manifests: dict[str, tuple[str, dict[str, Any]]] = {}
    for index, value in enumerate(values):
        path, relative = _repo_file(
            root,
            value,
            label=f"capture bundle manifest[{index}]",
        )
        payload = _strict_object(
            path,
            label=f"capture bundle manifest[{index}]",
        )
        if (
            set(payload) != _CAPTURE_BUNDLE_FIELDS
            or payload.get("schema_version") != "1.0"
            or payload.get("capture_mode") != _CAPTURE_MODE
        ):
            raise ForgejoFormalBuildSpecError(
                "capture bundle manifest fields or capture mode are invalid"
            )
        _require_sha256(
            payload.get("forgejo_sha256"),
            label="capture bundle forgejo_sha256",
        )
        _require_sha256(
            payload.get("webhook_sink_sha256"),
            label="capture bundle webhook_sink_sha256",
        )
        digest = _sha256_file(path)
        if digest in manifests:
            raise ForgejoFormalBuildSpecError(
                "capture bundle manifests must have unique bytes"
            )
        manifests[digest] = (relative, payload)
    if not manifests:
        raise ForgejoFormalBuildSpecError(
            "at least one exact capture bundle manifest is required"
        )
    return manifests


def _validate_capture_bundle(
    capture: dict[str, Any],
    *,
    manifests: dict[str, tuple[str, dict[str, Any]]],
    label: str,
) -> str:
    manifest_digest = _require_sha256(
        capture.get("bundle_manifest_file_sha256"),
        label=f"{label} bundle_manifest_file_sha256",
    )
    selected = manifests.get(manifest_digest)
    if selected is None:
        raise ForgejoFormalBuildSpecError(
            f"{label} references an undeclared exact bundle manifest"
        )
    relative, manifest = selected
    bundle = capture.get("bundle")
    if (
        not isinstance(bundle, dict)
        or bundle.get("manifest_file_sha256") != manifest_digest
        or deterministic_state_projection(bundle.get("manifest"))
        != deterministic_state_projection(manifest)
    ):
        raise ForgejoFormalBuildSpecError(
            f"{label} embedded bundle does not match its exact manifest"
        )
    forgejo = bundle.get("forgejo_archive")
    sink = bundle.get("webhook_sink_archive")
    if not isinstance(forgejo, dict) or not isinstance(sink, dict):
        raise ForgejoFormalBuildSpecError(f"{label} lacks exact archive bindings")
    for role, record, expected in (
        ("forgejo", forgejo, manifest["forgejo_sha256"]),
        ("webhook_sink", sink, manifest["webhook_sink_sha256"]),
    ):
        if (
            record.get("sha256") != expected
            or type(record.get("size_bytes")) is not int
            or record["size_bytes"] <= 0
        ):
            raise ForgejoFormalBuildSpecError(
                f"{label} has an invalid {role} archive binding"
            )
    return relative


def _validate_reset_capture(
    capture: dict[str, Any],
    *,
    path: Path,
    scenario: NativeScenario,
    instance_spec_sha256: str,
    variant_id: str,
    prefix_sha256: str,
    bundle_manifests: dict[str, tuple[str, dict[str, Any]]],
) -> str:
    label = f"reset capture {variant_id}"
    _validate_identity(
        capture,
        scenario=scenario,
        instance_spec_sha256=instance_spec_sha256,
        variant_id=variant_id,
        label=label,
    )
    if (
        capture.get("schema_version") != "1.0"
        or capture.get("artifact_type") != "forgejo_publication_native_state_projection"
        or capture.get("phase") != "reset"
        or capture.get("reset_verified") is not True
        or capture.get("prefix_file_sha256") != prefix_sha256
    ):
        raise ForgejoFormalBuildSpecError(f"{label} is not a verified canonical reset")
    expected = capture.get("expected_projection")
    projection = capture.get("state_projection")
    if (
        not isinstance(expected, dict)
        or expected.get("provided") is not True
        or expected.get("exact_match") is not True
        or not isinstance(projection, dict)
        or capture.get("state_fingerprint")
        != canonical_state_fingerprint(deterministic_state_projection(projection))
    ):
        raise ForgejoFormalBuildSpecError(
            f"{label} lacks an exact deterministic state projection"
        )
    del path
    return _validate_capture_bundle(
        capture,
        manifests=bundle_manifests,
        label=label,
    )


def _validate_raw_boundary(
    payload: dict[str, Any],
    *,
    scenario: NativeScenario,
    instance_spec_sha256: str,
    variant_id: str,
) -> tuple[str, dict[str, Any]]:
    label = f"raw boundary {variant_id}"
    _validate_identity(
        payload,
        scenario=scenario,
        instance_spec_sha256=instance_spec_sha256,
        variant_id=variant_id,
        label=label,
    )
    if payload.get("passed") is not True:
        raise ForgejoFormalBuildSpecError(f"{label} did not pass")
    _validate_true_checks(payload.get("checks"), label=f"{label} checks")
    surface = payload.get("surface_result")
    visible = payload.get("visible_failure")
    if (
        surface != scenario.raw["ambiguous_operation"]["surface_result"]
        or not isinstance(visible, dict)
        or visible.get("ok") is not False
        or visible.get("error") != surface
    ):
        raise ForgejoFormalBuildSpecError(
            f"{label} does not expose the registered ambiguous failure"
        )
    return surface, visible


def _validate_boundary_capture(
    capture: dict[str, Any],
    *,
    path: Path,
    reset_path: Path,
    raw_boundary_path: Path,
    raw_boundary: dict[str, Any],
    scenario: NativeScenario,
    instance_spec_sha256: str,
    variant_id: str,
    prefix_sha256: str,
    bundle_manifests: dict[str, tuple[str, dict[str, Any]]],
) -> str:
    label = f"boundary capture {variant_id}"
    _validate_identity(
        capture,
        scenario=scenario,
        instance_spec_sha256=instance_spec_sha256,
        variant_id=variant_id,
        label=label,
    )
    surface, visible = _validate_raw_boundary(
        raw_boundary,
        scenario=scenario,
        instance_spec_sha256=instance_spec_sha256,
        variant_id=variant_id,
    )
    projection = capture.get("state_projection")
    if (
        capture.get("schema_version") != "1.0"
        or capture.get("artifact_type") != "forgejo_publication_native_state_projection"
        or capture.get("phase") != "boundary"
        or capture.get("boundary_validation_passed") is not True
        or capture.get("prefix_file_sha256") != prefix_sha256
        or capture.get("reset_snapshot_sha256") != _sha256_file(reset_path)
        or capture.get("failure_report_file_sha256") != _sha256_file(raw_boundary_path)
        or capture.get("surface_result") != surface
        or deterministic_state_projection(capture.get("visible_failure"))
        != deterministic_state_projection(visible)
        or not isinstance(projection, dict)
        or capture.get("state_fingerprint")
        != canonical_state_fingerprint(deterministic_state_projection(projection))
    ):
        raise ForgejoFormalBuildSpecError(
            f"{label} is not cross-bound to reset, failure, and native state"
        )
    del path
    return _validate_capture_bundle(
        capture,
        manifests=bundle_manifests,
        label=label,
    )


def _validate_reference(
    payload: dict[str, Any],
    *,
    scenario: NativeScenario,
    instance_spec_sha256: str,
    variant_id: str,
) -> tuple[str, ...]:
    label = f"reference report {variant_id}"
    _validate_identity(
        payload,
        scenario=scenario,
        instance_spec_sha256=instance_spec_sha256,
        variant_id=variant_id,
        label=label,
    )
    trace = payload.get("reference_trace")
    evaluation = payload.get("evaluation")
    if (
        not isinstance(trace, list)
        or not trace
        or payload.get("control_error") is not None
        or not isinstance(payload.get("final_evidence"), dict)
        or not isinstance(evaluation, dict)
        or evaluation.get("passed") is not True
    ):
        raise ForgejoFormalBuildSpecError(
            f"{label} is not a complete passing deterministic recovery"
        )
    checks = _validate_true_checks(
        evaluation.get("checks"),
        label=f"{label} evaluator checks",
    )
    components = _validate_true_checks(
        evaluation.get("components"),
        label=f"{label} evaluator components",
    )
    del components
    known_tools = set(ForgejoPublicationEnvironment.TOOL_NAMES)
    for index, event in enumerate(trace):
        if (
            not isinstance(event, dict)
            or event.get("tool") not in known_tools
            or not isinstance(event.get("arguments"), dict)
            or "result" not in event
        ):
            raise ForgejoFormalBuildSpecError(
                f"{label} trace[{index}] is not a public-tool event"
            )
    return tuple(sorted(checks))


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
    label = f"execution-control trajectory {variant_id}"
    _validate_identity(
        payload,
        scenario=scenario,
        instance_spec_sha256=instance_spec_sha256,
        variant_id=variant_id,
        label=label,
    )
    evaluation = payload.get("evaluation")
    if (
        payload.get("domain") != scenario.domain_id
        or payload.get("family") != scenario.family_id
        or payload.get("instance_id") != scenario.instance_id
        or payload.get("execution_control") is not True
        or not isinstance(payload.get("run_id"), str)
        or not payload["run_id"]
        or not isinstance(evaluation, dict)
        or not isinstance(evaluation.get("passed"), bool)
        or deterministic_state_projection(payload.get("surface_failure"))
        != deterministic_state_projection(raw_boundary.get("visible_failure"))
    ):
        raise ForgejoFormalBuildSpecError(
            f"{label} is not a complete explicit execution control"
        )
    checks = _validate_boolean_checks(
        evaluation.get("checks"),
        label=f"{label} evaluator checks",
    )
    components = _validate_boolean_checks(
        evaluation.get("components"),
        label=f"{label} evaluator components",
    )
    if evaluation["passed"] is not (all(checks.values()) and all(components.values())):
        raise ForgejoFormalBuildSpecError(
            f"{label} pass result conflicts with deterministic checks"
        )
    if not isinstance(payload.get("turns"), list) or not payload["turns"]:
        raise ForgejoFormalBuildSpecError(
            f"{label} lacks a complete raw model trajectory"
        )
    recorded_lock = payload.get("formal_input_lock")
    if not isinstance(recorded_lock, dict):
        raise ForgejoFormalBuildSpecError(
            f"{label} lacks its verified formal input lock"
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
        raise ForgejoFormalBuildSpecError(
            f"{label} formal input lock does not exactly match "
            "the verified variant boundary"
        )
    return payload["run_id"]


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
        or len(reports) != _EXPECTED_VARIANT_COUNT
        or payload.get("completed_runs") != _EXPECTED_VARIANT_COUNT
        or payload.get("run_errors") != []
        or not isinstance(counts, dict)
        or counts.get("true") != _EXPECTED_VARIANT_COUNT
    ):
        raise ForgejoFormalBuildSpecError("execution-control summary is incomplete")
    passed_count = sum(
        trajectory.get("evaluation", {}).get("passed") is True
        for trajectory in trajectories.values()
    )
    expected_rate = passed_count / _EXPECTED_VARIANT_COUNT
    try:
        observed_rate = float(payload.get("task_pass_rate", -1))
    except (TypeError, ValueError) as error:
        raise ForgejoFormalBuildSpecError(
            "execution-control summary pass rate is invalid"
        ) from error
    if (
        abs(observed_rate - expected_rate) > 1e-12
        or observed_rate < MIN_EXECUTION_CONTROL_PASS_RATE
    ):
        raise ForgejoFormalBuildSpecError(
            "execution-control summary is below or inconsistent with "
            "the required pass rate"
        )
    observed: dict[str, dict[str, Any]] = {}
    for index, report in enumerate(reports):
        if not isinstance(report, dict):
            raise ForgejoFormalBuildSpecError(
                f"execution-control summary reports[{index}] is invalid"
            )
        variant_id = str(report.get("variant", ""))
        if (
            variant_id not in scenario.variants
            or variant_id in observed
            or report.get("scenario_id") != scenario.scenario_id
            or not isinstance(report.get("passed"), bool)
            or not isinstance(report.get("path"), str)
            or Path(report["path"]).name != f"{variant_id}.json"
        ):
            raise ForgejoFormalBuildSpecError(
                "execution-control summary report identity is invalid"
            )
        trajectory = trajectories.get(variant_id)
        if (
            trajectory is None
            or trajectory.get("execution_control") is not True
            or report.get("passed")
            is not trajectory.get("evaluation", {}).get("passed")
        ):
            raise ForgejoFormalBuildSpecError(
                "execution-control summary does not match raw trajectories"
            )
        observed[variant_id] = report
    if set(observed) != set(scenario.variants):
        raise ForgejoFormalBuildSpecError(
            "execution-control summary does not cover all eight variants"
        )


def _collect_variant_evidence(
    *,
    root: Path,
    scenario: NativeScenario,
    instance_spec_sha256: str,
    runtime_manifest: _ExactManifest,
    control_manifest: _ExactManifest | None,
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
    try:
        prefix_path.resolve().relative_to(root)
    except ValueError as error:
        raise ForgejoFormalBuildSpecError(
            "scenario prefix is outside the repository root"
        ) from error
    if not prefix_path.is_file():
        raise ForgejoFormalBuildSpecError("scenario prefix artifact is missing")
    prefix_sha256 = _sha256_file(prefix_path)
    evidence: list[_VariantEvidence] = []
    evaluator_check_ids: tuple[str, ...] | None = None
    run_ids: set[str] = set()
    used_capture_manifests: dict[str, set[str]] = {
        "reset": set(),
        "boundary": set(),
    }
    trajectories: dict[str, dict[str, Any]] = {}

    for variant_id in scenario.variants:
        reset_path, reset_relative = _repo_file(
            root,
            capture_directory / f"{variant_id}-reset.json",
            label=f"reset capture {variant_id}",
        )
        boundary_capture_path, boundary_capture_relative = _repo_file(
            root,
            capture_directory / f"{variant_id}-boundary.json",
            label=f"boundary capture {variant_id}",
        )
        reference_start_path, reference_start_relative = _repo_file(
            root,
            capture_directory / f"{variant_id}-reference-start.json",
            label=f"reference-start capture {variant_id}",
        )
        raw_boundary_path = (
            runtime_manifest.root / "runtime" / f"{variant_id}-boundary.json"
        )
        raw_reference_path = (
            runtime_manifest.root / "runtime" / f"{variant_id}-reference.json"
        )
        for selected, label in (
            (raw_boundary_path, f"raw boundary {variant_id}"),
            (raw_reference_path, f"raw reference {variant_id}"),
        ):
            if not selected.is_file():
                raise ForgejoFormalBuildSpecError(f"{label} is missing")

        runtime_manifest.require_file(
            raw_boundary_path,
            label=f"raw boundary {variant_id}",
        )
        runtime_manifest.require_file(
            raw_reference_path,
            label=f"raw reference {variant_id}",
        )
        runtime_manifest.require_file(
            reference_start_path,
            label=f"reference-start capture {variant_id}",
        )
        raw_boundary_relative = raw_boundary_path.relative_to(root).as_posix()
        raw_reference_relative = raw_reference_path.relative_to(root).as_posix()

        reset = _strict_object(
            reset_path,
            label=f"reset capture {variant_id}",
        )
        boundary_capture = _strict_object(
            boundary_capture_path,
            label=f"boundary capture {variant_id}",
        )
        raw_boundary = _strict_object(
            raw_boundary_path,
            label=f"raw boundary {variant_id}",
        )
        raw_reference = _strict_object(
            raw_reference_path,
            label=f"raw reference {variant_id}",
        )
        reference_start = _strict_object(
            reference_start_path,
            label=f"reference-start capture {variant_id}",
        )
        if reference_start_path.read_bytes() != boundary_capture_path.read_bytes():
            raise ForgejoFormalBuildSpecError(
                f"reference-start capture {variant_id} does not exactly "
                "match the admitted boundary"
            )
        trajectory_path: Path | None = None
        trajectory_relative: str | None = None
        trajectory: dict[str, Any] | None = None
        pre_model_boundary_path: Path | None = None
        pre_model_boundary_relative: str | None = None
        pre_model_boundary: dict[str, Any] | None = None
        if control_manifest is not None:
            trajectory_path = (
                control_manifest.root
                / "model-runs"
                / "repetition-01"
                / f"{variant_id}.json"
            )
            if not trajectory_path.is_file():
                raise ForgejoFormalBuildSpecError(
                    f"execution-control trajectory {variant_id} is missing"
                )
            control_manifest.require_file(
                trajectory_path,
                label=f"execution-control trajectory {variant_id}",
            )
            trajectory_relative = trajectory_path.relative_to(root).as_posix()
            trajectory = _strict_object(
                trajectory_path,
                label=f"execution-control trajectory {variant_id}",
            )
            pre_model_boundary_path = (
                control_manifest.root
                / "pre-model-boundaries"
                / f"{variant_id}-boundary.json"
            )
            if not pre_model_boundary_path.is_file():
                raise ForgejoFormalBuildSpecError(
                    f"pre-model boundary evidence {variant_id} is missing"
                )
            control_manifest.require_file(
                pre_model_boundary_path,
                label=f"pre-model boundary evidence {variant_id}",
            )
            pre_model_boundary_relative = pre_model_boundary_path.relative_to(
                root
            ).as_posix()
            pre_model_boundary = _strict_object(
                pre_model_boundary_path,
                label=f"pre-model boundary evidence {variant_id}",
            )
            if (
                pre_model_boundary_path.read_bytes()
                != boundary_capture_path.read_bytes()
            ):
                raise ForgejoFormalBuildSpecError(
                    f"pre-model boundary evidence {variant_id} does not "
                    "exactly match the admitted boundary"
                )
            recorded_pre_model = trajectory.get("pre_model_boundary_evidence")
            pre_model_sha256 = _sha256_file(pre_model_boundary_path)
            if (
                not isinstance(recorded_pre_model, dict)
                or set(recorded_pre_model)
                != {"variant_id", "source_basename", "sha256"}
                or recorded_pre_model.get("variant_id") != variant_id
                or recorded_pre_model.get("source_basename")
                != pre_model_boundary_path.name
                or recorded_pre_model.get("sha256") != pre_model_sha256
            ):
                raise ForgejoFormalBuildSpecError(
                    f"execution-control trajectory {variant_id} does not "
                    "bind its persisted pre-model boundary evidence"
                )

        reset_manifest = _validate_reset_capture(
            reset,
            path=reset_path,
            scenario=scenario,
            instance_spec_sha256=instance_spec_sha256,
            variant_id=variant_id,
            prefix_sha256=prefix_sha256,
            bundle_manifests=bundle_manifests,
        )
        boundary_manifest = _validate_boundary_capture(
            boundary_capture,
            path=boundary_capture_path,
            reset_path=reset_path,
            raw_boundary_path=raw_boundary_path,
            raw_boundary=raw_boundary,
            scenario=scenario,
            instance_spec_sha256=instance_spec_sha256,
            variant_id=variant_id,
            prefix_sha256=prefix_sha256,
            bundle_manifests=bundle_manifests,
        )
        used_capture_manifests["reset"].add(reset_manifest)
        used_capture_manifests["boundary"].add(boundary_manifest)

        current_check_ids = _validate_reference(
            raw_reference,
            scenario=scenario,
            instance_spec_sha256=instance_spec_sha256,
            variant_id=variant_id,
        )
        if evaluator_check_ids is None:
            evaluator_check_ids = current_check_ids
        elif evaluator_check_ids != current_check_ids:
            raise ForgejoFormalBuildSpecError(
                "reference reports do not expose one complete evaluator check set"
            )
        if trajectory is not None:
            if formal_input_lock_path is None:
                raise ForgejoFormalBuildSpecError(
                    "execution-control evidence requires a formal input lock"
                )
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
                raise ForgejoFormalBuildSpecError(
                    "execution-control run IDs must be unique"
                )
            run_ids.add(run_id)
            trajectories[variant_id] = trajectory
        evidence.append(
            _VariantEvidence(
                variant_id=variant_id,
                reset_path=reset_path,
                reset_relative=reset_relative,
                reset=reset,
                boundary_capture_path=boundary_capture_path,
                boundary_capture_relative=boundary_capture_relative,
                boundary_capture=boundary_capture,
                raw_boundary_path=raw_boundary_path,
                raw_boundary_relative=raw_boundary_relative,
                raw_boundary=raw_boundary,
                raw_reference_path=raw_reference_path,
                raw_reference_relative=raw_reference_relative,
                raw_reference=raw_reference,
                reference_start_path=reference_start_path,
                reference_start_relative=reference_start_relative,
                reference_start=reference_start,
                trajectory_path=trajectory_path,
                trajectory_relative=trajectory_relative,
                trajectory=trajectory,
                pre_model_boundary_path=pre_model_boundary_path,
                pre_model_boundary_relative=pre_model_boundary_relative,
                pre_model_boundary=pre_model_boundary,
            )
        )

    if control_manifest is not None:
        summary_path = control_manifest.root / "model-runs" / "summary.json"
        if not summary_path.is_file():
            raise ForgejoFormalBuildSpecError("execution-control summary is missing")
        control_manifest.require_file(
            summary_path,
            label="execution-control summary",
        )
        _validate_control_summary(
            _strict_object(
                summary_path,
                label="execution-control summary",
            ),
            scenario=scenario,
            trajectories=trajectories,
        )
    if evaluator_check_ids is None:
        raise ForgejoFormalBuildSpecError(
            "no deterministic evaluator checks were observed"
        )
    declared_manifest_paths = {relative for relative, _ in bundle_manifests.values()}
    used_manifest_paths = (
        used_capture_manifests["reset"] | used_capture_manifests["boundary"]
    )
    if used_manifest_paths != declared_manifest_paths:
        raise ForgejoFormalBuildSpecError(
            "capture bundle manifest inputs must all be used"
        )
    return (
        tuple(evidence),
        evaluator_check_ids,
        {
            phase: tuple(sorted(paths))
            for phase, paths in used_capture_manifests.items()
        },
    )


def _role_root(output: str, role: str) -> str:
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
    raise ForgejoFormalBuildSpecError(f"unknown formal role {role}")


def _support(output: str, role: str, name: str) -> str:
    return f"{_role_root(output, role)}/support/{name}"


def _file_sha256(path: str) -> dict[str, str]:
    return {"$file_sha256": path}


def _envelope_sha256(role: str) -> dict[str, str]:
    return {"$envelope_sha256": role}


def _role_dependencies(role: str) -> dict[str, str]:
    return {"$role_dependencies": role}


def _identity(field: str) -> dict[str, str]:
    return {"$identity": field}


def _bound_json_field(path: str, field: str) -> dict[str, dict[str, str]]:
    return {"$bound_json_field": {"path": path, "field": field}}


def _formal_input_lock_sha256() -> dict[str, bool]:
    return {"$formal_input_lock_sha256": True}


def _validate_output_directory(root: Path, value: str) -> str:
    path = Path(value)
    if (
        path.is_absolute()
        or ".." in path.parts
        or path.as_posix() != value
        or len(path.parts) < 3
        or path.parts[0] != "data"
    ):
        raise ForgejoFormalBuildSpecError(
            "output_directory must be a canonical path below data/"
        )
    try:
        (root / path).resolve().relative_to(root)
    except ValueError as error:
        raise ForgejoFormalBuildSpecError(
            "output_directory escapes the repository root"
        ) from error
    return value


def _source_support(path: str, source_path: str) -> dict[str, str]:
    return {"path": path, "source_path": source_path}


def _json_support(path: str, value: Any) -> dict[str, Any]:
    return {"path": path, "json_content": value}


def _build_tool_contract_role(
    *,
    root: Path,
    output: str,
    runtime_revision: str,
    source_verification_relative: str,
) -> dict[str, Any]:
    definition_source, definition_relative = _repo_file(
        root,
        _TOOL_DEFINITION_SOURCE,
        label="Forgejo tool-definition source",
    )
    implementation_source, implementation_relative = _repo_file(
        root,
        _TOOL_IMPLEMENTATION_SOURCE,
        label="Forgejo tool-implementation source",
    )
    del definition_source, implementation_source
    dependency_sources = [
        _repo_file(
            root,
            relative,
            label=f"Forgejo tool dependency {relative}",
        )[1]
        for relative in _TOOL_IMPLEMENTATION_DEPENDENCIES
    ]
    tools = tuple(FORGEJO_PUBLICATION_TOOL_DEFINITIONS)
    names = tuple(tool.name for tool in tools)
    if (
        len(tools) != 17
        or names != tuple(ForgejoPublicationEnvironment.TOOL_NAMES)
        or len(names) != len(set(names))
    ):
        raise ForgejoFormalBuildSpecError(
            "Forgejo public tool registry is not the expected 17-tool surface"
        )

    definition_output = _support(
        output,
        "tool_contract",
        "sources/native_forgejo_publication_family.py",
    )
    implementation_output = _support(
        output,
        "tool_contract",
        "sources/forgejo_publication_recovery.py",
    )
    dependency_outputs = {
        source: _support(
            output,
            "tool_contract",
            f"sources/{Path(source).name}",
        )
        for source in dependency_sources
    }
    schema_outputs = {
        tool.name: _support(
            output,
            "tool_contract",
            f"schemas/{tool.name}.json",
        )
        for tool in tools
    }
    implementation_dependencies = [
        {
            "path": dependency_outputs[source],
            "sha256": _file_sha256(dependency_outputs[source]),
        }
        for source in dependency_sources
    ]
    runtime_sources = [
        _repo_file(
            root,
            relative,
            label=f"Forgejo native runtime source {relative}",
        )[1]
        for relative in _NATIVE_RUNTIME_CONTRACT_SOURCES
    ]
    runtime_outputs = {
        source: _support(
            output,
            "tool_contract",
            f"native-runtime/{index:02d}-{Path(source).name}",
        )
        for index, source in enumerate(runtime_sources, start=1)
    }
    verification_output = _support(
        output,
        "tool_contract",
        "native-runtime/source-verification.json",
    )
    return {
        "primary_payload": {
            "tool_count": len(tools),
            "definition_source_path": definition_output,
            "definition_source_sha256": _file_sha256(definition_output),
            "implementation_dependencies": implementation_dependencies,
            "native_runtime_contract": {
                "revision": runtime_revision,
                "source_verification_path": verification_output,
                "source_verification_sha256": _file_sha256(verification_output),
                "files": [
                    {
                        "source_path": source,
                        "path": runtime_outputs[source],
                        "sha256": _file_sha256(runtime_outputs[source]),
                    }
                    for source in runtime_sources
                ],
            },
            "tools": [
                {
                    "name": tool.name,
                    "description": tool.description,
                    "input_schema_path": schema_outputs[tool.name],
                    "input_schema_sha256": _file_sha256(schema_outputs[tool.name]),
                    "definition_source_path": definition_output,
                    "definition_source_sha256": _file_sha256(definition_output),
                    "implementation_path": implementation_output,
                    "implementation_sha256": _file_sha256(implementation_output),
                    "implementation_symbol": ("ForgejoPublicationEnvironment.invoke"),
                    "implementation_dependencies": (implementation_dependencies),
                }
                for tool in tools
            ],
        },
        "support_files": [
            _source_support(definition_output, definition_relative),
            _source_support(
                implementation_output,
                implementation_relative,
            ),
            *[
                _source_support(dependency_outputs[source], source)
                for source in dependency_sources
            ],
            _source_support(
                verification_output,
                source_verification_relative,
            ),
            *[
                _source_support(runtime_outputs[source], source)
                for source in runtime_sources
            ],
            *[
                _json_support(
                    schema_outputs[tool.name],
                    tool.input_schema,
                )
                for tool in tools
            ],
        ],
    }


def _build_evaluator_role(
    *,
    root: Path,
    output: str,
    check_ids: tuple[str, ...],
) -> dict[str, Any]:
    _, source_relative = _repo_file(
        root,
        _EVALUATOR_SOURCE,
        label="Forgejo deterministic evaluator source",
    )
    implementation_output = _support(
        output,
        "evaluator",
        "sources/forgejo_publication_recovery.py",
    )
    return {
        "primary_payload": {
            "implementation_symbol": ("evaluate_forgejo_publication_recovery"),
            "checks": [
                {
                    "id": check_id,
                    "implementation_path": implementation_output,
                    "implementation_sha256": _file_sha256(implementation_output),
                }
                for check_id in check_ids
            ],
            "scored_state_fields": list(_SCORED_STATE_FIELDS),
        },
        "support_files": [_source_support(implementation_output, source_relative)],
    }


def _manifest_supports(
    *,
    output: str,
    role: str,
    source_paths: tuple[str, ...],
) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
    declarations: list[dict[str, str]] = []
    supports: list[dict[str, Any]] = []
    for index, source in enumerate(source_paths, start=1):
        destination = _support(
            output,
            role,
            f"capture-bundles/bundle-{index:02d}.json",
        )
        declarations.append(
            {
                "path": destination,
                "sha256": _file_sha256(destination),
            }
        )
        supports.append(_source_support(destination, source))
    return declarations, supports


def _build_input_evidence_roles(
    *,
    root: Path,
    scenario: NativeScenario,
    output: str,
    evidence: tuple[_VariantEvidence, ...],
    capture_manifest_usage: dict[str, tuple[str, ...]],
    runtime_manifest_relative: str,
    runtime_revision: str,
    source_verification_relative: str,
) -> dict[str, dict[str, Any]]:
    _, prefix_relative = _repo_file(
        root,
        scenario.resolve_artifact("prefix"),
        label="scenario admission prefix",
    )
    prefix_output = _support(
        output,
        "reset_evidence",
        "common/prefix.json",
    )
    tokens = {
        item.variant_id: f"v{index:02d}" for index, item in enumerate(evidence, start=1)
    }
    reset_manifest_declarations, reset_manifest_supports = _manifest_supports(
        output=output,
        role="reset_evidence",
        source_paths=capture_manifest_usage["reset"],
    )
    boundary_manifest_declarations, boundary_manifest_supports = _manifest_supports(
        output=output,
        role="boundary_bundle",
        source_paths=capture_manifest_usage["boundary"],
    )
    reset_outputs = {
        item.variant_id: _support(
            output,
            "reset_evidence",
            f"variants/{tokens[item.variant_id]}-reset.json",
        )
        for item in evidence
    }
    boundary_outputs = {
        item.variant_id: _support(
            output,
            "boundary_bundle",
            f"variants/{tokens[item.variant_id]}-boundary.json",
        )
        for item in evidence
    }
    failure_outputs = {
        item.variant_id: _support(
            output,
            "boundary_bundle",
            f"failure-surfaces/{tokens[item.variant_id]}.json",
        )
        for item in evidence
    }
    raw_boundary_outputs = {
        item.variant_id: _support(
            output,
            "boundary_bundle",
            f"raw/{tokens[item.variant_id]}-boundary.json",
        )
        for item in evidence
    }
    runtime_manifest_output = _support(
        output,
        "boundary_bundle",
        "source-bundles/runtime-files.json",
    )
    boundary_contract_sources = [
        _repo_file(
            root,
            relative,
            label=f"Forgejo boundary contract source {relative}",
        )[1]
        for relative in _BOUNDARY_CONTRACT_SOURCES
    ]
    boundary_contract_outputs = {
        source: _support(
            output,
            "boundary_bundle",
            f"native-boundary/{index:02d}-{Path(source).name}",
        )
        for index, source in enumerate(
            boundary_contract_sources,
            start=1,
        )
    }
    boundary_verification_output = _support(
        output,
        "boundary_bundle",
        "native-boundary/source-verification.json",
    )
    raw_reference_outputs = {
        item.variant_id: _support(
            output,
            "reference_bundle",
            f"raw/{tokens[item.variant_id]}-reference.json",
        )
        for item in evidence
    }
    reference_start_outputs = {
        item.variant_id: _support(
            output,
            "reference_bundle",
            f"start-states/{tokens[item.variant_id]}.json",
        )
        for item in evidence
    }
    trace_outputs = {
        item.variant_id: _support(
            output,
            "reference_bundle",
            f"traces/{tokens[item.variant_id]}.json",
        )
        for item in evidence
    }
    terminal_outputs = {
        item.variant_id: _support(
            output,
            "reference_bundle",
            f"terminal/{tokens[item.variant_id]}.json",
        )
        for item in evidence
    }

    reset_role = {
        "primary_payload": {
            "prefix_path": prefix_output,
            "prefix_sha256": _file_sha256(prefix_output),
            "exact_bundle_manifests": reset_manifest_declarations,
            "variants": [
                {
                    "variant_id": item.variant_id,
                    "reset_snapshot_path": reset_outputs[item.variant_id],
                    "reset_snapshot_sha256": _file_sha256(
                        reset_outputs[item.variant_id]
                    ),
                    "reset_verified": True,
                }
                for item in evidence
            ],
        },
        "support_files": [
            _source_support(prefix_output, prefix_relative),
            *reset_manifest_supports,
            *[
                _source_support(
                    reset_outputs[item.variant_id],
                    item.reset_relative,
                )
                for item in evidence
            ],
        ],
    }
    boundary_role = {
        "primary_payload": {
            "operation": scenario.raw["ambiguous_operation"]["operation"],
            "runtime_bundle_manifest_path": runtime_manifest_output,
            "runtime_bundle_manifest_sha256": _file_sha256(runtime_manifest_output),
            "failure_injection_contract": {
                "runtime_revision": runtime_revision,
                "source_verification_path": (boundary_verification_output),
                "source_verification_sha256": _file_sha256(
                    boundary_verification_output
                ),
                "files": [
                    {
                        "source_path": source,
                        "path": boundary_contract_outputs[source],
                        "sha256": _file_sha256(boundary_contract_outputs[source]),
                    }
                    for source in boundary_contract_sources
                ],
            },
            "exact_bundle_manifests": boundary_manifest_declarations,
            "variants": [
                {
                    "variant_id": item.variant_id,
                    "boundary_state_path": boundary_outputs[item.variant_id],
                    "boundary_state_sha256": _file_sha256(
                        boundary_outputs[item.variant_id]
                    ),
                    "failure_surface_path": failure_outputs[item.variant_id],
                    "failure_surface_sha256": _file_sha256(
                        failure_outputs[item.variant_id]
                    ),
                    "raw_failure_report_path": (raw_boundary_outputs[item.variant_id]),
                    "raw_failure_report_sha256": _file_sha256(
                        raw_boundary_outputs[item.variant_id]
                    ),
                    "reset_snapshot_sha256": _file_sha256(
                        reset_outputs[item.variant_id]
                    ),
                    "boundary_validation_passed": True,
                }
                for item in evidence
            ],
        },
        "support_files": [
            _source_support(
                runtime_manifest_output,
                runtime_manifest_relative,
            ),
            _source_support(
                boundary_verification_output,
                source_verification_relative,
            ),
            *[
                _source_support(
                    boundary_contract_outputs[source],
                    source,
                )
                for source in boundary_contract_sources
            ],
            *boundary_manifest_supports,
            *[
                _source_support(
                    boundary_outputs[item.variant_id],
                    item.boundary_capture_relative,
                )
                for item in evidence
            ],
            *[
                _source_support(
                    raw_boundary_outputs[item.variant_id],
                    item.raw_boundary_relative,
                )
                for item in evidence
            ],
            *[
                _json_support(
                    failure_outputs[item.variant_id],
                    {
                        "scenario_id": _identity("scenario_id"),
                        "variant_id": item.variant_id,
                        "phase": "failure_surface",
                        "operation": scenario.raw["ambiguous_operation"]["operation"],
                        "surface_result": item.raw_boundary["surface_result"],
                        "visible_failure": item.raw_boundary["visible_failure"],
                        "raw_failure_report_sha256": _file_sha256(
                            raw_boundary_outputs[item.variant_id]
                        ),
                    },
                )
                for item in evidence
            ],
        ],
    }
    reference_role = {
        "primary_payload": {
            "variants": [
                {
                    "variant_id": item.variant_id,
                    "boundary_state_sha256": _file_sha256(
                        boundary_outputs[item.variant_id]
                    ),
                    "raw_reference_report_path": (
                        raw_reference_outputs[item.variant_id]
                    ),
                    "raw_reference_report_sha256": _file_sha256(
                        raw_reference_outputs[item.variant_id]
                    ),
                    "reference_start_state_path": (
                        reference_start_outputs[item.variant_id]
                    ),
                    "reference_start_state_sha256": _file_sha256(
                        reference_start_outputs[item.variant_id]
                    ),
                    "reference_trace_path": trace_outputs[item.variant_id],
                    "reference_trace_sha256": _file_sha256(
                        trace_outputs[item.variant_id]
                    ),
                    "terminal_state_path": terminal_outputs[item.variant_id],
                    "terminal_state_sha256": _file_sha256(
                        terminal_outputs[item.variant_id]
                    ),
                    "evaluator_passed": True,
                }
                for item in evidence
            ]
        },
        "support_files": [
            *[
                _source_support(
                    reference_start_outputs[item.variant_id],
                    item.reference_start_relative,
                )
                for item in evidence
            ],
            *[
                _source_support(
                    raw_reference_outputs[item.variant_id],
                    item.raw_reference_relative,
                )
                for item in evidence
            ],
            *[
                _json_support(
                    trace_outputs[item.variant_id],
                    {
                        "scenario_id": _identity("scenario_id"),
                        "variant_id": item.variant_id,
                        "phase": "reference_trace",
                        "boundary_state_sha256": _file_sha256(
                            boundary_outputs[item.variant_id]
                        ),
                        "input_envelope_sha256": _role_dependencies("reference_bundle"),
                        "raw_reference_report_sha256": _file_sha256(
                            raw_reference_outputs[item.variant_id]
                        ),
                        "steps": item.raw_reference["reference_trace"],
                    },
                )
                for item in evidence
            ],
            *[
                _json_support(
                    terminal_outputs[item.variant_id],
                    {
                        "scenario_id": _identity("scenario_id"),
                        "variant_id": item.variant_id,
                        "phase": "terminal",
                        "boundary_state_sha256": _file_sha256(
                            boundary_outputs[item.variant_id]
                        ),
                        "evaluator_envelope_sha256": _envelope_sha256("evaluator"),
                        "raw_reference_report_sha256": _file_sha256(
                            raw_reference_outputs[item.variant_id]
                        ),
                        "evaluation": _bound_json_field(
                            raw_reference_outputs[item.variant_id],
                            "evaluation",
                        ),
                        "final_evidence": _bound_json_field(
                            raw_reference_outputs[item.variant_id],
                            "final_evidence",
                        ),
                        "status": "complete",
                    },
                )
                for item in evidence
            ],
        ],
    }
    return {
        "reset_evidence": reset_role,
        "boundary_bundle": boundary_role,
        "reference_bundle": reference_role,
    }


def _empty_completion_roles() -> dict[str, dict[str, Any]]:
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


def _build_completion_roles(
    *,
    scenario: NativeScenario,
    output: str,
    evidence: tuple[_VariantEvidence, ...],
    control_manifest_relative: str,
    model_input_lock_relative: str,
) -> dict[str, dict[str, Any]]:
    if any(
        item.trajectory is None
        or item.trajectory_relative is None
        or item.pre_model_boundary_path is None
        or item.pre_model_boundary_relative is None
        for item in evidence
    ):
        raise ForgejoFormalBuildSpecError(
            "complete mode requires all eight raw model trajectories"
        )
    tokens = {
        item.variant_id: f"v{index:02d}" for index, item in enumerate(evidence, start=1)
    }
    boundary_outputs = {
        item.variant_id: _support(
            output,
            "boundary_bundle",
            f"variants/{tokens[item.variant_id]}-boundary.json",
        )
        for item in evidence
    }
    lock_output = _support(
        output,
        "raw_run_archive",
        "formal-input-lock.json",
    )
    control_manifest_output = _support(
        output,
        "raw_run_archive",
        "source-bundles/control-files.json",
    )
    raw_outputs = {
        item.variant_id: _support(
            output,
            "raw_run_archive",
            f"trajectories/{tokens[item.variant_id]}.json",
        )
        for item in evidence
    }
    pre_model_outputs = {
        item.variant_id: _support(
            output,
            "raw_run_archive",
            f"pre-model-boundaries/{tokens[item.variant_id]}.json",
        )
        for item in evidence
    }
    run_outputs = {
        item.variant_id: _support(
            output,
            "raw_run_archive",
            f"run-records/{tokens[item.variant_id]}.json",
        )
        for item in evidence
    }
    summary_output = _support(
        output,
        "execution_control",
        "summary.json",
    )
    run_ids = {
        item.variant_id: str((item.trajectory or {})["run_id"]) for item in evidence
    }
    run_passes = {
        item.variant_id: (
            (item.trajectory or {}).get("evaluation", {}).get("passed") is True
        )
        for item in evidence
    }
    passed_runs = sum(run_passes.values())
    task_pass_rate = passed_runs / len(evidence)
    raw_role = {
        "primary_payload": {
            "formal_input_lock_path": lock_output,
            "formal_input_lock_sha256": _file_sha256(lock_output),
            "control_bundle_manifest_path": control_manifest_output,
            "control_bundle_manifest_sha256": _file_sha256(control_manifest_output),
            "runs": [
                {
                    "run_id": run_ids[item.variant_id],
                    "variant_id": item.variant_id,
                    "run_path": run_outputs[item.variant_id],
                    "run_sha256": _file_sha256(run_outputs[item.variant_id]),
                    "raw_trajectory_path": raw_outputs[item.variant_id],
                    "raw_trajectory_sha256": _file_sha256(raw_outputs[item.variant_id]),
                    "pre_model_boundary_evidence_path": (
                        pre_model_outputs[item.variant_id]
                    ),
                    "pre_model_boundary_evidence_sha256": _file_sha256(
                        pre_model_outputs[item.variant_id]
                    ),
                    "summary_report_path": raw_outputs[item.variant_id],
                    "boundary_state_sha256": _file_sha256(
                        boundary_outputs[item.variant_id]
                    ),
                    "formal_input_lock_sha256": (_formal_input_lock_sha256()),
                    "execution_control": True,
                    "passed": run_passes[item.variant_id],
                }
                for item in evidence
            ],
        },
        "support_files": [
            _source_support(lock_output, model_input_lock_relative),
            _source_support(
                control_manifest_output,
                control_manifest_relative,
            ),
            *[
                _source_support(
                    raw_outputs[item.variant_id],
                    str(item.trajectory_relative),
                )
                for item in evidence
            ],
            *[
                _source_support(
                    pre_model_outputs[item.variant_id],
                    str(item.pre_model_boundary_relative),
                )
                for item in evidence
            ],
            *[
                _json_support(
                    run_outputs[item.variant_id],
                    {
                        "scenario_id": _identity("scenario_id"),
                        "variant_id": item.variant_id,
                        "run_id": run_ids[item.variant_id],
                        "boundary_state_sha256": _file_sha256(
                            boundary_outputs[item.variant_id]
                        ),
                        "input_envelope_sha256": _role_dependencies("raw_run_archive"),
                        "formal_input_lock_sha256": (_formal_input_lock_sha256()),
                        "raw_trajectory_path": raw_outputs[item.variant_id],
                        "raw_trajectory_sha256": _file_sha256(
                            raw_outputs[item.variant_id]
                        ),
                        "pre_model_boundary_evidence_path": (
                            pre_model_outputs[item.variant_id]
                        ),
                        "pre_model_boundary_evidence_sha256": _file_sha256(
                            pre_model_outputs[item.variant_id]
                        ),
                        "summary_report_path": raw_outputs[item.variant_id],
                        "execution_control": True,
                        "passed": run_passes[item.variant_id],
                    },
                )
                for item in evidence
            ],
        ],
    }
    summary = {
        "schema_version": "1.0",
        "completed_runs": len(evidence),
        "run_errors": [],
        "task_pass_rate": task_pass_rate,
        "execution_control_counts": {"true": len(evidence)},
        "reports": [
            {
                "scenario_id": _identity("scenario_id"),
                "variant": item.variant_id,
                "passed": run_passes[item.variant_id],
                "path": raw_outputs[item.variant_id],
            }
            for item in evidence
        ],
    }
    control_role = {
        "primary_payload": {
            "formal_input_lock_sha256": _formal_input_lock_sha256(),
            "run_ids": [run_ids[item.variant_id] for item in evidence],
            "completed_runs": len(evidence),
            "passed_runs": passed_runs,
            "task_pass_rate": task_pass_rate,
            "control_summary_path": summary_output,
            "control_summary_sha256": _file_sha256(summary_output),
        },
        "support_files": [
            _json_support(summary_output, summary),
        ],
    }
    return {
        "raw_run_archive": raw_role,
        "execution_control": control_role,
    }


def generate_forgejo_formal_build_spec(
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
) -> ForgejoFormalBuildSpecResult:
    """Generate a strict seven-role spec from native Forgejo evidence.

    ``inputs`` validates and emits the five roles that must be frozen before
    provider access. ``complete`` additionally requires the frozen input lock
    plus the exact execution-control bundle and emits the two completion
    roles. The function writes neither the spec nor formal evidence.
    """

    resolved_root = Path(root).resolve()
    if not resolved_root.is_dir():
        raise ForgejoFormalBuildSpecError(
            "repository root must be an existing directory"
        )
    if phase not in {"inputs", "complete"}:
        raise ForgejoFormalBuildSpecError("phase must be inputs or complete")
    release_id = _require_identifier(
        benchmark_release_id,
        label="benchmark_release_id",
    )
    output = _validate_output_directory(
        resolved_root,
        output_directory,
    )
    scenario, scenario_relative, instance_spec_sha256 = _validate_active_scenario(
        resolved_root, scenario_path
    )
    if phase == "inputs":
        if control_manifest_path is not None or model_input_lock_path is not None:
            raise ForgejoFormalBuildSpecError(
                "inputs phase must not receive completion-only evidence"
            )
    elif control_manifest_path is None or model_input_lock_path is None:
        raise ForgejoFormalBuildSpecError(
            "complete phase requires control manifest and input lock"
        )
    runtime_manifest = _load_exact_manifest(
        resolved_root,
        runtime_manifest_path,
        label="runtime exact bundle manifest",
    )
    runtime_revision, source_verification_relative = _validate_native_runtime_contract(
        resolved_root,
        runtime_manifest,
    )
    capture_dir, _ = _repo_directory(
        resolved_root,
        capture_directory,
        label="state capture directory",
    )
    capture_manifests = _load_capture_bundle_manifests(
        resolved_root,
        capture_bundle_manifest_paths,
    )

    control_manifest: _ExactManifest | None = None
    control_relative: str | None = None
    lock_relative: str | None = None
    if phase == "complete":
        assert control_manifest_path is not None
        assert model_input_lock_path is not None
        control_manifest = _load_exact_manifest(
            resolved_root,
            control_manifest_path,
            label="execution-control exact bundle manifest",
        )
        control_relative = control_manifest.relative_path
        lock_path, lock_relative = _repo_file(
            resolved_root,
            model_input_lock_path,
            label="formal model input lock",
        )
        expected_lock = (resolved_root / output / "formal-input-lock.json").resolve()
        if lock_path != expected_lock:
            raise ForgejoFormalBuildSpecError(
                "complete mode input lock must be output/formal-input-lock.json"
            )

    producer_commit = _current_git_commit(resolved_root)
    evidence, check_ids, capture_manifest_usage = _collect_variant_evidence(
        root=resolved_root,
        scenario=scenario,
        instance_spec_sha256=instance_spec_sha256,
        runtime_manifest=runtime_manifest,
        control_manifest=control_manifest,
        formal_input_lock_path=lock_relative,
        trusted_producer_commit=producer_commit,
        capture_directory=capture_dir,
        bundle_manifests=capture_manifests,
    )

    roles: dict[str, dict[str, Any]] = {
        "tool_contract": _build_tool_contract_role(
            root=resolved_root,
            output=output,
            runtime_revision=runtime_revision,
            source_verification_relative=(source_verification_relative),
        ),
        "evaluator": _build_evaluator_role(
            root=resolved_root,
            output=output,
            check_ids=check_ids,
        ),
        **_build_input_evidence_roles(
            root=resolved_root,
            scenario=scenario,
            output=output,
            evidence=evidence,
            capture_manifest_usage=capture_manifest_usage,
            runtime_manifest_relative=runtime_manifest.relative_path,
            runtime_revision=runtime_revision,
            source_verification_relative=(source_verification_relative),
        ),
    }
    if phase == "inputs":
        roles.update(_empty_completion_roles())
    else:
        assert control_relative is not None
        assert lock_relative is not None
        roles.update(
            _build_completion_roles(
                scenario=scenario,
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
    return ForgejoFormalBuildSpecResult(
        spec=spec,
        scenario_path=scenario_relative,
        runtime_manifest_path=runtime_manifest.relative_path,
        control_manifest_path=control_relative,
        capture_bundle_manifest_paths=tuple(
            sorted(relative for relative, _ in capture_manifests.values())
        ),
    )


def write_forgejo_formal_build_spec(
    path: str | Path,
    spec: dict[str, Any],
    *,
    root: str | Path,
) -> str:
    resolved_root = Path(root).resolve()
    output = Path(path)
    candidate = output if output.is_absolute() else resolved_root / output
    try:
        resolved = candidate.resolve()
        resolved.relative_to(resolved_root)
    except ValueError as error:
        raise ForgejoFormalBuildSpecError(
            "build-spec output must stay inside the repository root"
        ) from error
    if resolved.exists():
        raise ForgejoFormalBuildSpecError("build-spec output already exists")
    try:
        content = (
            json.dumps(
                spec,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise ForgejoFormalBuildSpecError(
            "generated build spec is not strict JSON"
        ) from error
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_bytes(content)
    return resolved.relative_to(resolved_root).as_posix()


__all__ = [
    "ForgejoFormalBuildSpecError",
    "ForgejoFormalBuildSpecResult",
    "discover_active_forgejo_public_dev_scenario",
    "generate_forgejo_formal_build_spec",
    "write_forgejo_formal_build_spec",
]
