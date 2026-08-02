from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from .native_scenario import (
    load_native_scenario,
    validate_native_scenario_document,
)
from .path_safety import safe_relative_path
from .release_manifest import (
    FORMAL_EVIDENCE_DEPENDENCIES,
    FORMAL_EVIDENCE_ROLES,
    MIN_EXECUTION_CONTROL_PASS_RATE,
    bound_reset_snapshot_sha256,
    file_sha256,
    validate_formal_evidence_roles,
)
from .schema import repository_root
from .strict_json import load_json_strict

_IDENTIFIER = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
_GIT_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_FORMAL_SPLITS = frozenset({"public_dev", "hidden_test"})
_ALLOWED_SUPPORT_SOURCE_PREFIXES = frozenset(
    {"data", "runtimes", "schemas", "scripts", "src"}
)
_BUILD_SPEC_FIELDS = frozenset(
    {
        "schema_version",
        "benchmark_release_id",
        "scenario_path",
        "scenario_id",
        "domain_id",
        "family_id",
        "instance_id",
        "variant_ids",
        "producer_commit",
        "output_directory",
        "roles",
    }
)
_ROLE_SPEC_FIELDS = frozenset({"primary_payload", "support_files"})
_SUPPORT_COMMON_FIELDS = frozenset({"path"})
_SUPPORT_SOURCE_FIELDS = _SUPPORT_COMMON_FIELDS | {"source_path"}
_SUPPORT_JSON_FIELDS = _SUPPORT_COMMON_FIELDS | {"json_content"}
_PRIMARY_IDENTITY_FIELDS = frozenset(
    {
        "schema_version",
        "artifact_type",
        "benchmark_release_id",
        "scenario_id",
        "domain_id",
        "family_id",
        "instance_id",
        "variant_ids",
        "producer_commit",
        "input_envelope_sha256",
    }
)

# This order is deliberately explicit. A later change to the dependency graph
# must fail here instead of silently producing envelopes in an unsafe order.
FORMAL_EVIDENCE_BUILD_ORDER = (
    "tool_contract",
    "evaluator",
    "reset_evidence",
    "boundary_bundle",
    "reference_bundle",
    "raw_run_archive",
    "execution_control",
)
FORMAL_INPUT_ROLES = FORMAL_EVIDENCE_BUILD_ORDER[:5]
FORMAL_COMPLETION_ROLES = FORMAL_EVIDENCE_BUILD_ORDER[5:]


class FormalEvidenceBuildError(ValueError):
    """Raised before an invalid formal-evidence package is published."""


@dataclass(frozen=True)
class FormalEvidenceBuildResult:
    benchmark_release_id: str
    scenario_id: str
    output_directory: str
    declarations_manifest_path: str
    declarations_manifest_sha256: str
    formal_evidence: dict[str, dict[str, str]]
    control_evidence: dict[str, str | float]

    def as_dict(self) -> dict[str, Any]:
        return {
            "benchmark_release_id": self.benchmark_release_id,
            "scenario_id": self.scenario_id,
            "output_directory": self.output_directory,
            "declarations_manifest_path": (
                self.declarations_manifest_path
            ),
            "declarations_manifest_sha256": (
                self.declarations_manifest_sha256
            ),
            "formal_evidence": deepcopy(self.formal_evidence),
            "control_evidence": deepcopy(self.control_evidence),
        }


@dataclass(frozen=True)
class FormalInputLockResult:
    benchmark_release_id: str
    scenario_id: str
    output_directory: str
    input_lock_path: str
    input_lock_sha256: str
    input_evidence: dict[str, dict[str, str]]

    def as_dict(self) -> dict[str, Any]:
        return {
            "benchmark_release_id": self.benchmark_release_id,
            "scenario_id": self.scenario_id,
            "output_directory": self.output_directory,
            "input_lock_path": self.input_lock_path,
            "input_lock_sha256": self.input_lock_sha256,
            "input_evidence": deepcopy(self.input_evidence),
        }


@dataclass(frozen=True)
class FormalInputLockVerification:
    lock_sha256: str
    input_envelope_sha256: dict[str, str]
    variant_id: str
    boundary_state_sha256: str
    failure_report_sha256: str
    prefix_sha256: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "lock_sha256": self.lock_sha256,
            "input_envelope_sha256": deepcopy(
                self.input_envelope_sha256
            ),
            "variant_id": self.variant_id,
            "boundary_state_sha256": self.boundary_state_sha256,
            "failure_report_sha256": self.failure_report_sha256,
            "prefix_sha256": self.prefix_sha256,
        }


def load_formal_evidence_build_spec(path: str | Path) -> dict[str, Any]:
    raw = load_json_strict(path)
    if not isinstance(raw, dict):
        raise FormalEvidenceBuildError("build spec must be a JSON object")
    return raw


