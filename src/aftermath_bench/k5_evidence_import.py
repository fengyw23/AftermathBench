from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .release_manifest import MIN_EXECUTION_CONTROL_PASS_RATE
from .strict_json import load_json_strict

K4_WORKFLOW_PATH = (
    ".github/workflows/kubernetes-interaction-execution-control.yml"
)
K4_MODEL_ID = "glm-5.2"
K4_EXPECTED_CASES = 13
_GIT_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_ARTIFACT_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_GATE_FIELDS = frozenset(
    {
        "schema_version",
        "stage",
        "k4_run_id",
        "k4_commit",
        "k4_artifact",
        "source_run_id",
        "source_commit",
        "minimum_pass_rate",
    }
)
_SUMMARY_FIELDS = frozenset(
    {
        "schema_version",
        "stage",
        "source_run_id",
        "source_commit",
        "model",
        "expected_cases",
        "minimum_pass_rate",
        "completed_runs",
        "task_pass_rate",
        "matched_group_count",
        "matched_group_success_rate",
        "component_pass_rates",
        "failure_type_counts",
        "execution_control_counts",
        "run_error_count",
    }
)


class K5EvidenceImportError(ValueError):
    """Raised when reviewed K4 evidence cannot enter the K5 import gate."""


@dataclass(frozen=True)
class K5EvidenceImportGate:
    k4_run_id: int
    k4_commit: str
    k4_artifact: str
    source_run_id: int
    source_commit: str
    minimum_pass_rate: float

    @classmethod
    def from_mapping(cls, value: Any) -> K5EvidenceImportGate:
        if not isinstance(value, Mapping) or set(value) != _GATE_FIELDS:
            raise K5EvidenceImportError("K5 gate fields are not exact")
        if value.get("schema_version") != "1.0":
            raise K5EvidenceImportError("K5 gate schema is invalid")
        if value.get("stage") != "K5-evidence-import":
            raise K5EvidenceImportError("K5 gate stage is invalid")
        for key in ("k4_run_id", "source_run_id"):
            if type(value.get(key)) is not int or int(value[key]) <= 0:
                raise K5EvidenceImportError(f"{key} is invalid")
        for key in ("k4_commit", "source_commit"):
            if _GIT_COMMIT.fullmatch(str(value.get(key, ""))) is None:
                raise K5EvidenceImportError(f"{key} is invalid")
        expected_artifact = (
            f"kubernetes-execution-control-{value['k4_run_id']}"
        )
        if value.get("k4_artifact") != expected_artifact:
            raise K5EvidenceImportError(
                "K4 artifact name is not bound to the run id"
            )
        threshold = value.get("minimum_pass_rate")
        if type(threshold) not in {int, float} or isinstance(threshold, bool):
            raise K5EvidenceImportError("minimum_pass_rate is invalid")
        if (
            abs(float(threshold) - MIN_EXECUTION_CONTROL_PASS_RATE)
            > 1e-12
        ):
            raise K5EvidenceImportError(
                "K4 threshold differs from release policy"
            )
        return cls(
            k4_run_id=int(value["k4_run_id"]),
            k4_commit=str(value["k4_commit"]),
            k4_artifact=str(value["k4_artifact"]),
            source_run_id=int(value["source_run_id"]),
            source_commit=str(value["source_commit"]),
            minimum_pass_rate=float(threshold),
        )

    @classmethod
    def from_path(cls, path: str | Path) -> K5EvidenceImportGate:
        return cls.from_mapping(load_json_strict(path))

    def github_environment(self) -> dict[str, str]:
        return {
            "K4_RUN_ID": str(self.k4_run_id),
            "K4_COMMIT": self.k4_commit,
            "K4_ARTIFACT": self.k4_artifact,
            "SOURCE_RUN_ID": str(self.source_run_id),
            "SOURCE_COMMIT": self.source_commit,
            "CONTROL_MIN_PASS_RATE": str(self.minimum_pass_rate),
        }


def validate_k4_run_metadata(
    value: Any,
    *,
    gate: K5EvidenceImportGate,
) -> None:
    if not isinstance(value, Mapping):
        raise K5EvidenceImportError("K4 run metadata is invalid")
    checks = {
        "run_id": value.get("id") == gate.k4_run_id,
        "commit": value.get("head_sha") == gate.k4_commit,
        "status": value.get("status") == "completed",
        "conclusion": value.get("conclusion") == "success",
        "workflow": value.get("path") == K4_WORKFLOW_PATH,
    }
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise K5EvidenceImportError(
            "K4 run provenance failed: " + ", ".join(failures)
        )


def select_k4_artifact_metadata(
    value: Any,
    *,
    gate: K5EvidenceImportGate,
) -> dict[str, Any]:
    if not isinstance(value, Mapping) or not isinstance(
        value.get("artifacts"), Sequence
    ):
        raise K5EvidenceImportError("K4 artifact metadata is invalid")
    matches = [
        item
        for item in value["artifacts"]
        if isinstance(item, Mapping)
        and item.get("name") == gate.k4_artifact
    ]
    if len(matches) != 1:
        raise K5EvidenceImportError("K4 artifact provenance is not unique")
    artifact = dict(matches[0])
    checks = {
        "id": type(artifact.get("id")) is int
        and int(artifact["id"]) > 0,
        "not_expired": artifact.get("expired") is False,
        "size": type(artifact.get("size_in_bytes")) is int
        and int(artifact["size_in_bytes"]) > 0,
        "digest": _ARTIFACT_DIGEST.fullmatch(
            str(artifact.get("digest", ""))
        )
        is not None,
    }
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise K5EvidenceImportError(
            "K4 artifact metadata failed: " + ", ".join(failures)
        )
    return artifact


