from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Relation:
    source: str
    target: str
    type: str


@dataclass(frozen=True)
class TaskSpec:
    raw: dict[str, Any]

    @property
    def task_id(self) -> str:
        return str(self.raw["task_id"])

    @property
    def relations(self) -> tuple[Relation, ...]:
        return tuple(Relation(**item) for item in self.raw["relations"])


def repository_root() -> Path:
    return Path(__file__).resolve().parents[2]


def default_task_path() -> Path:
    return repository_root() / "data" / "tasks" / "enterprise-transfer-001" / "task.json"


def task_paths() -> tuple[Path, ...]:
    return tuple(sorted((repository_root() / "data" / "tasks").glob("*/task.json")))


def load_task(path: str | Path | None = None) -> TaskSpec:
    task_path = Path(path) if path is not None else default_task_path()
    with task_path.open("r", encoding="utf-8") as handle:
        return TaskSpec(json.load(handle))
