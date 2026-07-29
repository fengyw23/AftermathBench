from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from .model_runner import ToolDefinition
from .native_scenario import NativeScenario


class NativeEnvironment(Protocol):
    def invoke(self, tool_name: str, **arguments: Any) -> dict[str, Any]: ...

    def snapshot(self) -> dict[str, Any]: ...

    def event_log(self) -> list[dict[str, Any]]: ...


@dataclass(frozen=True)
class NativeRuntimeContext:
    scenario: NativeScenario
    credentials: dict[str, Any]
    prefix: dict[str, Any]
    failure_report: dict[str, Any]
    repository_root: Path
    base_url: str
    container_cli: str


@dataclass(frozen=True)
class NativeFamilyDefinition:
    family_id: str
    domain: str
    system_prompt: str
    tool_definitions: tuple[ToolDefinition, ...]
    mutation_tools: frozenset[str]
    build_environment: Callable[[NativeRuntimeContext], NativeEnvironment]
    build_initial_message: Callable[..., str]
    evaluate: Callable[[dict[str, Any], dict[str, Any]], Any]
    diagnose: Callable[..., dict[str, Any]]


class NativeFamilyRegistry:
    def __init__(
        self,
        definitions: tuple[NativeFamilyDefinition, ...],
    ) -> None:
        self._definitions = {
            definition.family_id: definition for definition in definitions
        }
        if len(self._definitions) != len(definitions):
            raise ValueError("native family identifiers must be unique")

    @property
    def family_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._definitions))

    def get(self, family_id: str) -> NativeFamilyDefinition:
        try:
            return self._definitions[family_id]
        except KeyError as error:
            raise ValueError(
                f"unsupported native family {family_id!r}; available={self.family_ids}"
            ) from error
