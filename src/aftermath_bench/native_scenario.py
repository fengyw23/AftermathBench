from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .path_safety import safe_relative_path
from .schema import repository_root
from .strict_json import load_json_strict

ALLOWED_BENCHMARK_SPLITS = frozenset(
    {
        "pilot",
        "development",
        "development_regression",
        "public_dev",
        "hidden_test",
    }
)
ALLOWED_BENCHMARK_TIERS = frozenset({"easy", "candidate", "hard"})
REQUIRED_ADMISSION_ARTIFACTS = frozenset(
    {"prefix", "reference", "observed_graph", "baselines"}
)
DOMAIN_RUNTIME_IDS = {
    "erpnext": "erpnext-v15",
    "forgejo": "forgejo-main",
    "kubernetes": "kubernetes-v1.34",
}
_IDENTIFIER = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


@dataclass(frozen=True)
class NativeScenario:
    path: Path
    raw: dict[str, Any]

    @property
    def scenario_id(self) -> str:
        return str(self.raw["scenario_id"])

    @property
    def split(self) -> str:
        return str(self.raw.get("benchmark_split", "development"))

    @property
    def tier(self) -> str:
        return str(self.raw.get("benchmark_tier", "unclassified"))

    @property
    def domain_id(self) -> str:
        return str(self.raw.get("domain_id", ""))

    @property
    def family_id(self) -> str:
        return str(self.raw.get("family", ""))

    @property
    def instance_id(self) -> str:
        return str(self.raw.get("instance_id", ""))

    @property
    def variants(self) -> tuple[str, ...]:
        return tuple(
            str(item["id"]) for item in self.raw["matched_variants"]
        )

    def resolve_artifact(self, key: str) -> Path:
        relative = str(self.raw["admission_artifacts"][key])
        if relative.startswith("artifacts/"):
            return safe_relative_path(
                self.path.parent,
                relative,
                required_prefix="artifacts",
            )
        if str(self.raw.get("schema_version", "")).startswith("0."):
            scenario_data_root = repository_root() / "data"
            return safe_relative_path(
                scenario_data_root,
                (
                    self.path.parent.joinpath(relative)
                    .resolve()
                    .relative_to(scenario_data_root.resolve())
                    .as_posix()
                ),
            )
        raise ValueError(
            "native scenario admission artifacts must be under artifacts/"
        )


def native_scenario_paths() -> tuple[Path, ...]:
    return tuple(
        sorted(
            (repository_root() / "data" / "scenarios").glob(
                "*/scenario.json"
            )
        )
    )


def load_native_scenario(path: str | Path) -> NativeScenario:
    scenario_path = Path(path).resolve()
    raw = load_json_strict(scenario_path)
    return NativeScenario(path=scenario_path, raw=raw)


def validate_native_scenario_document(
    scenario: NativeScenario,
) -> tuple[str, ...]:
    raw = scenario.raw
    failures: list[str] = []
    required_strings = (
        "schema_version",
        "scenario_id",
        "domain_id",
        "instance_id",
        "family",
        "runtime_id",
        "benchmark_split",
        "benchmark_tier",
        "title",
        "user_instruction",
    )
    for field in required_strings:
        value = raw.get(field)
        if not isinstance(value, str) or not value.strip():
            failures.append(f"missing_or_invalid:{field}")
    for field in ("scenario_id", "domain_id", "instance_id", "family"):
        value = str(raw.get(field, ""))
        if value and _IDENTIFIER.fullmatch(value) is None:
            failures.append(f"invalid_identifier:{field}")
    if scenario.split not in ALLOWED_BENCHMARK_SPLITS:
        failures.append("invalid:benchmark_split")
    if scenario.tier not in ALLOWED_BENCHMARK_TIERS:
        failures.append("invalid:benchmark_tier")
    if DOMAIN_RUNTIME_IDS.get(scenario.domain_id) != str(
        raw.get("runtime_id", "")
    ):
        failures.append("domain_runtime_mismatch")
    ambiguous = raw.get("ambiguous_operation")
    if not isinstance(ambiguous, dict) or not all(
        isinstance(ambiguous.get(field), str) and ambiguous[field].strip()
        for field in ("operation", "surface_result")
    ):
        failures.append("invalid:ambiguous_operation")
    variants = raw.get("matched_variants")
    if not isinstance(variants, list) or not variants:
        failures.append("invalid:matched_variants")
    else:
        variant_ids = [
            str(item.get("id", ""))
            for item in variants
            if isinstance(item, dict)
        ]
        if (
            len(variant_ids) != len(variants)
            or not all(variant_ids)
            or len(variant_ids) != len(set(variant_ids))
        ):
            failures.append("matched_variant_ids_not_unique")
    artifacts = raw.get("admission_artifacts")
    if not isinstance(artifacts, dict):
        failures.append("invalid:admission_artifacts")
    else:
        if not REQUIRED_ADMISSION_ARTIFACTS <= set(artifacts):
            failures.append("missing_required_admission_artifact")
        for key in artifacts:
            try:
                scenario.resolve_artifact(str(key))
            except (KeyError, OSError, ValueError):
                failures.append(f"unsafe_admission_artifact:{key}")
    return tuple(failures)


__all__ = [
    "ALLOWED_BENCHMARK_SPLITS",
    "ALLOWED_BENCHMARK_TIERS",
    "DOMAIN_RUNTIME_IDS",
    "NativeScenario",
    "load_native_scenario",
    "native_scenario_paths",
    "validate_native_scenario_document",
]
