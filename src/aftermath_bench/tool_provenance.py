from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .model_runner import ToolDefinition


@dataclass(frozen=True)
class ToolProvenanceReport:
    passed: bool
    checks: dict[str, bool]
    declared_tools: tuple[str, ...]
    exposed_tools: tuple[str, ...]

    @property
    def failures(self) -> tuple[str, ...]:
        return tuple(name for name, value in self.checks.items() if not value)


def load_tool_provenance(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def validate_tool_provenance(
    raw: dict[str, Any],
    exposed: Iterable[ToolDefinition],
) -> ToolProvenanceReport:
    entries = tuple(raw.get("tools", ()))
    declared_names = tuple(str(entry.get("name", "")) for entry in entries)
    exposed_names = tuple(tool.name for tool in exposed)
    allowed_kinds = {"read", "write", "runtime_control"}
    checks = {
        "schema_version_present": bool(raw.get("schema_version")),
        "runtime_id_present": bool(raw.get("runtime_id")),
        "tool_names_unique": len(declared_names) == len(set(declared_names)),
        "coverage_exact": set(declared_names) == set(exposed_names),
        "every_tool_has_native_source": all(
            bool(entry.get("native_sources")) for entry in entries
        ),
        "every_tool_has_audit_boundary": all(
            bool(entry.get("audit_boundary")) for entry in entries
        ),
        "tool_kinds_valid": all(
            entry.get("kind") in allowed_kinds for entry in entries
        ),
        "no_decision_oracle": all(
            entry.get("returns_recommendation") is False for entry in entries
        ),
        "one_hop_reads_are_bounded": all(
            entry.get("maximum_relation_hops") in (None, 1)
            for entry in entries
        ),
    }
    return ToolProvenanceReport(
        passed=all(checks.values()),
        checks=checks,
        declared_tools=declared_names,
        exposed_tools=exposed_names,
    )
