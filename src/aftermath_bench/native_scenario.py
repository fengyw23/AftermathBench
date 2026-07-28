from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .schema import repository_root


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
    def variants(self) -> tuple[str, ...]:
        return tuple(
            str(item["id"]) for item in self.raw["matched_variants"]
        )

    def resolve_artifact(self, key: str) -> Path:
        relative = self.raw["admission_artifacts"][key]
        return (self.path.parent / relative).resolve()


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
    with scenario_path.open("r", encoding="utf-8") as handle:
        raw = json.load(handle)
    return NativeScenario(path=scenario_path, raw=raw)
