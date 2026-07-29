from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Iterable


@dataclass(frozen=True)
class RelationReplayResult:
    source: str
    target: str
    relation_type: str
    passed: bool
    checked_captures: int
    failures: tuple[str, ...]


def select_values(value: Any, selector: str) -> list[Any]:
    """Resolve a small, deterministic JSON selector with ``*`` list hops."""
    values = [value]
    for segment in selector.split("."):
        next_values: list[Any] = []
        if segment == "*":
            for current in values:
                if isinstance(current, list):
                    next_values.extend(current)
            values = next_values
            continue
        for current in values:
            if isinstance(current, dict) and segment in current:
                next_values.append(current[segment])
        values = next_values
    return values


def _expected(
    clause: dict[str, Any],
    entity_names: dict[str, str],
) -> Any:
    if "expected_entity" in clause:
        return entity_names[str(clause["expected_entity"])]
    return clause.get("expected")


def evaluate_clause(
    evidence: dict[str, Any],
    clause: dict[str, Any],
    entity_names: dict[str, str],
) -> bool:
    operator = str(clause["operator"])
    values = select_values(evidence, str(clause["selector"]))
    expected = _expected(clause, entity_names)
    if operator == "any_equals":
        return any(str(value) == str(expected) for value in values)
    if operator == "all_equal":
        return bool(values) and all(
            str(value) == str(expected) for value in values
        )
    if operator == "nonempty":
        return bool(values)
    if operator == "all_numeric_zero":
        return bool(values) and all(float(value) == 0 for value in values)
    if operator == "any_numeric_zero":
        return any(float(value) == 0 for value in values)
    if operator == "any_serialized_contains":
        return any(
            str(expected) in json.dumps(value, sort_keys=True, default=str)
            for value in values
        )
    if operator == "intersects":
        other = select_values(evidence, str(clause["other_selector"]))
        return bool({str(value) for value in values} & {str(v) for v in other})
    raise ValueError(f"unsupported replay operator: {operator}")


def replay_relation(
    relation: dict[str, Any],
    *,
    captures: Iterable[dict[str, Any]],
    entity_names: dict[str, str],
) -> RelationReplayResult:
    failures: list[str] = []
    checked = 0
    clauses = tuple(relation.get("replay", ()))
    if not clauses:
        failures.append("relation has no replay clauses")
    for capture in captures:
        checked += 1
        evidence = capture.get("evidence", {})
        for clause_index, clause in enumerate(clauses):
            try:
                passed = evaluate_clause(evidence, clause, entity_names)
            except (KeyError, TypeError, ValueError) as error:
                failures.append(
                    f"{capture.get('variant')} clause {clause_index}: {error}"
                )
                continue
            if not passed:
                failures.append(
                    f"{capture.get('variant')} clause {clause_index} failed"
                )
    return RelationReplayResult(
        source=str(relation["source"]),
        target=str(relation["target"]),
        relation_type=str(relation["type"]),
        passed=bool(clauses) and checked > 0 and not failures,
        checked_captures=checked,
        failures=tuple(failures),
    )


def replay_graph(
    graph: dict[str, Any],
    replay_evidence: dict[str, Any],
) -> tuple[RelationReplayResult, ...]:
    entity_names = {
        str(entity["id"]): str(entity["native_name"])
        for entity in graph.get("entities", ())
        if entity.get("native_name") is not None
    }
    captures = tuple(replay_evidence.get("captures", ()))
    return tuple(
        replay_relation(
            relation,
            captures=captures,
            entity_names=entity_names,
        )
        for relation in graph.get("relations", ())
    )