def validate_k4_public_summary(
    value: Any,
    *,
    gate: K5EvidenceImportGate,
) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _SUMMARY_FIELDS:
        raise K5EvidenceImportError("K4 public summary fields are not exact")
    try:
        pass_rate = float(value["task_pass_rate"])
        threshold = float(value["minimum_pass_rate"])
    except (KeyError, TypeError, ValueError) as error:
        raise K5EvidenceImportError(
            "K4 public summary rates are invalid"
        ) from error
    implied_passes = round(pass_rate * K4_EXPECTED_CASES)
    discrete_rate = implied_passes / K4_EXPECTED_CASES
    execution_counts = value.get("execution_control_counts")
    checks = {
        "schema": value.get("schema_version") == "1.0",
        "stage": value.get("stage") == "K4-execution-control",
        "source_run": value.get("source_run_id") == gate.source_run_id,
        "source_commit": value.get("source_commit") == gate.source_commit,
        "model": value.get("model") == K4_MODEL_ID,
        "expected_cases": value.get("expected_cases") == K4_EXPECTED_CASES,
        "completed_runs": value.get("completed_runs") == K4_EXPECTED_CASES,
        "threshold": abs(threshold - gate.minimum_pass_rate) <= 1e-12,
        "pass_rate_range": 0.0 <= pass_rate <= 1.0,
        "pass_rate_is_discrete": abs(pass_rate - discrete_rate) <= 1e-12,
        "pass_rate_gate": pass_rate >= gate.minimum_pass_rate,
        "run_errors": value.get("run_error_count") == 0,
        "control_count": isinstance(execution_counts, Mapping)
        and execution_counts.get("true") == K4_EXPECTED_CASES,
        "component_rates": isinstance(
            value.get("component_pass_rates"), Mapping
        ),
        "failure_counts": isinstance(
            value.get("failure_type_counts"), Mapping
        ),
    }
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise K5EvidenceImportError(
            "K4 aggregate gate failed: " + ", ".join(failures)
        )
    return dict(value)


def validate_k4_artifact_layout(
    stage: str | Path,
) -> dict[str, Path]:
    root = Path(stage).resolve(strict=True)
    if not root.is_dir():
        raise K5EvidenceImportError("K4 artifact root is not a directory")
    allowed = {"generated", "scenarios", "evidence"}
    observed = {path.name for path in root.iterdir()}
    if observed != allowed:
        raise K5EvidenceImportError(
            f"unexpected K4 artifact roots: {sorted(observed)}"
        )
    for path in root.rglob("*"):
        if path.is_symlink():
            raise K5EvidenceImportError(
                f"K4 artifact contains a symlink: {path}"
            )
    paths = {
        "generated": root / "generated" / "public-dev-slot-003",
        "scenario": root
        / "scenarios"
        / "public-dev-slot-003"
        / "scenario.json",
        "formal": root
        / "evidence"
        / "formal"
        / "aftermathbench-2026.08-r1"
        / "kubernetes"
        / "k8s-constraint-interaction-recovery"
        / "dev-006",
    }
    if not paths["generated"].is_dir():
        raise K5EvidenceImportError("K4 generated evidence is missing")
    if not paths["scenario"].is_file():
        raise K5EvidenceImportError("K4 scenario is missing")
    declarations = paths["formal"] / "completion" / "declarations.json"
    if not declarations.is_file():
        raise K5EvidenceImportError("K4 formal declarations are missing")
    paths["summary"] = paths["generated"] / "k4-public-summary.json"
    if not paths["summary"].is_file():
        raise K5EvidenceImportError("K4 public summary is missing")
    paths["declarations"] = declarations
    return paths


def build_k5_import_provenance(
    *,
    gate: K5EvidenceImportGate,
    artifact: Mapping[str, Any],
    import_gate_commit: str,
) -> dict[str, Any]:
    if _GIT_COMMIT.fullmatch(import_gate_commit) is None:
        raise K5EvidenceImportError("K5 import gate commit is invalid")
    selected = select_k4_artifact_metadata(
        {"artifacts": [dict(artifact)]},
        gate=gate,
    )
    return {
        "schema_version": "1.0",
        "stage": "K5-evidence-import",
        "import_gate_commit": import_gate_commit,
        "k4_run_id": gate.k4_run_id,
        "k4_commit": gate.k4_commit,
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
    "K4_EXPECTED_CASES",
    "K4_MODEL_ID",
    "K4_WORKFLOW_PATH",
    "K5EvidenceImportError",
    "K5EvidenceImportGate",
    "build_k5_import_provenance",
    "select_k4_artifact_metadata",
    "validate_k4_artifact_layout",
    "validate_k4_public_summary",
    "validate_k4_run_metadata",
]