def current_git_commit(root: str | Path | None = None) -> str:
    resolved_root = (Path(root) if root is not None else repository_root()).resolve()
    try:
        result = subprocess.run(
            ["git", "-C", str(resolved_root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise FormalEvidenceBuildError(
            "cannot determine the trusted producer commit"
        ) from error
    commit = result.stdout.strip()
    if _GIT_COMMIT.fullmatch(commit) is None:
        raise FormalEvidenceBuildError(
            "git returned an invalid producer commit"
        )
    return commit


def _repository_file(
    root: Path,
    value: str | Path,
    *,
    required_prefix: str | None = None,
) -> Path:
    candidate = Path(value)
    if candidate.is_absolute():
        try:
            relative = candidate.resolve().relative_to(root).as_posix()
        except ValueError as error:
            raise FormalEvidenceBuildError(
                "file path is outside the repository"
            ) from error
    else:
        relative = candidate.as_posix() if isinstance(value, Path) else value
    try:
        return safe_relative_path(
            root,
            relative,
            required_prefix=required_prefix,
            must_exist=True,
            require_file=True,
        )
    except (OSError, ValueError) as error:
        raise FormalEvidenceBuildError(
            f"repository file is missing or unsafe: {relative}"
        ) from error


def verify_formal_input_lock(
    lock_path: str | Path,
    *,
    root: str | Path | None = None,
    scenario_id: str,
    domain_id: str,
    family_id: str,
    instance_id: str,
    variant_id: str,
    failure_report_path: str | Path,
    prefix_path: str | Path,
    trusted_producer_commit: str | None = None,
) -> FormalInputLockVerification:
    """Verify the exact pre-provider evidence for one model-run variant.

    This verifier intentionally reads only ``formal-input-lock.json`` and the
    five input-role envelopes. It has no dependency on raw model runs,
    execution-control evidence or the final declarations manifest.
    """

    resolved_root = (
        Path(root) if root is not None else repository_root()
    ).resolve()
    lock_file = _repository_file(
        resolved_root,
        lock_path,
        required_prefix="data",
    )
    try:
        lock = load_json_strict(lock_file)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise FormalEvidenceBuildError(
            "formal input lock is not strict JSON"
        ) from error
    expected_lock_fields = {
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
    if not isinstance(lock, dict) or set(lock) != expected_lock_fields:
        raise FormalEvidenceBuildError(
            "formal input lock fields are not exact"
        )
    variants = tuple(map(str, lock.get("variant_ids", ())))
    expected_identity = (
        scenario_id,
        domain_id,
        family_id,
        instance_id,
    )
    observed_identity = (
        str(lock.get("scenario_id", "")),
        str(lock.get("domain_id", "")),
        str(lock.get("family_id", "")),
        str(lock.get("instance_id", "")),
    )
    producer_commit = str(lock.get("producer_commit", ""))
    trusted_commit = trusted_producer_commit or current_git_commit(
        resolved_root
    )
    if (
        lock.get("schema_version") != "1.0"
        or lock.get("artifact_type") != "formal_input_lock"
        or lock_file.name != "formal-input-lock.json"
        or any(
            _IDENTIFIER.fullmatch(str(value)) is None
            for value in (
                lock.get("benchmark_release_id", ""),
                *observed_identity,
                *variants,
            )
        )
        or observed_identity != expected_identity
        or variant_id not in variants
        or len(variants) != len(set(variants))
        or _GIT_COMMIT.fullmatch(producer_commit) is None
        or producer_commit != trusted_commit
        or _SHA256.fullmatch(
            str(lock.get("input_projection_sha256", ""))
        )
        is None
        or _SHA256.fullmatch(str(lock.get("scenario_sha256", "")))
        is None
    ):
        raise FormalEvidenceBuildError(
            "formal input lock identity or producer commit is invalid"
        )

    scenario_path = _repository_file(
        resolved_root,
        str(lock["scenario_path"]),
        required_prefix="data",
    )
    scenario = load_native_scenario(scenario_path)
    if (
        file_sha256(scenario_path) != str(lock["scenario_sha256"])
        or (
            scenario.scenario_id,
            scenario.domain_id,
            scenario.family_id,
            scenario.instance_id,
            scenario.variants,
        )
        != (*expected_identity, variants)
    ):
        raise FormalEvidenceBuildError(
            "active scenario differs from the formal input lock"
        )

    declarations = lock["input_role_declarations"]
    if (
        not isinstance(declarations, dict)
        or set(declarations) != set(FORMAL_INPUT_ROLES)
    ):
        raise FormalEvidenceBuildError(
            "formal input lock does not contain exactly five input roles"
        )
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
    if _sha256_bytes(_json_bytes(projection)) != str(
        lock["input_projection_sha256"]
    ):
        raise FormalEvidenceBuildError(
            "formal input projection hash is invalid"
        )
    envelope_hashes: dict[str, str] = {}
    envelopes: dict[str, dict[str, Any]] = {}
    primary_payloads: dict[str, dict[str, Any]] = {}
    role_file_hashes: dict[str, dict[str, str]] = {}
    all_file_paths: list[str] = []
    envelope_paths: list[str] = []
    output_relative = lock_file.parent.relative_to(
        resolved_root
    ).as_posix()
    for role in FORMAL_INPUT_ROLES:
        declaration = declarations[role]
        if not isinstance(declaration, dict) or set(declaration) != {
            "path",
            "sha256",
        }:
            raise FormalEvidenceBuildError(
                f"input declaration is invalid: {role}"
            )
        envelope_path = _repository_file(
            resolved_root,
            str(declaration["path"]),
            required_prefix="data",
        )
        envelope_hash = file_sha256(envelope_path)
        expected_envelope_relative = (
            f"{_role_root_relative(output_relative, role)}/envelope.json"
        )
        if (
            _SHA256.fullmatch(str(declaration["sha256"])) is None
            or envelope_hash != declaration["sha256"]
            or envelope_path.relative_to(resolved_root).as_posix()
            != expected_envelope_relative
        ):
            raise FormalEvidenceBuildError(
                f"input envelope hash drift: {role}"
            )
        envelope = load_json_strict(envelope_path)
        if not isinstance(envelope, dict):
            raise FormalEvidenceBuildError(
                f"input envelope is not an object: {role}"
            )
        if (
            envelope.get("schema_version") != "1.0"
            or envelope.get("artifact_type") != role
            or envelope.get("benchmark_release_id")
            != lock.get("benchmark_release_id")
            or (
                envelope.get("scenario_id"),
                envelope.get("domain_id"),
                envelope.get("family_id"),
                envelope.get("instance_id"),
            )
            != expected_identity
            or tuple(map(str, envelope.get("variant_ids", ())))
            != variants
            or envelope.get("producer_commit") != producer_commit
        ):
            raise FormalEvidenceBuildError(
                f"input envelope identity drift: {role}"
            )
        files = envelope.get("files")
        if not isinstance(files, list) or not files:
            raise FormalEvidenceBuildError(
                f"input envelope has no files: {role}"
            )
        local_hashes: dict[str, str] = {}
        expected_role_root = _role_root_relative(output_relative, role)
        for item in files:
            if not isinstance(item, dict) or set(item) != {
                "path",
                "sha256",
            }:
                raise FormalEvidenceBuildError(
                    f"input envelope file declaration is invalid: {role}"
                )
            payload_path = _repository_file(
                resolved_root,
                str(item["path"]),
                required_prefix="data",
            )
            relative = payload_path.relative_to(resolved_root).as_posix()
            digest = file_sha256(payload_path)
            if (
                relative in local_hashes
                or not relative.startswith(f"{expected_role_root}/")
                or _SHA256.fullmatch(str(item["sha256"])) is None
                or digest != item["sha256"]
            ):
                raise FormalEvidenceBuildError(
                    f"input role payload hash drift: {role}"
                )
            local_hashes[relative] = digest
            all_file_paths.append(relative)
        primary_relative = str(envelope.get("primary_payload_path", ""))
        if (
            primary_relative
            != f"{expected_role_root}/primary.json"
            or primary_relative not in local_hashes
        ):
            raise FormalEvidenceBuildError(
                f"input primary payload is not envelope-bound: {role}"
            )
        primary = load_json_strict(
            _repository_file(
                resolved_root,
                primary_relative,
                required_prefix="data",
            )
        )
        if (
            not isinstance(primary, dict)
            or primary.get("artifact_type") != role
            or primary.get("benchmark_release_id")
            != lock.get("benchmark_release_id")
            or (
                primary.get("scenario_id"),
                primary.get("domain_id"),
                primary.get("family_id"),
                primary.get("instance_id"),
            )
            != expected_identity
            or tuple(map(str, primary.get("variant_ids", ()))) != variants
            or primary.get("producer_commit") != producer_commit
        ):
            raise FormalEvidenceBuildError(
                f"input primary identity drift: {role}"
            )
        relative_envelope = envelope_path.relative_to(
            resolved_root
        ).as_posix()
        envelope_paths.append(relative_envelope)
        envelope_hashes[role] = envelope_hash
        envelopes[role] = envelope
        primary_payloads[role] = primary
        role_file_hashes[role] = local_hashes
    if (
        len(envelope_paths) != len(set(envelope_paths))
        or len(all_file_paths) != len(set(all_file_paths))
        or set(envelope_paths) & set(all_file_paths)
    ):
        raise FormalEvidenceBuildError(
            "formal input paths are not globally unique"
        )
    for role in FORMAL_INPUT_ROLES:
        expected_dependencies = FORMAL_EVIDENCE_DEPENDENCIES[role]
        dependencies = envelopes[role].get("depends_on")
        if (
            not isinstance(dependencies, dict)
            or set(dependencies) != expected_dependencies
            or any(
                dependencies[dependency] != envelope_hashes[dependency]
                for dependency in expected_dependencies
            )
            or primary_payloads[role].get("input_envelope_sha256")
            != dependencies
        ):
            raise FormalEvidenceBuildError(
                f"formal input dependency drift: {role}"
            )

    reset_primary = primary_payloads["reset_evidence"]
    locked_prefix_path = str(reset_primary.get("prefix_path", ""))
    locked_prefix_hash = str(reset_primary.get("prefix_sha256", ""))
    if (
        _SHA256.fullmatch(locked_prefix_hash) is None
        or role_file_hashes["reset_evidence"].get(locked_prefix_path)
        != locked_prefix_hash
    ):
        raise FormalEvidenceBuildError(
            "formal input lock has no unique hash-bound prefix"
        )
    actual_prefix_file = _repository_file(resolved_root, prefix_path)
    actual_prefix_hash = file_sha256(actual_prefix_file)
    if actual_prefix_hash != locked_prefix_hash:
        raise FormalEvidenceBuildError(
            "runner prefix is not the prefix bound by the input lock"
        )

    boundary_variants = _variant_index(
        primary_payloads["boundary_bundle"],
        variants,
    )
    if boundary_variants is None:
        raise FormalEvidenceBuildError(
            "boundary input variants are not exact"
        )
    boundary = boundary_variants[variant_id]
    boundary_hash = str(boundary.get("boundary_state_sha256", ""))
    failure_surface_hash = str(
        boundary.get("failure_surface_sha256", "")
    )
    raw_failure_hash = str(
        boundary.get("raw_failure_report_sha256", "")
    )
    boundary_path = str(boundary.get("boundary_state_path", ""))
    failure_surface_path = str(
        boundary.get("failure_surface_path", "")
    )
    raw_failure_path = str(
        boundary.get("raw_failure_report_path", "")
    )
    if (
        _SHA256.fullmatch(boundary_hash) is None
        or _SHA256.fullmatch(failure_surface_hash) is None
        or _SHA256.fullmatch(raw_failure_hash) is None
        or role_file_hashes["boundary_bundle"].get(boundary_path)
        != boundary_hash
        or role_file_hashes["boundary_bundle"].get(failure_surface_path)
        != failure_surface_hash
        or role_file_hashes["boundary_bundle"].get(raw_failure_path)
        != raw_failure_hash
    ):
        raise FormalEvidenceBuildError(
            "variant boundary hashes are invalid"
        )
    report_file = _repository_file(resolved_root, failure_report_path)
    actual_failure_hash = file_sha256(report_file)
    if actual_failure_hash != raw_failure_hash:
        raise FormalEvidenceBuildError(
            "failure report is not the variant bound by the input lock"
        )
    return FormalInputLockVerification(
        lock_sha256=file_sha256(lock_file),
        input_envelope_sha256=envelope_hashes,
        variant_id=variant_id,
        boundary_state_sha256=boundary_hash,
        failure_report_sha256=actual_failure_hash,
        prefix_sha256=actual_prefix_hash,
    )


def _json_bytes(value: Any) -> bytes:
    try:
        rendered = json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
    except (TypeError, ValueError) as error:
        raise FormalEvidenceBuildError(
            "build spec contains a non-JSON value"
        ) from error
    return (rendered + "\n").encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _require_exact_fields(
    value: dict[str, Any],
    expected: frozenset[str],
    *,
    label: str,
) -> None:
    observed = set(value)
    if observed != expected:
        missing = sorted(expected - observed)
        extra = sorted(observed - expected)
        raise FormalEvidenceBuildError(
            f"{label} fields are not exact; missing={missing}, extra={extra}"
        )


def _require_identifier(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
        raise FormalEvidenceBuildError(
            f"{field} must be a canonical lowercase identifier"
        )
    return value


def _relative_to_output(
    *,
    root: Path,
    output_directory: Path,
    relative: str,
    label: str,
) -> Path:
    try:
        path = safe_relative_path(
            root,
            relative,
            required_prefix="data",
        )
        path.relative_to(output_directory)
    except (OSError, ValueError) as error:
        raise FormalEvidenceBuildError(
            f"{label} must be a canonical path inside output_directory"
        ) from error
    return path


def _role_root_relative(output_relative: str, role: str) -> str:
    if role in FORMAL_INPUT_ROLES:
        return f"{output_relative}/roles/{role}"
    if role in FORMAL_COMPLETION_ROLES:
        return f"{output_relative}/completion/roles/{role}"
    raise FormalEvidenceBuildError(f"unknown formal evidence role: {role}")


def _validate_build_order() -> None:
    if set(FORMAL_EVIDENCE_BUILD_ORDER) != FORMAL_EVIDENCE_ROLES:
        raise RuntimeError("formal evidence build order does not cover all roles")
    seen: set[str] = set()
    for role in FORMAL_EVIDENCE_BUILD_ORDER:
        if not FORMAL_EVIDENCE_DEPENDENCIES[role] <= seen:
            raise RuntimeError(
                f"formal evidence build order violates dependencies for {role}"
            )
        seen.add(role)


@dataclass(frozen=True)
class _PreparedSupport:
    role: str
    relative_path: str
    source_path: Path | None
    json_content: Any | None


@dataclass(frozen=True)
class _PreparedBuild:
    raw: dict[str, Any]
    root: Path
    output_directory: Path
    output_relative: str
    input_lock_relative: str
    declarations_relative: str
    scenario_id: str
    domain_id: str
    family_id: str
    instance_id: str
    variants: tuple[str, ...]
    producer_commit: str
    supports: dict[str, tuple[_PreparedSupport, ...]]
    support_paths: frozenset[str]
    support_owners: dict[str, str]


def _prepare_build(
    raw: dict[str, Any],
    *,
    root: Path,
    trusted_producer_commit: str,
    required_source_roles: frozenset[str],
) -> _PreparedBuild:
    _validate_build_order()
    _json_bytes(raw)
    _require_exact_fields(raw, _BUILD_SPEC_FIELDS, label="build spec")
    if raw["schema_version"] != "1.0":
        raise FormalEvidenceBuildError("build spec schema_version must be 1.0")

    release_id = _require_identifier(
        raw["benchmark_release_id"],
        field="benchmark_release_id",
    )
    scenario_id = _require_identifier(raw["scenario_id"], field="scenario_id")
    domain_id = _require_identifier(raw["domain_id"], field="domain_id")
    family_id = _require_identifier(raw["family_id"], field="family_id")
    instance_id = _require_identifier(raw["instance_id"], field="instance_id")
    del release_id

    variants_raw = raw["variant_ids"]
    if not isinstance(variants_raw, list) or not variants_raw:
        raise FormalEvidenceBuildError(
            "variant_ids must be a non-empty JSON array"
        )
    variants = tuple(
        _require_identifier(value, field="variant_ids[]")
        for value in variants_raw
    )
    if len(variants) != len(set(variants)):
        raise FormalEvidenceBuildError("variant_ids must be unique")

    producer_commit = str(raw["producer_commit"])
    if (
        _GIT_COMMIT.fullmatch(producer_commit) is None
        or producer_commit != trusted_producer_commit
    ):
        raise FormalEvidenceBuildError(
            "producer_commit does not match the trusted repository commit"
        )

    try:
        scenario_path = safe_relative_path(
            root,
            str(raw["scenario_path"]),
            required_prefix="data",
            must_exist=True,
            require_file=True,
        )
        scenario_relative = scenario_path.relative_to(root)
    except (OSError, ValueError) as error:
        raise FormalEvidenceBuildError("scenario_path is unsafe") from error
    if (
        len(scenario_relative.parts) != 4
        or scenario_relative.parts[:2] != ("data", "scenarios")
        or scenario_relative.parts[-1] != "scenario.json"
    ):
        raise FormalEvidenceBuildError(
            "scenario_path must identify an active data/scenarios entry"
        )
    scenario = load_native_scenario(scenario_path)
    document_failures = validate_native_scenario_document(scenario)
    if document_failures:
        raise FormalEvidenceBuildError(
            "scenario document is invalid: "
            + ", ".join(document_failures)
        )
    if scenario.split not in _FORMAL_SPLITS:
        raise FormalEvidenceBuildError(
            "formal evidence can only be built for public_dev or hidden_test"
        )
    expected_identity = (
        scenario.scenario_id,
        scenario.domain_id,
        scenario.family_id,
        scenario.instance_id,
        scenario.variants,
    )
    declared_identity = (
        scenario_id,
        domain_id,
        family_id,
        instance_id,
        variants,
    )
    if declared_identity != expected_identity:
        raise FormalEvidenceBuildError(
            "declared identity does not match the active scenario"
        )

    output_relative = str(raw["output_directory"])
    try:
        output_directory = safe_relative_path(
            root,
            output_relative,
            required_prefix="data",
        )
    except (OSError, ValueError) as error:
        raise FormalEvidenceBuildError(
            "output_directory is unsafe"
        ) from error
    if len(Path(output_relative).parts) < 3:
        raise FormalEvidenceBuildError(
            "output_directory must be below a dedicated data subdirectory"
        )
    input_lock_relative = f"{output_relative}/formal-input-lock.json"
    declarations_relative = (
        f"{output_relative}/completion/declarations.json"
    )

    roles_raw = raw["roles"]
    if not isinstance(roles_raw, dict) or set(roles_raw) != FORMAL_EVIDENCE_ROLES:
        raise FormalEvidenceBuildError(
            "roles must contain exactly the seven formal evidence roles"
        )

    prepared: dict[str, tuple[_PreparedSupport, ...]] = {}
    all_support_paths: set[str] = set()
    support_owners: dict[str, str] = {}
    reserved_paths = {
        input_lock_relative,
        declarations_relative,
        *(
            f"{_role_root_relative(output_relative, role)}/{name}.json"
            for role in FORMAL_EVIDENCE_ROLES
            for name in ("primary", "envelope")
        ),
    }
    for role in FORMAL_EVIDENCE_BUILD_ORDER:
        role_spec = roles_raw[role]
        if not isinstance(role_spec, dict):
            raise FormalEvidenceBuildError(f"role {role} must be an object")
        _require_exact_fields(
            role_spec,
            _ROLE_SPEC_FIELDS,
            label=f"role {role}",
        )
        primary = role_spec["primary_payload"]
        if not isinstance(primary, dict):
            raise FormalEvidenceBuildError(
                f"role {role} primary_payload must be an object"
            )
        forged = sorted(set(primary) & _PRIMARY_IDENTITY_FIELDS)
        if forged:
            raise FormalEvidenceBuildError(
                f"role {role} attempts to supply generated identity fields: "
                f"{forged}"
            )
        supports_raw = role_spec["support_files"]
        if not isinstance(supports_raw, list):
            raise FormalEvidenceBuildError(
                f"role {role} support_files must be an array"
            )
        role_supports: list[_PreparedSupport] = []
        role_support_root = safe_relative_path(
            root,
            f"{_role_root_relative(output_relative, role)}/support",
            required_prefix="data",
        )
        for index, support in enumerate(supports_raw):
            label = f"role {role} support_files[{index}]"
            if not isinstance(support, dict):
                raise FormalEvidenceBuildError(f"{label} must be an object")
            fields = set(support)
            if fields not in {_SUPPORT_SOURCE_FIELDS, _SUPPORT_JSON_FIELDS}:
                raise FormalEvidenceBuildError(
                    f"{label} must contain path and exactly one content source"
                )
            relative = str(support["path"])
            destination = _relative_to_output(
                root=root,
                output_directory=output_directory,
                relative=relative,
                label=label,
            )
            try:
                destination.relative_to(role_support_root)
            except ValueError as error:
                raise FormalEvidenceBuildError(
                    f"{label} must be inside its role support directory"
                ) from error
            if relative in all_support_paths or relative in reserved_paths:
                raise FormalEvidenceBuildError(
                    f"duplicate or reserved output path: {relative}"
                )
            all_support_paths.add(relative)
            support_owners[relative] = role
            if "source_path" in support:
                try:
                    source_relative = str(support["source_path"])
                    source_parts = Path(source_relative).parts
                    if (
                        not source_parts
                        or source_parts[0]
                        not in _ALLOWED_SUPPORT_SOURCE_PREFIXES
                    ):
                        raise ValueError("source prefix is not allowed")
                    source = safe_relative_path(
                        root,
                        source_relative,
                        must_exist=role in required_source_roles,
                        require_file=role in required_source_roles,
                    )
                    if source.exists() and not source.is_file():
                        raise ValueError("source path is not a file")
                except (OSError, ValueError) as error:
                    raise FormalEvidenceBuildError(
                        f"{label} source_path is missing or unsafe"
                    ) from error
                role_supports.append(
                    _PreparedSupport(role, relative, source, None)
                )
            else:
                _json_bytes(support["json_content"])
                role_supports.append(
                    _PreparedSupport(
                        role,
                        relative,
                        None,
                        deepcopy(support["json_content"]),
                    )
                )
        prepared[role] = tuple(role_supports)

    return _PreparedBuild(
        raw=deepcopy(raw),
        root=root,
        output_directory=output_directory,
        output_relative=output_relative,
        input_lock_relative=input_lock_relative,
        declarations_relative=declarations_relative,
        scenario_id=scenario_id,
        domain_id=domain_id,
        family_id=family_id,
        instance_id=instance_id,
        variants=variants,
        producer_commit=producer_commit,
        supports=prepared,
        support_paths=frozenset(all_support_paths),
        support_owners=support_owners,
    )


@dataclass
class _TemplateContext:
    identity: dict[str, Any]
    current_role: str
    file_hashes: dict[str, str]
    envelope_hashes: dict[str, str]
    rendered_json_values: dict[str, Any]
    declared_support_paths: frozenset[str]
    support_owners: dict[str, str]
    referenced_file_hashes: set[str]
    input_lock_sha256: str | None = None
    formal_input_lock_verifications: dict[str, dict[str, Any]] | None = None


def _resolve_template(
    value: Any,
    *,
    context: _TemplateContext,
    field_name: str | None = None,
) -> Any:
    if isinstance(value, dict):
        keys = set(value)
        if keys == {"$file_sha256"}:
            relative = value["$file_sha256"]
            if (
                not isinstance(relative, str)
                or relative not in context.declared_support_paths
            ):
                raise FormalEvidenceBuildError(
                    "$file_sha256 must name a declared support output"
                )
            owner = context.support_owners[relative]
            permitted_owners = {
                context.current_role,
                *FORMAL_EVIDENCE_DEPENDENCIES[context.current_role],
            }
            if owner not in permitted_owners:
                raise FormalEvidenceBuildError(
                    "$file_sha256 crosses an undeclared role dependency"
                )
            digest = context.file_hashes.get(relative)
            if digest is None:
                raise FormalEvidenceBuildError(
                    f"support hash is not available yet: {relative}"
                )
            context.referenced_file_hashes.add(relative)
            return digest
        if keys == {"$envelope_sha256"}:
            role = value["$envelope_sha256"]
            if (
                not isinstance(role, str)
                or role
                not in FORMAL_EVIDENCE_DEPENDENCIES[context.current_role]
            ):
                raise FormalEvidenceBuildError(
                    "$envelope_sha256 must name a direct role dependency"
                )
            digest = context.envelope_hashes.get(role)
            if digest is None:
                raise FormalEvidenceBuildError(
                    f"envelope hash is not available yet: {role}"
                )
            return digest
        if keys == {"$role_dependencies"}:
            role = value["$role_dependencies"]
            if role != context.current_role:
                raise FormalEvidenceBuildError(
                    "$role_dependencies must name the current role"
                )
            dependencies = FORMAL_EVIDENCE_DEPENDENCIES[role]
            if not dependencies <= set(context.envelope_hashes):
                raise FormalEvidenceBuildError(
                    f"role dependencies are not available yet: {role}"
                )
            return {
                dependency: context.envelope_hashes[dependency]
                for dependency in sorted(dependencies)
            }
        if keys == {"$identity"}:
            identity_field = value["$identity"]
            if (
                not isinstance(identity_field, str)
                or identity_field not in context.identity
            ):
                raise FormalEvidenceBuildError(
                    "$identity names an unknown generated identity field"
                )
            return deepcopy(context.identity[identity_field])
        if keys == {"$bound_json_field"}:
            if field_name is not None and field_name.endswith("_sha256"):
                raise FormalEvidenceBuildError(
                    "$bound_json_field cannot populate a formal hash field"
                )
            selector = value["$bound_json_field"]
            if (
                not isinstance(selector, dict)
                or set(selector) != {"path", "field"}
                or not isinstance(selector.get("path"), str)
                or not isinstance(selector.get("field"), str)
            ):
                raise FormalEvidenceBuildError(
                    "$bound_json_field requires exact path and field strings"
                )
            relative = selector["path"]
            owner = context.support_owners.get(relative)
            permitted_owners = {
                context.current_role,
                *FORMAL_EVIDENCE_DEPENDENCIES[context.current_role],
            }
            source = context.rendered_json_values.get(relative)
            if (
                relative not in context.declared_support_paths
                or owner not in permitted_owners
                or relative not in context.file_hashes
                or not isinstance(source, dict)
                or selector["field"] not in source
            ):
                raise FormalEvidenceBuildError(
                    "$bound_json_field must select an available field from "
                    "a declared, hash-bound support JSON"
                )
            context.referenced_file_hashes.add(relative)
            return deepcopy(source[selector["field"]])
        if keys == {"$formal_input_lock_sha256"}:
            if value["$formal_input_lock_sha256"] is not True:
                raise FormalEvidenceBuildError(
                    "$formal_input_lock_sha256 must have the value true"
                )
            if context.input_lock_sha256 is None:
                raise FormalEvidenceBuildError(
                    "formal input lock hash is not available in this phase"
                )
            return context.input_lock_sha256
        if keys == {"$formal_input_lock_verification"}:
            variant_id = value["$formal_input_lock_verification"]
            verifications = context.formal_input_lock_verifications
            if (
                not isinstance(variant_id, str)
                or verifications is None
                or variant_id not in verifications
            ):
                raise FormalEvidenceBuildError(
                    "$formal_input_lock_verification must name a verified "
                    "completion variant"
                )
            return deepcopy(verifications[variant_id])
        if any(
            isinstance(key, str) and key.startswith("$")
            for key in keys
        ):
            raise FormalEvidenceBuildError(
                "unknown or malformed build-spec placeholder"
            )
        if field_name is not None and field_name.endswith("_sha256"):
            raise FormalEvidenceBuildError(
                f"{field_name} must use a builder-generated hash placeholder"
            )
        return {
            key: _resolve_template(
                nested,
                context=context,
                field_name=str(key),
            )
            for key, nested in value.items()
        }
    if field_name is not None and field_name.endswith("_sha256"):
        raise FormalEvidenceBuildError(
            f"{field_name} must use a builder-generated hash placeholder"
        )
    if isinstance(value, list):
        return [
            _resolve_template(item, context=context) for item in value
        ]
    return deepcopy(value)


def _stage_path(staging_root: Path, relative: str) -> Path:
    path = safe_relative_path(
        staging_root,
        relative,
        required_prefix="data",
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _write_bytes(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(value)


def _build_identity(prepared: _PreparedBuild) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "benchmark_release_id": prepared.raw["benchmark_release_id"],
        "scenario_id": prepared.scenario_id,
        "domain_id": prepared.domain_id,
        "family_id": prepared.family_id,
        "instance_id": prepared.instance_id,
        "variant_ids": list(prepared.variants),
        "producer_commit": prepared.producer_commit,
    }


@dataclass
class _BuildState:
    declarations: dict[str, dict[str, str]]
    envelope_hashes: dict[str, str]
    file_hashes: dict[str, str]
    rendered_json_values: dict[str, Any]


def _emit_roles(
    prepared: _PreparedBuild,
    *,
    staging_root: Path,
    roles: tuple[str, ...],
    state: _BuildState | None = None,
    input_lock_sha256: str | None = None,
    formal_input_lock_verifications: (
        dict[str, dict[str, Any]] | None
    ) = None,
) -> _BuildState:
    identity = _build_identity(prepared)
    state = state or _BuildState({}, {}, {}, {})
    for role in roles:
        dependencies = {
            dependency: state.envelope_hashes[dependency]
            for dependency in sorted(FORMAL_EVIDENCE_DEPENDENCIES[role])
        }
        context = _TemplateContext(
            identity=identity,
            current_role=role,
            file_hashes=state.file_hashes,
            envelope_hashes=state.envelope_hashes,
            rendered_json_values=state.rendered_json_values,
            declared_support_paths=prepared.support_paths,
            support_owners=prepared.support_owners,
            referenced_file_hashes=set(),
            input_lock_sha256=input_lock_sha256,
            formal_input_lock_verifications=(
                formal_input_lock_verifications
            ),
        )
        role_support_files: list[dict[str, str]] = []
        for support in prepared.supports[role]:
            destination = _stage_path(
                staging_root,
                support.relative_path,
            )
            if support.source_path is not None:
                try:
                    content = support.source_path.read_bytes()
                except OSError as error:
                    raise FormalEvidenceBuildError(
                        f"support source is unavailable: "
                        f"{support.source_path}"
                    ) from error
            else:
                resolved = _resolve_template(
                    support.json_content,
                    context=context,
                )
                content = _json_bytes(resolved)
            _write_bytes(destination, content)
            digest = _sha256_bytes(content)
            state.file_hashes[support.relative_path] = digest
            try:
                rendered_json = load_json_strict(destination)
            except (ValueError, json.JSONDecodeError):
                rendered_json = None
            if rendered_json is not None:
                state.rendered_json_values[support.relative_path] = (
                    rendered_json
                )
            role_support_files.append(
                {"path": support.relative_path, "sha256": digest}
            )

        # A support file may use another file's hash while being generated,
        # but that does not bind the support file into the role contract.
        # Require the primary payload itself to name every owned support file.
        context.referenced_file_hashes = set()
        primary_specific = _resolve_template(
            prepared.raw["roles"][role]["primary_payload"],
            context=context,
        )
        own_support_paths = {
            support.relative_path for support in prepared.supports[role]
        }
        if not own_support_paths <= context.referenced_file_hashes:
            unbound = sorted(
                own_support_paths - context.referenced_file_hashes
            )
            raise FormalEvidenceBuildError(
                f"role {role} has support files not hash-bound by its "
                f"primary payload: {unbound}"
            )
        primary_payload = {
            **identity,
            "artifact_type": role,
            "input_envelope_sha256": dependencies,
            **primary_specific,
        }
        role_relative = _role_root_relative(prepared.output_relative, role)
        primary_relative = f"{role_relative}/primary.json"
        primary_content = _json_bytes(primary_payload)
        primary_path = _stage_path(staging_root, primary_relative)
        _write_bytes(primary_path, primary_content)
        primary_hash = _sha256_bytes(primary_content)

        envelope = {
            **identity,
            "artifact_type": role,
            "depends_on": dependencies,
            "primary_payload_path": primary_relative,
            "files": [
                {"path": primary_relative, "sha256": primary_hash},
                *role_support_files,
            ],
        }
        envelope_relative = f"{role_relative}/envelope.json"
        envelope_content = _json_bytes(envelope)
        envelope_path = _stage_path(staging_root, envelope_relative)
        _write_bytes(envelope_path, envelope_content)
        envelope_hash = _sha256_bytes(envelope_content)
        state.envelope_hashes[role] = envelope_hash
        state.declarations[role] = {
            "path": envelope_relative,
            "sha256": envelope_hash,
        }
    return state


def _load_role_material(
    staging_root: Path,
    declaration: dict[str, str],
) -> tuple[dict[str, Any], dict[str, str]]:
    envelope_path = safe_relative_path(
        staging_root,
        declaration["path"],
        required_prefix="data",
        must_exist=True,
        require_file=True,
    )
    envelope = load_json_strict(envelope_path)
    if not isinstance(envelope, dict):
        raise FormalEvidenceBuildError("role envelope is not an object")
    local_hashes = {
        str(item.get("path", "")): str(item.get("sha256", ""))
        for item in envelope.get("files", ())
        if isinstance(item, dict)
    }
    primary_relative = str(envelope.get("primary_payload_path", ""))
    primary_path = safe_relative_path(
        staging_root,
        primary_relative,
        required_prefix="data",
        must_exist=True,
        require_file=True,
    )
    primary = load_json_strict(primary_path)
    if not isinstance(primary, dict):
        raise FormalEvidenceBuildError("role primary payload is not an object")
    return primary, local_hashes


def _bound_json(
    staging_root: Path,
    entry: dict[str, Any],
    *,
    path_field: str,
    sha_field: str,
    local_hashes: dict[str, str],
) -> dict[str, Any] | None:
    relative = entry.get(path_field)
    expected = entry.get(sha_field)
    if (
        not isinstance(relative, str)
        or not isinstance(expected, str)
        or local_hashes.get(relative) != expected
    ):
        return None
    try:
        payload = load_json_strict(
            safe_relative_path(
                staging_root,
                relative,
                required_prefix="data",
                must_exist=True,
                require_file=True,
            )
        )
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _variant_index(
    payload: dict[str, Any],
    variants: tuple[str, ...],
) -> dict[str, dict[str, Any]] | None:
    values = payload.get("variants")
    if not isinstance(values, list):
        return None
    result: dict[str, dict[str, Any]] = {}
    observed: list[str] = []
    for value in values:
        if not isinstance(value, dict):
            return None
        variant = str(value.get("variant_id", ""))
        if not variant or variant in result:
            return None
        observed.append(variant)
        result[variant] = value
    return result if tuple(observed) == variants else None


def _validate_input_semantics(
    prepared: _PreparedBuild,
    *,
    staging_root: Path,
    state: _BuildState,
) -> None:
    materials = {
        role: _load_role_material(
            staging_root,
            state.declarations[role],
        )
        for role in FORMAL_INPUT_ROLES
    }
    tool_payload, tool_files = materials["tool_contract"]
    tools = tool_payload.get("tools")
    tool_names: list[str] = []
    if not isinstance(tools, list) or not tools:
        raise FormalEvidenceBuildError("tool_contract has no tools")
    for tool in tools:
        if not isinstance(tool, dict):
            raise FormalEvidenceBuildError("tool contract entry is invalid")
        name = str(tool.get("name", ""))
        schema = _bound_json(
            staging_root,
            tool,
            path_field="input_schema_path",
            sha_field="input_schema_sha256",
            local_hashes=tool_files,
        )
        implementation_path = str(tool.get("implementation_path", ""))
        if (
            not name
            or schema is None
            or schema.get("type") != "object"
            or not isinstance(schema.get("properties"), dict)
            or tool_files.get(implementation_path)
            != tool.get("implementation_sha256")
        ):
            raise FormalEvidenceBuildError(
                "tool_contract contains an invalid bound tool"
            )
        tool_names.append(name)
    if len(tool_names) != len(set(tool_names)):
        raise FormalEvidenceBuildError("tool names must be unique")

    evaluator_payload, evaluator_files = materials["evaluator"]
    checks = evaluator_payload.get("checks")
    scored_fields = evaluator_payload.get("scored_state_fields")
    check_ids: list[str] = []
    if (
        not isinstance(checks, list)
        or not checks
        or not isinstance(scored_fields, list)
        or not scored_fields
        or not all(
            isinstance(value, str) and value for value in scored_fields
        )
    ):
        raise FormalEvidenceBuildError("evaluator payload is incomplete")
    for check in checks:
        if not isinstance(check, dict):
            raise FormalEvidenceBuildError("evaluator check is invalid")
        check_id = str(check.get("id", ""))
        implementation_path = str(check.get("implementation_path", ""))
        if (
            not check_id
            or evaluator_files.get(implementation_path)
            != check.get("implementation_sha256")
        ):
            raise FormalEvidenceBuildError(
                "evaluator check is not hash-bound"
            )
        check_ids.append(check_id)
    if len(check_ids) != len(set(check_ids)):
        raise FormalEvidenceBuildError("evaluator check IDs must be unique")

    reset_payload, reset_files = materials["reset_evidence"]
    boundary_payload, boundary_files = materials["boundary_bundle"]
    reference_payload, reference_files = materials["reference_bundle"]
    resets = _variant_index(reset_payload, prepared.variants)
    boundaries = _variant_index(boundary_payload, prepared.variants)
    references = _variant_index(reference_payload, prepared.variants)
    if resets is None or boundaries is None or references is None:
        raise FormalEvidenceBuildError(
            "input evidence variants are not exact"
        )
    prefix_snapshot = _bound_json(
        staging_root,
        reset_payload,
        path_field="prefix_path",
        sha_field="prefix_sha256",
        local_hashes=reset_files,
    )
    prefix_sha256 = str(reset_payload.get("prefix_sha256", ""))
    if prefix_snapshot is None or not prefix_snapshot:
        raise FormalEvidenceBuildError(
            "reset evidence has no unique hash-bound common prefix"
        )
    evaluator_envelope_hash = state.envelope_hashes["evaluator"]
    reference_dependencies = {
        dependency: state.envelope_hashes[dependency]
        for dependency in sorted(
            FORMAL_EVIDENCE_DEPENDENCIES["reference_bundle"]
        )
    }
    for variant in prepared.variants:
        reset = resets[variant]
        boundary = boundaries[variant]
        reference = references[variant]
        reset_snapshot = _bound_json(
            staging_root,
            reset,
            path_field="reset_snapshot_path",
            sha_field="reset_snapshot_sha256",
            local_hashes=reset_files,
        )
        boundary_state = _bound_json(
            staging_root,
            boundary,
            path_field="boundary_state_path",
            sha_field="boundary_state_sha256",
            local_hashes=boundary_files,
        )
        failure_surface = _bound_json(
            staging_root,
            boundary,
            path_field="failure_surface_path",
            sha_field="failure_surface_sha256",
            local_hashes=boundary_files,
        )
        raw_failure_report = _bound_json(
            staging_root,
            boundary,
            path_field="raw_failure_report_path",
            sha_field="raw_failure_report_sha256",
            local_hashes=boundary_files,
        )
        reference_start = _bound_json(
            staging_root,
            reference,
            path_field="reference_start_state_path",
            sha_field="reference_start_state_sha256",
            local_hashes=reference_files,
        )
        reference_trace = _bound_json(
            staging_root,
            reference,
            path_field="reference_trace_path",
            sha_field="reference_trace_sha256",
            local_hashes=reference_files,
        )
        terminal_state = _bound_json(
            staging_root,
            reference,
            path_field="terminal_state_path",
            sha_field="terminal_state_sha256",
            local_hashes=reference_files,
        )
        semantic_checks = {
            "reset_envelope_verified": reset.get("reset_verified") is True,
            "reset_snapshot_bound": reset_snapshot is not None,
            "reset_scenario_bound": (
                reset_snapshot is not None
                and reset_snapshot.get("scenario_id") == prepared.scenario_id
            ),
            "reset_variant_bound": (
                reset_snapshot is not None
                and reset_snapshot.get("variant_id") == variant
            ),
            "reset_phase_bound": (
                reset_snapshot is not None
                and reset_snapshot.get("phase") == "reset"
            ),
            "reset_snapshot_verified": (
                reset_snapshot is not None
                and reset_snapshot.get("reset_verified") is True
            ),
            "reset_prefix_bound": (
                reset_snapshot is not None
                and reset_snapshot.get("prefix_file_sha256") == prefix_sha256
            ),
            "boundary_envelope_verified": (
                boundary.get("boundary_validation_passed") is True
            ),
            "boundary_state_bound": boundary_state is not None,
            "boundary_scenario_bound": (
                boundary_state is not None
                and boundary_state.get("scenario_id") == prepared.scenario_id
            ),
            "boundary_variant_bound": (
                boundary_state is not None
                and boundary_state.get("variant_id") == variant
            ),
            "boundary_phase_bound": (
                boundary_state is not None
                and boundary_state.get("phase") == "boundary"
            ),
            "boundary_reset_bound": (
                boundary_state is not None
                and bound_reset_snapshot_sha256(boundary_state)
                == reset.get("reset_snapshot_sha256")
                and boundary.get("reset_snapshot_sha256")
                == reset.get("reset_snapshot_sha256")
            ),
            "failure_surface_bound": failure_surface is not None,
            "failure_surface_identity_bound": (
                failure_surface is not None
                and failure_surface.get("scenario_id") == prepared.scenario_id
                and failure_surface.get("variant_id") == variant
                and failure_surface.get("phase") == "failure_surface"
            ),
            "failure_surface_operation_present": (
                failure_surface is not None
                and isinstance(failure_surface.get("operation"), str)
                and bool(failure_surface.get("operation"))
            ),
            "failure_surface_result_present": (
                failure_surface is not None
                and isinstance(failure_surface.get("surface_result"), str)
                and bool(failure_surface.get("surface_result"))
            ),
            "raw_failure_report_present": bool(raw_failure_report),
            "reference_start_bound": reference_start is not None,
            "reference_start_hash_bound": (
                reference.get("reference_start_state_sha256")
                == boundary.get("boundary_state_sha256")
            ),
            "reference_starts_from_boundary": reference_start == boundary_state,
            "reference_evaluator_passed": (
                reference.get("evaluator_passed") is True
            ),
            "reference_boundary_bound": (
                reference.get("boundary_state_sha256")
                == boundary.get("boundary_state_sha256")
            ),
            "reference_trace_bound": reference_trace is not None,
            "reference_trace_identity_bound": (
                reference_trace is not None
                and reference_trace.get("scenario_id") == prepared.scenario_id
                and reference_trace.get("variant_id") == variant
                and reference_trace.get("phase") == "reference_trace"
            ),
            "reference_trace_boundary_bound": (
                reference_trace is not None
                and reference_trace.get("boundary_state_sha256")
                == boundary.get("boundary_state_sha256")
            ),
            "reference_trace_inputs_bound": (
                reference_trace is not None
                and reference_trace.get("input_envelope_sha256")
                == reference_dependencies
            ),
            "reference_trace_nonempty": (
                reference_trace is not None
                and isinstance(reference_trace.get("steps"), list)
                and bool(reference_trace.get("steps"))
            ),
            "terminal_state_bound": terminal_state is not None,
            "terminal_identity_bound": (
                terminal_state is not None
                and terminal_state.get("scenario_id") == prepared.scenario_id
                and terminal_state.get("variant_id") == variant
                and terminal_state.get("phase") == "terminal"
            ),
            "terminal_boundary_bound": (
                terminal_state is not None
                and terminal_state.get("boundary_state_sha256")
                == boundary.get("boundary_state_sha256")
            ),
            "terminal_evaluator_bound": (
                terminal_state is not None
                and terminal_state.get("evaluator_envelope_sha256")
                == evaluator_envelope_hash
            ),
            "terminal_evaluation_passed": (
                terminal_state is not None
                and isinstance(terminal_state.get("evaluation"), dict)
                and terminal_state["evaluation"].get("passed") is True
            ),
        }
        failed_semantics = [
            name for name, passed in semantic_checks.items() if not passed
        ]
        if failed_semantics:
            raise FormalEvidenceBuildError(
                f"input evidence semantics failed for variant {variant}: "
                + ", ".join(failed_semantics)
            )


def _input_projection(
    prepared: _PreparedBuild,
    state: _BuildState,
) -> dict[str, Any]:
    scenario_path = safe_relative_path(
        prepared.root,
        str(prepared.raw["scenario_path"]),
        required_prefix="data",
        must_exist=True,
        require_file=True,
    )
    return {
        **_build_identity(prepared),
        "scenario_path": str(prepared.raw["scenario_path"]),
        "scenario_sha256": file_sha256(scenario_path),
        "input_role_declarations": {
            role: state.declarations[role] for role in FORMAL_INPUT_ROLES
        },
    }


def _write_input_lock(
    prepared: _PreparedBuild,
    *,
    staging_root: Path,
    state: _BuildState,
) -> tuple[dict[str, Any], str]:
    projection = _input_projection(prepared, state)
    projection_hash = _sha256_bytes(_json_bytes(projection))
    lock = {
        **_build_identity(prepared),
        "artifact_type": "formal_input_lock",
        "scenario_path": projection["scenario_path"],
        "scenario_sha256": projection["scenario_sha256"],
        "input_role_declarations": projection[
            "input_role_declarations"
        ],
        "input_projection_sha256": projection_hash,
    }
    path = _stage_path(staging_root, prepared.input_lock_relative)
    content = _json_bytes(lock)
    _write_bytes(path, content)
    return lock, _sha256_bytes(content)


def _tree_signature(
    root: Path,
    *,
    ignore_completion: bool = False,
) -> dict[str, tuple[str, str]]:
    if not root.is_dir() or root.is_symlink():
        raise FormalEvidenceBuildError("evidence package root is not safe")
    result: dict[str, tuple[str, str]] = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if ignore_completion and (
            relative == "completion"
            or relative.startswith("completion/")
        ):
            continue
        if path.is_symlink():
            raise FormalEvidenceBuildError(
                f"evidence package contains a symlink: {relative}"
            )
        if path.is_dir():
            result[relative] = ("directory", "")
        elif path.is_file():
            result[relative] = ("file", file_sha256(path))
        else:
            raise FormalEvidenceBuildError(
                f"evidence package contains a special file: {relative}"
            )
    return result


def _verify_input_tree(
    *,
    expected_output: Path,
    actual_output: Path,
) -> None:
    expected = _tree_signature(expected_output, ignore_completion=True)
    actual = _tree_signature(actual_output, ignore_completion=True)
    if actual != expected:
        raise FormalEvidenceBuildError(
            "published formal inputs differ from the recomputed input lock"
        )


def _build_input_stage(
    prepared: _PreparedBuild,
    *,
    staging_root: Path,
) -> tuple[_BuildState, str]:
    state = _emit_roles(
        prepared,
        staging_root=staging_root,
        roles=FORMAL_INPUT_ROLES,
    )
    _validate_input_semantics(
        prepared,
        staging_root=staging_root,
        state=state,
    )
    _, lock_hash = _write_input_lock(
        prepared,
        staging_root=staging_root,
        state=state,
    )
    return state, lock_hash


def _expected_input_lock_verifications(
    prepared: _PreparedBuild,
    *,
    staging_root: Path,
    state: _BuildState,
) -> dict[str, dict[str, Any]]:
    """Re-verify each model-visible variant against the published phase 1.

    Completion is rendered only after this check.  In particular, the
    expected object embedded in a raw trajectory is not reconstructed from
    caller-supplied strings: it is the result of running the same verifier
    that gates provider access over the immutable, already-published input
    lock.
    """

    reset_payload, _ = _load_role_material(
        staging_root,
        state.declarations["reset_evidence"],
    )
    boundary_payload, _ = _load_role_material(
        staging_root,
        state.declarations["boundary_bundle"],
    )
    boundaries = _variant_index(boundary_payload, prepared.variants)
    if boundaries is None:
        raise FormalEvidenceBuildError(
            "cannot derive completion lock verification from boundaries"
        )
    locked_prefix_relative = str(reset_payload.get("prefix_path", ""))
    locked_prefix = safe_relative_path(
        prepared.root,
        locked_prefix_relative,
        required_prefix="data",
        must_exist=True,
        require_file=True,
    )
    scenario = load_native_scenario(
        safe_relative_path(
            prepared.root,
            str(prepared.raw["scenario_path"]),
            required_prefix="data",
            must_exist=True,
            require_file=True,
        )
    )
    try:
        active_prefix = scenario.resolve_artifact("prefix")
    except (KeyError, OSError, ValueError):
        active_prefix = locked_prefix
    if file_sha256(active_prefix) != file_sha256(locked_prefix):
        raise FormalEvidenceBuildError(
            "hash-bound prefix differs from the active scenario prefix"
        )

    result: dict[str, dict[str, Any]] = {}
    for variant_id in prepared.variants:
        raw_failure_relative = str(
            boundaries[variant_id].get("raw_failure_report_path", "")
        )
        raw_failure = safe_relative_path(
            prepared.root,
            raw_failure_relative,
            required_prefix="data",
            must_exist=True,
            require_file=True,
        )
        result[variant_id] = verify_formal_input_lock(
            prepared.root / prepared.input_lock_relative,
            root=prepared.root,
            scenario_id=prepared.scenario_id,
            domain_id=prepared.domain_id,
            family_id=prepared.family_id,
            instance_id=prepared.instance_id,
            variant_id=variant_id,
            failure_report_path=raw_failure,
            prefix_path=active_prefix,
            trusted_producer_commit=prepared.producer_commit,
        ).as_dict()
    return result


def _validate_completion_causality(
    *,
    prepared: _PreparedBuild,
    staging_root: Path,
    state: _BuildState,
    input_lock_sha256: str,
    lock_verifications: dict[str, dict[str, Any]],
) -> None:
    raw_payload, raw_files = _load_role_material(
        staging_root,
        state.declarations["raw_run_archive"],
    )
    boundary_payload, boundary_files = _load_role_material(
        staging_root,
        state.declarations["boundary_bundle"],
    )
    boundaries = _variant_index(boundary_payload, prepared.variants)
    if boundaries is None:
        raise FormalEvidenceBuildError(
            "completion cannot resolve the locked boundary variants"
        )
    runs = raw_payload.get("runs")
    if not isinstance(runs, list) or not runs:
        raise FormalEvidenceBuildError(
            "raw run archive contains no runs"
        )
    scenario_spec_sha256 = load_native_scenario(
        safe_relative_path(
            prepared.root,
            str(prepared.raw["scenario_path"]),
            required_prefix="data",
            must_exist=True,
            require_file=True,
        )
    ).raw.get("instance_spec_sha256")
    observed_run_ids: set[str] = set()
    observed_variants: set[str] = set()
    for run in runs:
        if (
            not isinstance(run, dict)
            or run.get("formal_input_lock_sha256")
            != input_lock_sha256
        ):
            raise FormalEvidenceBuildError(
                "raw run declaration is not bound to the formal input lock"
            )
        run_id = str(run.get("run_id", ""))
        variant_id = str(run.get("variant_id", ""))
        expected_lock = lock_verifications.get(variant_id)
        if (
            not run_id
            or run_id in observed_run_ids
            or variant_id not in prepared.variants
            or variant_id in observed_variants
            or expected_lock is None
            or run.get("execution_control") is not True
            or type(run.get("passed")) is not bool
        ):
            raise FormalEvidenceBuildError(
                "raw run declaration identity is invalid"
            )
        raw_run = _bound_json(
            staging_root,
            run,
            path_field="run_path",
            sha_field="run_sha256",
            local_hashes=raw_files,
        )
        raw_trajectory = _bound_json(
            staging_root,
            run,
            path_field="raw_trajectory_path",
            sha_field="raw_trajectory_sha256",
            local_hashes=raw_files,
        )
        pre_model_boundary = _bound_json(
            staging_root,
            run,
            path_field="pre_model_boundary_evidence_path",
            sha_field="pre_model_boundary_evidence_sha256",
            local_hashes=raw_files,
        )
        boundary_state = _bound_json(
            staging_root,
            boundaries[variant_id],
            path_field="boundary_state_path",
            sha_field="boundary_state_sha256",
            local_hashes=boundary_files,
        )
        pre_model_hash = run.get(
            "pre_model_boundary_evidence_sha256"
        )
        if (
            raw_run is None
            or raw_run.get("formal_input_lock_sha256")
            != input_lock_sha256
            or raw_run.get("scenario_id") != prepared.scenario_id
            or raw_run.get("variant_id") != variant_id
            or raw_run.get("run_id") != run_id
            or raw_run.get("raw_trajectory_path")
            != run.get("raw_trajectory_path")
            or raw_run.get("raw_trajectory_sha256")
            != run.get("raw_trajectory_sha256")
            or raw_run.get("pre_model_boundary_evidence_path")
            != run.get("pre_model_boundary_evidence_path")
            or raw_run.get("pre_model_boundary_evidence_sha256")
            != pre_model_hash
            or raw_run.get("execution_control") is not True
            or raw_run.get("passed") is not run.get("passed")
            or run.get("boundary_state_sha256")
            != expected_lock["boundary_state_sha256"]
            or pre_model_hash != run.get("boundary_state_sha256")
            or pre_model_boundary is None
            or boundary_state is None
            or pre_model_boundary != boundary_state
        ):
            raise FormalEvidenceBuildError(
                "raw run bytes are not bound to the formal input lock"
            )
        evaluation = (
            raw_trajectory.get("evaluation")
            if isinstance(raw_trajectory, dict)
            else None
        )
        trajectory_pre_model = (
            raw_trajectory.get("pre_model_boundary_evidence")
            if isinstance(raw_trajectory, dict)
            else None
        )
        source_basename = (
            trajectory_pre_model.get("source_basename")
            if isinstance(trajectory_pre_model, dict)
            else None
        )
        if (
            raw_trajectory is None
            or raw_trajectory.get("scenario_id") != prepared.scenario_id
            or raw_trajectory.get("instance_id") != prepared.instance_id
            or raw_trajectory.get("variant") != variant_id
            or raw_trajectory.get("run_id") != run_id
            or raw_trajectory.get("execution_control") is not True
            or not isinstance(evaluation, dict)
            or type(evaluation.get("passed")) is not bool
            or evaluation.get("passed") is not run.get("passed")
            or raw_trajectory.get("formal_input_lock") != expected_lock
            or not isinstance(trajectory_pre_model, dict)
            or set(trajectory_pre_model)
            != {"variant_id", "source_basename", "sha256"}
            or trajectory_pre_model.get("variant_id") != variant_id
            or trajectory_pre_model.get("sha256") != pre_model_hash
            or not isinstance(source_basename, str)
            or not source_basename
            or Path(source_basename).name != source_basename
        ):
            raise FormalEvidenceBuildError(
                "raw trajectory is not causally bound to its verified "
                "input lock and deterministic evaluation"
            )
        if (
            isinstance(scenario_spec_sha256, str)
            and scenario_spec_sha256
            and raw_trajectory.get("instance_spec_sha256")
            != scenario_spec_sha256
        ):
            raise FormalEvidenceBuildError(
                "raw trajectory instance specification is not exact"
            )
        observed_run_ids.add(run_id)
        observed_variants.add(variant_id)
    if observed_variants != set(prepared.variants):
        raise FormalEvidenceBuildError(
            "raw trajectory archive does not cover every variant exactly"
        )
    control_payload, _ = _load_role_material(
        staging_root,
        state.declarations["execution_control"],
    )
    if (
        control_payload.get("formal_input_lock_sha256")
        != input_lock_sha256
    ):
        raise FormalEvidenceBuildError(
            "execution control is not bound to the formal input lock"
        )


def _finish_completion_stage(
    prepared: _PreparedBuild,
    *,
    staging_root: Path,
    state: _BuildState,
) -> tuple[
    dict[str, dict[str, str]],
    dict[str, str | float],
]:
    input_lock_path = safe_relative_path(
        staging_root,
        prepared.input_lock_relative,
        required_prefix="data",
        must_exist=True,
        require_file=True,
    )
    input_lock_hash = file_sha256(input_lock_path)
    lock_verifications = _expected_input_lock_verifications(
        prepared,
        staging_root=staging_root,
        state=state,
    )
    state = _emit_roles(
        prepared,
        staging_root=staging_root,
        roles=FORMAL_COMPLETION_ROLES,
        state=state,
        input_lock_sha256=input_lock_hash,
        formal_input_lock_verifications=lock_verifications,
    )
    _validate_completion_causality(
        prepared=prepared,
        staging_root=staging_root,
        state=state,
        input_lock_sha256=input_lock_hash,
        lock_verifications=lock_verifications,
    )

    control_primary_path = _stage_path(
        staging_root,
        f"{_role_root_relative(prepared.output_relative, 'execution_control')}"
        "/primary.json",
    )
    control_primary = load_json_strict(control_primary_path)
    control_path = str(control_primary.get("control_summary_path", ""))
    control_hash = str(control_primary.get("control_summary_sha256", ""))
    control_evidence: dict[str, str | float] = {
        "path": control_path,
        "sha256": control_hash,
        "minimum_task_pass_rate": MIN_EXECUTION_CONTROL_PASS_RATE,
    }
    declarations_manifest = {
        **_build_identity(prepared),
        "artifact_type": "formal_evidence_declarations",
        "scenario_path": str(prepared.raw["scenario_path"]),
        "formal_input_lock": {
            "path": prepared.input_lock_relative,
            "sha256": input_lock_hash,
        },
        "formal_evidence": state.declarations,
        "control_evidence": control_evidence,
    }
    declarations_path = _stage_path(
        staging_root,
        prepared.declarations_relative,
    )
    _write_bytes(declarations_path, _json_bytes(declarations_manifest))

    # The completed-chain validator resolves the active scenario and its
    # prefix from the validation root.  They are copied outside the evidence
    # output solely for this read-only staging validation and are never part
    # of the atomically published completion subtree.
    scenario_relative = str(prepared.raw["scenario_path"])
    scenario_source = safe_relative_path(
        prepared.root,
        scenario_relative,
        required_prefix="data",
        must_exist=True,
        require_file=True,
    )
    _write_bytes(
        _stage_path(staging_root, scenario_relative),
        scenario_source.read_bytes(),
    )
    scenario = load_native_scenario(scenario_source)
    try:
        prefix_source = scenario.resolve_artifact("prefix")
        prefix_relative = prefix_source.relative_to(prepared.root).as_posix()
    except (KeyError, OSError, ValueError) as error:
        raise FormalEvidenceBuildError(
            "active scenario prefix cannot be staged for validation"
        ) from error
    _write_bytes(
        _stage_path(staging_root, prefix_relative),
        prefix_source.read_bytes(),
    )

    try:
        accepted = validate_formal_evidence_roles(
            root=staging_root,
            declarations=state.declarations,
            benchmark_release_id=str(prepared.raw["benchmark_release_id"]),
            scenario_id=prepared.scenario_id,
            domain_id=prepared.domain_id,
            family_id=prepared.family_id,
            instance_id=prepared.instance_id,
            variants=prepared.variants,
            control_evidence_path=control_path,
            control_evidence_sha256=control_hash,
            declarations_manifest_path=prepared.declarations_relative,
            declarations_manifest_sha256=file_sha256(declarations_path),
            require_trusted_evaluator=True,
        )
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise FormalEvidenceBuildError(
            "generated evidence could not be read by the authoritative "
            "formal validator"
        ) from error
    if not accepted:
        raise FormalEvidenceBuildError(
            "generated evidence failed the authoritative formal validator"
        )
    return state.declarations, control_evidence


def _trusted_commit(
    *,
    root: Path,
    override: str | None,
) -> str:
    trusted_commit = override or current_git_commit(root)
    if _GIT_COMMIT.fullmatch(trusted_commit) is None:
        raise FormalEvidenceBuildError(
            "trusted_producer_commit is not a full Git commit"
        )
    return trusted_commit


def _input_result(
    prepared: _PreparedBuild,
    *,
    state: _BuildState,
    lock_hash: str,
) -> FormalInputLockResult:
    return FormalInputLockResult(
        benchmark_release_id=str(prepared.raw["benchmark_release_id"]),
        scenario_id=prepared.scenario_id,
        output_directory=prepared.output_relative,
        input_lock_path=prepared.input_lock_relative,
        input_lock_sha256=lock_hash,
        input_evidence={
            role: state.declarations[role] for role in FORMAL_INPUT_ROLES
        },
    )


def build_formal_inputs(
    raw: dict[str, Any],
    *,
    root: str | Path | None = None,
    trusted_producer_commit: str | None = None,
) -> FormalInputLockResult:
    """Atomically publish only the five pre-model formal input roles."""

    resolved_root = (
        Path(root) if root is not None else repository_root()
    ).resolve()
    prepared = _prepare_build(
        raw,
        root=resolved_root,
        trusted_producer_commit=_trusted_commit(
            root=resolved_root,
            override=trusted_producer_commit,
        ),
        required_source_roles=frozenset(FORMAL_INPUT_ROLES),
    )
    prepared.output_directory.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(
        prefix=".afi-",
        dir=resolved_root,
    ) as temporary:
        staging_root = Path(temporary)
        state, lock_hash = _build_input_stage(
            prepared,
            staging_root=staging_root,
        )
        staged_output = safe_relative_path(
            staging_root,
            prepared.output_relative,
            required_prefix="data",
            must_exist=True,
        )
        if prepared.output_directory.exists():
            _verify_input_tree(
                expected_output=staged_output,
                actual_output=prepared.output_directory,
            )
            return _input_result(
                prepared,
                state=state,
                lock_hash=lock_hash,
            )
        try:
            os.rename(staged_output, prepared.output_directory)
        except OSError as error:
            if not prepared.output_directory.exists():
                raise FormalEvidenceBuildError(
                    "failed to atomically publish formal inputs"
                ) from error
            _verify_input_tree(
                expected_output=staged_output,
                actual_output=prepared.output_directory,
            )
        return _input_result(
            prepared,
            state=state,
            lock_hash=lock_hash,
        )


def _completion_result(
    prepared: _PreparedBuild,
    *,
    declarations: dict[str, dict[str, str]],
    control_evidence: dict[str, str | float],
) -> FormalEvidenceBuildResult:
    declarations_path = safe_relative_path(
        prepared.root,
        prepared.declarations_relative,
        required_prefix="data",
        must_exist=True,
        require_file=True,
    )
    return FormalEvidenceBuildResult(
        benchmark_release_id=str(prepared.raw["benchmark_release_id"]),
        scenario_id=prepared.scenario_id,
        output_directory=prepared.output_relative,
        declarations_manifest_path=prepared.declarations_relative,
        declarations_manifest_sha256=file_sha256(declarations_path),
        formal_evidence=declarations,
        control_evidence=control_evidence,
    )


def complete_formal_evidence(
    raw: dict[str, Any],
    *,
    root: str | Path | None = None,
    trusted_producer_commit: str | None = None,
) -> FormalEvidenceBuildResult:
    """Verify immutable inputs, then atomically append model-run evidence."""

    resolved_root = (
        Path(root) if root is not None else repository_root()
    ).resolve()
    prepared = _prepare_build(
        raw,
        root=resolved_root,
        trusted_producer_commit=_trusted_commit(
            root=resolved_root,
            override=trusted_producer_commit,
        ),
        required_source_roles=frozenset(FORMAL_EVIDENCE_ROLES),
    )
    if not prepared.output_directory.is_dir():
        raise FormalEvidenceBuildError(
            "formal inputs must be published before completion"
        )
    with TemporaryDirectory(
        prefix=".afc-",
        dir=resolved_root,
    ) as temporary:
        staging_root = Path(temporary)
        state, _ = _build_input_stage(
            prepared,
            staging_root=staging_root,
        )
        staged_output = safe_relative_path(
            staging_root,
            prepared.output_relative,
            required_prefix="data",
            must_exist=True,
        )
        _verify_input_tree(
            expected_output=staged_output,
            actual_output=prepared.output_directory,
        )
        declarations, control_evidence = _finish_completion_stage(
            prepared,
            staging_root=staging_root,
            state=state,
        )
        staged_completion = staged_output / "completion"
        final_completion = prepared.output_directory / "completion"
        if final_completion.exists():
            if _tree_signature(final_completion) != _tree_signature(
                staged_completion
            ):
                raise FormalEvidenceBuildError(
                    "published formal completion differs from recomputation"
                )
            return _completion_result(
                prepared,
                declarations=declarations,
                control_evidence=control_evidence,
            )

        # Recheck immediately before the only write to the published package.
        _verify_input_tree(
            expected_output=staged_output,
            actual_output=prepared.output_directory,
        )
        try:
            os.rename(staged_completion, final_completion)
        except OSError as error:
            if not final_completion.exists():
                raise FormalEvidenceBuildError(
                    "failed to atomically publish formal completion"
                ) from error
            if _tree_signature(final_completion) != _tree_signature(
                staged_completion
            ):
                raise FormalEvidenceBuildError(
                    "a concurrent completion published different bytes"
                ) from error
        return _completion_result(
            prepared,
            declarations=declarations,
            control_evidence=control_evidence,
        )


def build_formal_evidence(
    raw: dict[str, Any],
    *,
    root: str | Path | None = None,
    trusted_producer_commit: str | None = None,
) -> FormalEvidenceBuildResult:
    """Run the causal two-phase build in one process.

    The function deliberately does not update ``data/release_manifest.json``.
    Passing this packager is necessary but not sufficient for formal release:
    the scenario still has to pass the independent release-slot gates.
    """

    build_formal_inputs(
        raw,
        root=root,
        trusted_producer_commit=trusted_producer_commit,
    )
    return complete_formal_evidence(
        raw,
        root=root,
        trusted_producer_commit=trusted_producer_commit,
    )


__all__ = [
    "FORMAL_COMPLETION_ROLES",
    "FORMAL_EVIDENCE_BUILD_ORDER",
    "FORMAL_INPUT_ROLES",
    "FormalEvidenceBuildError",
    "FormalEvidenceBuildResult",
    "FormalInputLockResult",
    "FormalInputLockVerification",
    "build_formal_evidence",
    "build_formal_inputs",
    "complete_formal_evidence",
    "current_git_commit",
    "load_formal_evidence_build_spec",
    "verify_formal_input_lock",
]
