from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .native_admission import validate_native_scenario
from .native_scenario import (
    load_native_scenario,
    validate_native_scenario_document,
)
from .path_safety import safe_relative_path
from .release_manifest import (
    FORMAL_EVIDENCE_ROLES,
    MIN_EXECUTION_CONTROL_PASS_RATE,
    file_sha256,
    validate_formal_evidence_roles,
)
from .strict_json import load_json_strict

_GIT_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_DECLARATION_FIELDS = frozenset(
    {
        "artifact_type",
        "benchmark_release_id",
        "control_evidence",
        "domain_id",
        "family_id",
        "formal_evidence",
        "formal_input_lock",
        "instance_id",
        "producer_commit",
        "scenario_id",
        "scenario_path",
        "schema_version",
        "variant_ids",
    }
)


class FormalReleaseBindingError(ValueError):
    """Raised when formal evidence cannot produce a release-slot binding."""


def _repository_file(root: Path, value: str | Path, *, label: str) -> Path:
    source = Path(value)
    try:
        relative = (
            source.resolve(strict=True).relative_to(root).as_posix()
            if source.is_absolute()
            else source.as_posix()
        )
        return safe_relative_path(
            root,
            relative,
            required_prefix="data",
            must_exist=True,
            require_file=True,
        )
    except (OSError, ValueError) as error:
        raise FormalReleaseBindingError(
            f"{label} must be a regular repository data file"
        ) from error


def _bound_file(
    root: Path,
    declaration: Any,
    *,
    label: str,
    extra_fields: frozenset[str] = frozenset(),
) -> dict[str, Any]:
    if not isinstance(declaration, dict) or set(declaration) != (
        {"path", "sha256"} | extra_fields
    ):
        raise FormalReleaseBindingError(f"{label} declaration is invalid")
    path = _repository_file(root, str(declaration.get("path", "")), label=label)
    digest = file_sha256(path)
    if digest != declaration.get("sha256"):
        raise FormalReleaseBindingError(f"{label} SHA-256 does not match")
    return {
        "path": path.relative_to(root).as_posix(),
        "sha256": digest,
    }


def generate_formal_release_binding(
    *,
    root: str | Path,
    scenario_path: str | Path,
    declarations_path: str | Path,
) -> dict[str, Any]:
    """Derive one release-slot declaration solely from verified source files."""

    repository = Path(root).resolve()
    if not repository.is_dir():
        raise FormalReleaseBindingError("repository root does not exist")
    scenario_file = _repository_file(
        repository,
        scenario_path,
        label="scenario",
    )
    declarations_file = _repository_file(
        repository,
        declarations_path,
        label="formal declarations",
    )
    scenario = load_native_scenario(scenario_file)
    document_failures = validate_native_scenario_document(scenario)
    if document_failures:
        raise FormalReleaseBindingError(
            "scenario document is invalid: " + ", ".join(document_failures)
        )
    if scenario.split not in {"public_dev", "hidden_test"}:
        raise FormalReleaseBindingError(
            "release slots require a public_dev or hidden_test scenario"
        )
    admission = validate_native_scenario(scenario)
    if not admission.passed or admission.admitted_tier != "hard":
        raise FormalReleaseBindingError(
            "scenario does not pass replay-derived hard admission"
        )

    declarations = load_json_strict(declarations_file)
    if not isinstance(declarations, dict) or set(declarations) != _DECLARATION_FIELDS:
        raise FormalReleaseBindingError("formal declaration fields are not exact")
    variants = scenario.variants
    scenario_relative = scenario_file.relative_to(repository).as_posix()
    identity_matches = (
        declarations.get("schema_version") == "1.0"
        and declarations.get("artifact_type") == "formal_evidence_declarations"
        and declarations.get("scenario_id") == scenario.scenario_id
        and declarations.get("domain_id") == scenario.domain_id
        and declarations.get("family_id") == scenario.family_id
        and declarations.get("instance_id") == scenario.instance_id
        and declarations.get("scenario_path") == scenario_relative
        and tuple(map(str, declarations.get("variant_ids", ()))) == variants
        and _GIT_COMMIT.fullmatch(str(declarations.get("producer_commit", "")))
        is not None
    )
    if not identity_matches:
        raise FormalReleaseBindingError(
            "formal declarations do not match the active scenario"
        )

    formal = declarations.get("formal_evidence")
    if not isinstance(formal, dict) or set(formal) != FORMAL_EVIDENCE_ROLES:
        raise FormalReleaseBindingError("formal evidence roles are incomplete")
    bound_formal = {
        role: _bound_file(
            repository,
            formal[role],
            label=f"formal role {role}",
        )
        for role in sorted(FORMAL_EVIDENCE_ROLES)
    }
    control = _bound_file(
        repository,
        declarations.get("control_evidence"),
        label="execution-control summary",
        extra_fields=frozenset({"minimum_task_pass_rate"}),
    )
    minimum_rate = float(
        declarations.get("control_evidence", {}).get(
            "minimum_task_pass_rate",
            -1,
        )
    )
    if abs(minimum_rate - MIN_EXECUTION_CONTROL_PASS_RATE) > 1e-12:
        raise FormalReleaseBindingError(
            "execution-control threshold differs from release policy"
        )
    control["minimum_task_pass_rate"] = minimum_rate
    declarations_digest = file_sha256(declarations_file)
    if not validate_formal_evidence_roles(
        root=repository,
        declarations=bound_formal,
        benchmark_release_id=str(declarations["benchmark_release_id"]),
        scenario_id=scenario.scenario_id,
        domain_id=scenario.domain_id,
        family_id=scenario.family_id,
        instance_id=scenario.instance_id,
        variants=variants,
        control_evidence_path=control["path"],
        control_evidence_sha256=control["sha256"],
        declarations_manifest_path=(
            declarations_file.relative_to(repository).as_posix()
        ),
        declarations_manifest_sha256=declarations_digest,
        require_trusted_evaluator=True,
    ):
        raise FormalReleaseBindingError(
            "seven-role formal evidence failed release validation"
        )

    admission_hashes = {
        key: file_sha256(scenario.resolve_artifact(key))
        for key in sorted(scenario.raw["admission_artifacts"])
    }
    return {
        "quality_role": "release_slot",
        "scenario_path": scenario_relative,
        "scenario_sha256": file_sha256(scenario_file),
        "scenario_id": scenario.scenario_id,
        "domain_id": scenario.domain_id,
        "family_id": scenario.family_id,
        "instance_id": scenario.instance_id,
        "split": scenario.split,
        "variant_ids": list(variants),
        "admission_artifact_sha256": admission_hashes,
        "control_evidence": control,
        "formal_evidence_declarations": {
            "path": declarations_file.relative_to(repository).as_posix(),
            "sha256": declarations_digest,
        },
        "formal_evidence": bound_formal,
    }


__all__ = [
    "FormalReleaseBindingError",
    "generate_formal_release_binding",
]
