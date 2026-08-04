from __future__ import annotations

from collections import deque
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class InterventionAction:
    """A design-time abstraction of one public mutation operator.

    Native replay must later verify these declared effects. ``unsafe_if_true``
    models duplicate or destructive application to an already-valid effect.
    """

    name: str
    sets_true: frozenset[str]
    requires_true: frozenset[str] = frozenset()
    invalidates: frozenset[str] = frozenset()
    unsafe_if_true: frozenset[str] = frozenset()


def _normalize_actions(
    obligations: frozenset[str], actions: Sequence[InterventionAction]
) -> tuple[InterventionAction, ...]:
    if not actions:
        raise ValueError("intervention audit requires at least one action")
    names: set[str] = set()
    normalized: list[InterventionAction] = []
    for action in actions:
        name = action.name.strip()
        if not name or name in names:
            raise ValueError("intervention action names must be unique and non-empty")
        names.add(name)
        mentioned = (
            action.sets_true
            | action.requires_true
            | action.invalidates
            | action.unsafe_if_true
        )
        if not action.sets_true or not mentioned <= obligations:
            raise ValueError(f"invalid intervention action {name!r}")
        normalized.append(
            InterventionAction(
                name=name,
                sets_true=frozenset(action.sets_true),
                requires_true=frozenset(action.requires_true),
                invalidates=frozenset(action.invalidates),
                unsafe_if_true=frozenset(action.unsafe_if_true),
            )
        )
    return tuple(normalized)


def _minimal_safe_plans(
    *,
    obligations: frozenset[str],
    initial: frozenset[str],
    actions: tuple[InterventionAction, ...],
) -> tuple[tuple[str, ...], ...]:
    if initial == obligations:
        return ((),)
    queue: deque[tuple[frozenset[str], tuple[str, ...]]] = deque([(initial, ())])
    best_depth: dict[frozenset[str], int] = {initial: 0}
    solutions: list[tuple[str, ...]] = []
    solution_depth: int | None = None
    while queue:
        state, plan = queue.popleft()
        if solution_depth is not None and len(plan) >= solution_depth:
            continue
        for action in actions:
            if not action.requires_true <= state:
                continue
            if action.unsafe_if_true & state:
                continue
            next_state = (state - action.invalidates) | action.sets_true
            if next_state == state:
                continue
            next_plan = (*plan, action.name)
            if next_state == obligations:
                solution_depth = len(next_plan)
                solutions.append(next_plan)
                continue
            previous = best_depth.get(next_state)
            if previous is None or len(next_plan) <= previous:
                best_depth[next_state] = len(next_plan)
                queue.append((next_state, next_plan))
    if solution_depth is None:
        return ()
    return tuple(sorted({plan for plan in solutions if len(plan) == solution_depth}))


def audit_intervention_design(
    *,
    obligations: Iterable[str],
    actions: Sequence[InterventionAction],
    variants: Mapping[str, Iterable[str]],
    minimum_multi_action_variants: int = 3,
    minimum_effect_overlap_pairs: int = 2,
    minimum_context_sensitive_actions: int = 3,
    minimum_tempting_unsafe_choices: int = 3,
) -> dict[str, Any]:
    """Audit mutation coupling independently of evidence-query complexity.

    ``variants`` maps a boundary name to obligations already valid there. The
    result is design evidence only: a native runtime must replay every action's
    effects before a family can use the measurements for hard admission.
    """

    obligation_set = frozenset(str(item).strip() for item in obligations)
    if len(obligation_set) < 3 or "" in obligation_set:
        raise ValueError("intervention audit requires at least three obligations")
    if len(variants) < 4:
        raise ValueError("intervention audit requires at least four variants")
    normalized_actions = _normalize_actions(obligation_set, actions)

    normalized_variants: dict[str, frozenset[str]] = {}
    for raw_name, raw_valid in variants.items():
        name = str(raw_name).strip()
        valid = frozenset(str(item).strip() for item in raw_valid)
        if not name or name in normalized_variants or not valid <= obligation_set:
            raise ValueError(f"invalid intervention variant {raw_name!r}")
        normalized_variants[name] = valid

    rows: dict[str, Any] = {}
    used_actions: set[str] = set()
    total_tempting_unsafe = 0
    for name, valid in normalized_variants.items():
        plans = _minimal_safe_plans(
            obligations=obligation_set,
            initial=valid,
            actions=normalized_actions,
        )
        missing = obligation_set - valid
        tempting_unsafe = sorted(
            action.name
            for action in normalized_actions
            if action.sets_true & missing and action.unsafe_if_true & valid
        )
        total_tempting_unsafe += len(tempting_unsafe)
        for plan in plans:
            used_actions.update(plan)
        rows[name] = {
            "valid_obligations": sorted(valid),
            "missing_obligations": sorted(missing),
            "minimal_safe_plan_length": len(plans[0]) if plans else None,
            "minimal_safe_plans": [list(plan) for plan in plans],
            "tempting_unsafe_actions": tempting_unsafe,
        }

    overlap_pairs = sorted(
        [left.name, right.name]
        for index, left in enumerate(normalized_actions)
        for right in normalized_actions[index + 1 :]
        if (
            left.sets_true & right.sets_true
            or left.invalidates & right.sets_true
            or right.invalidates & left.sets_true
        )
    )
    context_sensitive = sorted(
        action.name
        for action in normalized_actions
        if action.name in used_actions
        and any(
            action.unsafe_if_true & frozenset(row)
            for row in normalized_variants.values()
        )
    )
    lengths = [
        row["minimal_safe_plan_length"]
        for row in rows.values()
        if row["minimal_safe_plan_length"] is not None
    ]
    multi_action_count = sum(length >= 2 for length in lengths)
    distinct_plans = {
        tuple(plan)
        for row in rows.values()
        for plan in row["minimal_safe_plans"]
    }
    checks = {
        "all_variants_safely_solvable": len(lengths) == len(rows),
        "multiple_variants_require_composed_repairs": (
            multi_action_count >= minimum_multi_action_variants
        ),
        "mutation_effects_overlap": (
            len(overlap_pairs) >= minimum_effect_overlap_pairs
        ),
        "actions_are_context_sensitive": (
            len(context_sensitive) >= minimum_context_sensitive_actions
        ),
        "unsafe_shortcuts_are_present": (
            total_tempting_unsafe >= minimum_tempting_unsafe_choices
        ),
        "recovery_plans_are_not_one_template": len(distinct_plans) >= 4,
    }
    return {
        "schema_version": "1.0-design",
        "source": "declared intervention effects; native replay required",
        "obligations": sorted(obligation_set),
        "actions": [
            {
                "name": action.name,
                "sets_true": sorted(action.sets_true),
                "requires_true": sorted(action.requires_true),
                "invalidates": sorted(action.invalidates),
                "unsafe_if_true": sorted(action.unsafe_if_true),
            }
            for action in normalized_actions
        ],
        "variants": rows,
        "observed": {
            "multi_action_variant_count": multi_action_count,
            "maximum_minimal_plan_length": max(lengths, default=None),
            "effect_overlap_pairs": overlap_pairs,
            "context_sensitive_actions": context_sensitive,
            "tempting_unsafe_choice_count": total_tempting_unsafe,
            "distinct_minimal_plan_count": len(distinct_plans),
        },
        "checks": checks,
        "passed_design_gate": all(checks.values()),
    }


__all__ = ["InterventionAction", "audit_intervention_design"]
