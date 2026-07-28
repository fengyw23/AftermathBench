from __future__ import annotations

import hashlib
import json
from abc import ABC, abstractmethod
from copy import deepcopy
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Callable


def canonical_fingerprint(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True)
class ToolEvent:
    sequence: int
    timestamp: str
    tool: str
    arguments: dict[str, Any]
    result: dict[str, Any]
    state_before: str
    state_after: str
    injected_fault: str | None = None


class ToolEnvironment(ABC):
    @abstractmethod
    def list_tools(self) -> tuple[str, ...]:
        raise NotImplementedError

    @abstractmethod
    def invoke(self, tool: str, **kwargs: Any) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def snapshot(self) -> dict[str, Any]:
        raise NotImplementedError


class RecordedEnvironment(ToolEnvironment):
    """Base class that records auditable tool/state transitions."""

    def __init__(self) -> None:
        self._events: list[ToolEvent] = []
        self._boundaries: dict[str, int] = {}

    @property
    def events(self) -> tuple[ToolEvent, ...]:
        return tuple(self._events)

    def event_log(self) -> list[dict[str, Any]]:
        return [asdict(event) for event in self._events]

    def mark_boundary(self, name: str) -> None:
        self._boundaries[name] = len(self._events)

    def events_after(self, name: str) -> tuple[ToolEvent, ...]:
        if name not in self._boundaries:
            raise KeyError(f"unknown event boundary: {name}")
        return tuple(self._events[self._boundaries[name]:])

    def _recorded_call(
        self,
        tool: str,
        arguments: dict[str, Any],
        operation: Callable[[], dict[str, Any]],
        injected_fault: str | None = None,
    ) -> dict[str, Any]:
        before = canonical_fingerprint(self.snapshot())
        result = operation()
        after = canonical_fingerprint(self.snapshot())
        self._events.append(
            ToolEvent(
                sequence=len(self._events) + 1,
                timestamp=datetime.now(UTC).isoformat(),
                tool=tool,
                arguments=deepcopy(arguments),
                result=deepcopy(result),
                state_before=before,
                state_after=after,
                injected_fault=injected_fault,
            )
        )
        return result


class CommitOutcome(StrEnum):
    NO_COMMIT = "no_commit"
    FULL_COMMIT_RESPONSE_LOST = "full_commit_response_lost"
    PARTIAL_COMMIT = "partial_commit"
    ASYNC_COMMIT_PENDING = "asynchronous_commit_pending"


@dataclass(frozen=True)
class FaultPlan:
    target_tool: str
    outcome: CommitOutcome
    occurrence: int = 1
    visible_error: str = "504 Gateway Timeout"


class TransitionFaultProxy(RecordedEnvironment):
    """Injects matched transition faults without exposing the hidden outcome.

    For full commits the wrapped tool executes normally and only its response is
    suppressed. Partial and asynchronous outcomes require explicit environment
    callbacks so the injected state remains a real, auditable state transition.
    """

    def __init__(
        self,
        wrapped: ToolEnvironment,
        plan: FaultPlan,
        partial_commit: Callable[[str, dict[str, Any]], None] | None = None,
        enqueue_async: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> None:
        super().__init__()
        self.wrapped = wrapped
        self.plan = plan
        self.partial_commit = partial_commit
        self.enqueue_async = enqueue_async
        self._target_calls = 0

    def list_tools(self) -> tuple[str, ...]:
        return self.wrapped.list_tools()

    def snapshot(self) -> dict[str, Any]:
        return self.wrapped.snapshot()

    def invoke(self, tool: str, **kwargs: Any) -> dict[str, Any]:
        if tool != self.plan.target_tool:
            return self._recorded_call(
                tool,
                kwargs,
                lambda: self.wrapped.invoke(tool, **kwargs),
            )

        self._target_calls += 1
        if self._target_calls != self.plan.occurrence:
            return self._recorded_call(
                tool,
                kwargs,
                lambda: self.wrapped.invoke(tool, **kwargs),
            )

        def inject() -> dict[str, Any]:
            match self.plan.outcome:
                case CommitOutcome.NO_COMMIT:
                    pass
                case CommitOutcome.FULL_COMMIT_RESPONSE_LOST:
                    self.wrapped.invoke(tool, **kwargs)
                case CommitOutcome.PARTIAL_COMMIT:
                    if self.partial_commit is None:
                        raise RuntimeError("partial_commit callback is required")
                    self.partial_commit(tool, kwargs)
                case CommitOutcome.ASYNC_COMMIT_PENDING:
                    if self.enqueue_async is None:
                        raise RuntimeError("enqueue_async callback is required")
                    self.enqueue_async(tool, kwargs)
            return {"ok": False, "error": self.plan.visible_error}

        return self._recorded_call(
            tool,
            kwargs,
            inject,
            injected_fault=self.plan.outcome.value,
        )
