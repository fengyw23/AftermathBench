from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .release_manifest import MIN_EXECUTION_CONTROL_PASS_RATE
from .strict_json import load_json_strict

SOURCE_WORKFLOW = ".github/workflows/forgejo-publication-public-dev.yml"
_GIT_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_ARTIFACT_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_GATE_FIELDS = frozenset(
    {
        "schema_version",
        "stage",
        "source_run_id",
        "source_commit",
        "artifact_name",
        "artifact_digest",
        "expected_cases",
        "minimum_pass_rate",
        "scenario_id",
        "formal_relative_root",
    }
)


class ForgejoEvidenceImportError(ValueError):
    """Raised when Forgejo public-development evidence is not importable."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _safe_relative(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ForgejoEvidenceImportError(f"{label} is invalid")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or "\\" in value:
        raise ForgejoEvidenceImportError(f"{label} is unsafe")
    return path.as_posix()


@dataclass(frozen=True)
class ForgejoEvidenceImportGate:
    source_run_id: int
    source_commit: str
    artifact_name: str
    artifact_digest: str
    expected_cases: int
    minimum_pass_rate: float
    scenario_id: str
    formal_relative_root: str

    @classmethod
    def from_mapping(cls, value: Any) -> ForgejoEvidenceImportGate:
        if not isinstance(value, Mapping) or set(value) != _GATE_FIELDS:
            raise ForgejoEvidenceImportError("Forgejo import gate fields are not exact")
        if value.get("schema_version") != "1.0":
            raise ForgejoEvidenceImportError("Forgejo import gate schema is invalid")
        if value.get("stage") != "forgejo-public-dev-evidence-import":
            raise ForgejoEvidenceImportError("Forgejo import gate stage is invalid")
        run_id = value.get("source_run_id")
        if type(run_id) is not int or int(run_id) <= 0:
            raise ForgejoEvidenceImportError("source_run_id is invalid")
        commit = str(value.get("source_commit", ""))
        if _GIT_COMMIT.fullmatch(commit) is None:
            raise ForgejoEvidenceImportError("source_commit is invalid")
        expected_name = f"forgejo-publication-public-dev-evidence-{run_id}"
        if value.get("artifact_name") != expected_name:
            raise ForgejoEvidenceImportError("artifact_name is not bound to the run id")
        artifact_digest = str(value.get("artifact_digest", ""))
        if _ARTIFACT_DIGEST.fullmatch(artifact_digest) is None:
            raise ForgejoEvidenceImportError("artifact_digest is invalid")
        expected_cases = value.get("expected_cases")
        if type(expected_cases) is not int or int(expected_cases) < 1:
            raise ForgejoEvidenceImportError("expected_cases is invalid")
        threshold = value.get("minimum_pass_rate")
        if type(threshold) not in {int, float} or isinstance(threshold, bool):
            raise ForgejoEvidenceImportError("minimum_pass_rate is invalid")
        if abs(float(threshold) - MIN_EXECUTION_CONTROL_PASS_RATE) > 1e-12:
            raise ForgejoEvidenceImportError("threshold differs from release policy")
        scenario_id = value.get("scenario_id")
        if (
            not isinstance(scenario_id, str)
            or re.fullmatch(r"[a-z0-9][a-z0-9._-]*", scenario_id) is None
        ):
            raise ForgejoEvidenceImportError("scenario_id is invalid")
        formal_root = _safe_relative(
            value.get("formal_relative_root"), label="formal_relative_root"
        )
        if not formal_root.startswith("data/evidence/formal/"):
            raise ForgejoEvidenceImportError(
                "formal_relative_root is outside formal evidence"
            )
        return cls(
            source_run_id=int(run_id),
            source_commit=commit,
            artifact_name=expected_name,
            artifact_digest=artifact_digest,
            expected_cases=int(expected_cases),
            minimum_pass_rate=float(threshold),
            scenario_id=scenario_id,
            formal_relative_root=formal_root,
        )

    @classmethod
    def from_path(cls, path: str | Path) -> ForgejoEvidenceImportGate:
        return cls.from_mapping(load_json_strict(path))

    def github_environment(self) -> dict[str, str]:
        return {
            "SOURCE_RUN_ID": str(self.source_run_id),
            "SOURCE_COMMIT": self.source_commit,
            "SOURCE_ARTIFACT": self.artifact_name,
            "SCENARIO_ID": self.scenario_id,
            "FORMAL_RELATIVE_ROOT": self.formal_relative_root,
        }


def validate_source_run(value: Any, *, gate: ForgejoEvidenceImportGate) -> None:
    if not isinstance(value, Mapping):
        raise ForgejoEvidenceImportError("source run metadata is invalid")
    checks = {
        "run_id": value.get("id") == gate.source_run_id,
        "commit": value.get("head_sha") == gate.source_commit,
        "status": value.get("status") == "completed",
        "conclusion": value.get("conclusion") == "success",
        "workflow": value.get("path") == SOURCE_WORKFLOW,
    }
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise ForgejoEvidenceImportError(
            "source run provenance failed: " + ", ".join(failures)
        )


def select_artifact(value: Any, *, gate: ForgejoEvidenceImportGate) -> dict[str, Any]:
    if not isinstance(value, Mapping) or not isinstance(
        value.get("artifacts"), Sequence
    ):
        raise ForgejoEvidenceImportError("artifact metadata is invalid")
    matches = [
        dict(item)
        for item in value["artifacts"]
        if isinstance(item, Mapping) and item.get("name") == gate.artifact_name
    ]
    if len(matches) != 1:
        raise ForgejoEvidenceImportError("artifact provenance is not unique")
    artifact = matches[0]
    checks = {
        "id": type(artifact.get("id")) is int and int(artifact["id"]) > 0,
        "not_expired": artifact.get("expired") is False,
        "size": type(artifact.get("size_in_bytes")) is int
        and int(artifact["size_in_bytes"]) > 0,
        "digest": artifact.get("digest") == gate.artifact_digest,
    }
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise ForgejoEvidenceImportError(
            "artifact metadata failed: " + ", ".join(failures)
        )
    return artifact


def validate_artifact_layout(
    stage: str | Path, *, gate: ForgejoEvidenceImportGate
) -> dict[str, Path]:
    root = Path(stage).resolve(strict=True)
    if not root.is_dir():
        raise ForgejoEvidenceImportError("artifact root is not a directory")
    for path in root.rglob("*"):
        if path.is_symlink():
            raise ForgejoEvidenceImportError(f"artifact contains a symlink: {path}")
    scenario = (
        root / "repo-ready" / "data" / "scenarios" / gate.scenario_id / "scenario.json"
    )
    formal = root / "repo-ready" / gate.formal_relative_root
    declarations = formal / "completion" / "declarations.json"
    status_path = root / "publication-status.json"
    files = root / "files.json"
    omissions = root / "omissions.json"
    required = {
        "scenario": scenario,
        "declarations": declarations,
        "publication_status": status_path,
        "files": files,
        "omissions": omissions,
    }
    missing = [name for name, path in required.items() if not path.is_file()]
    if missing:
        raise ForgejoEvidenceImportError(
            "artifact required files are missing: " + ", ".join(missing)
        )
    repo_ready = root / "repo-ready"
    allowed_roots = {
        (repo_ready / "data" / "scenarios" / gate.scenario_id).resolve(),
        formal.resolve(),
    }
    for path in repo_ready.rglob("*"):
        if path.is_file() and not any(
            parent in path.resolve().parents for parent in allowed_roots
        ):
            raise ForgejoEvidenceImportError(
                f"unexpected repository-ready file: {path.relative_to(repo_ready)}"
            )
    status = load_json_strict(status_path)
    validate_publication_status(
        status,
        gate=gate,
        scenario_sha256=_sha256(scenario),
        declarations_sha256=_sha256(declarations),
    )
    return required | {"repo_ready": repo_ready, "formal": formal}


def validate_publication_status(
    value: Any,
    *,
    gate: ForgejoEvidenceImportGate,
    scenario_sha256: str,
    declarations_sha256: str,
) -> None:
    if not isinstance(value, Mapping):
        raise ForgejoEvidenceImportError("publication status is invalid")
    control = value.get("control")
    formal = value.get("formal")
    safety = value.get("safety")
    checks = {
        "schema": value.get("schema_version") == "1.0",
        "type": value.get("artifact_type")
        == "forgejo_public_development_publication_status",
        "formal_complete": value.get("formal_complete") is True,
        "control_gate": value.get("control_gate_pass") is True,
        "promotion": value.get("release_promotion_eligible") is True,
        "control": isinstance(control, Mapping),
        "formal": isinstance(formal, Mapping),
        "safety": isinstance(safety, Mapping),
    }
    if isinstance(control, Mapping):
        rate = control.get("task_pass_rate")
        checks.update(
            {
                "summary_valid": control.get("summary_valid") is True,
                "expected_cases": control.get("expected_cases") == gate.expected_cases,
                "completed_runs": control.get("completed_runs") == gate.expected_cases,
                "passed_runs": control.get("passed_runs") == gate.expected_cases,
                "threshold": control.get("minimum_pass_rate") == gate.minimum_pass_rate,
                "pass_rate": isinstance(rate, (int, float))
                and float(rate) >= gate.minimum_pass_rate,
            }
        )
    if isinstance(formal, Mapping):
        checks.update(
            {
                "declarations_present": formal.get("declarations_present") is True,
                "declarations_hash": formal.get("declarations_sha256")
                == declarations_sha256,
            }
        )
    if isinstance(safety, Mapping):
        checks.update(
            {
                "secret_scan": safety.get("provider_secret_scan_passed") is True,
                "scenario_present": safety.get("scenario_present") is True,
                "scenario_hash": safety.get("scenario_sha256") == scenario_sha256,
            }
        )
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise ForgejoEvidenceImportError(
            "publication status failed: " + ", ".join(failures)
        )


def build_import_provenance(
    *, gate: ForgejoEvidenceImportGate, artifact: Mapping[str, Any], import_commit: str
) -> dict[str, Any]:
    if _GIT_COMMIT.fullmatch(import_commit) is None:
        raise ForgejoEvidenceImportError("import commit is invalid")
    selected = select_artifact({"artifacts": [dict(artifact)]}, gate=gate)
    return {
        "schema_version": "1.0",
        "stage": "forgejo-public-dev-evidence-import",
        "import_commit": import_commit,
        "source_run_id": gate.source_run_id,
        "source_commit": gate.source_commit,
        "artifact": {
            "id": selected["id"],
            "name": selected["name"],
            "digest": selected["digest"],
            "size_in_bytes": selected["size_in_bytes"],
        },
    }


__all__ = [
    "SOURCE_WORKFLOW",
    "ForgejoEvidenceImportError",
    "ForgejoEvidenceImportGate",
    "build_import_provenance",
    "select_artifact",
    "validate_artifact_layout",
    "validate_publication_status",
    "validate_source_run",
]
