from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


_SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class ObligationInteractionAudit:
    variant_count: int
    obligation_count: int
    protected_obligation_count: int
    action_count: int
    gold_scope_count: int
    probe_count: int
    cross_obligation_witness_count: int
    repair_preservation_conflict_count: int
    variants_with_cross_obligation_witness: int
    variants_with_repair_preservation_conflict: int
    minimum_gold_action_count: int
    replay_bound: bool


def _identifiers(values: Any, *, label: str) -> tuple[str, ...]:
    if not isinstance(values, list):
        raise TypeError(f"{label} must be a list")
    result = tuple(str(value).strip() for value in values)
    if not result or any(not value for value in result):
        raise ValueError(f"{label} contains an empty identifier")
    if len(result) != len(set(result)):
        raise ValueError(f"{label} contains duplicate identifiers")
    return result


def analyze_obligation_interactions(
    payload: dict[str, Any],
) -> ObligationInteractionAudit:
    """Audit replayed evidence that recovery actions couple native obligations.

    This deliberately does not trust author-written ``repairs`` or ``breaks``
    labels.  A witness is derived from deterministic evaluator booleans before
    and after replaying a public-tool action.  Every probe is bound to its tool
    events and resulting native-state hash.
    """

    raw_obligations = payload.get("obligations")
    if not isinstance(raw_obligations, list) or not raw_obligations:
        raise ValueError("obligation interaction audit requires obligations")
    obligation_ids: list[str] = []
    protected: set[str] = set()
    for index, raw in enumerate(raw_obligations):
        if not isinstance(raw, dict):
            raise TypeError(f"obligation {index} is not an object")
        obligation_id = str(raw.get("id", "")).strip()
        if not obligation_id:
            raise ValueError(f"obligation {index} has no id")
        obligation_ids.append(obligation_id)
        if bool(raw.get("protected", False)):
            protected.add(obligation_id)
    if len(obligation_ids) != len(set(obligation_ids)):
        raise ValueError("obligation identifiers must be unique")
    obligation_set = set(obligation_ids)

    raw_actions = payload.get("actions")
    if not isinstance(raw_actions, list) or not raw_actions:
        raise ValueError("obligation interaction audit requires actions")
    action_ids = _identifiers(
        [raw.get("id", "") if isinstance(raw, dict) else "" for raw in raw_actions],
        label="actions",
    )
    action_set = set(action_ids)

    raw_rows = payload.get("rows")
    if not isinstance(raw_rows, list) or len(raw_rows) < 2:
        raise ValueError("obligation interaction audit requires at least two rows")

    variants: set[str] = set()
    gold_scopes: set[tuple[str, ...]] = set()
    probe_count = 0
    cross_count = 0
    conflict_count = 0
    variants_with_cross: set[str] = set()
    variants_with_conflict: set[str] = set()
    gold_action_counts: list[int] = []
    replay_bound = True

    for row_index, row in enumerate(raw_rows):
        if not isinstance(row, dict):
            raise TypeError(f"obligation row {row_index} is not an object")
        variant = str(row.get("variant", "")).strip()
        if not variant or variant in variants:
            raise ValueError(f"invalid or duplicate obligation variant: {variant}")
        variants.add(variant)
        boundary = row.get("boundary_evaluation")
        if not isinstance(boundary, dict) or set(boundary) != obligation_set:
            raise ValueError(
                f"variant {variant} must evaluate every declared obligation"
            )
        if any(not isinstance(value, bool) for value in boundary.values()):
            raise TypeError(f"variant {variant} boundary values must be booleans")

        gold_actions = _identifiers(
            row.get("gold_action_ids"), label=f"variant {variant} gold actions"
        )
        if not set(gold_actions) <= action_set:
            raise ValueError(f"variant {variant} references an unknown gold action")
        gold_scope = tuple(sorted(gold_actions))
        gold_scopes.add(gold_scope)
        gold_action_counts.append(len(gold_scope))

        probes = row.get("probes")
        if not isinstance(probes, list) or not probes:
            raise ValueError(f"variant {variant} has no replayed action probes")
        seen_actions: set[str] = set()
        for probe_index, probe in enumerate(probes):
            if not isinstance(probe, dict):
                raise TypeError(
                    f"variant {variant} probe {probe_index} is not an object"
                )
            action_id = str(probe.get("action_id", "")).strip()
            if action_id not in action_set or action_id in seen_actions:
                raise ValueError(
                    f"variant {variant} has an unknown or duplicate action probe"
                )
            seen_actions.add(action_id)
            events = probe.get("tool_events")
            result_hash = str(probe.get("result_state_sha256", ""))
            after = probe.get("result_evaluation")
            if (
                not isinstance(events, list)
                or not events
                or not all(
                    isinstance(event, dict)
                    and str(event.get("tool", "")).strip()
                    and isinstance(event.get("arguments"), dict)
                    for event in events
                )
                or not _SHA256.fullmatch(result_hash)
            ):
                replay_bound = False
            if not isinstance(after, dict) or set(after) != obligation_set:
                raise ValueError(
                    f"variant {variant} probe {action_id} must evaluate every obligation"
                )
            if any(not isinstance(value, bool) for value in after.values()):
                raise TypeError(
                    f"variant {variant} probe {action_id} values must be booleans"
                )

            repaired = {
                key for key in obligation_set if not boundary[key] and after[key]
            }
            broken = {
                key for key in obligation_set if boundary[key] and not after[key]
            }
            changed = repaired | broken
            probe_count += 1
            if len(changed) >= 2:
                cross_count += 1
                variants_with_cross.add(variant)
            if repaired and broken and bool(broken & protected):
                conflict_count += 1
                variants_with_conflict.add(variant)

    return ObligationInteractionAudit(
        variant_count=len(variants),
        obligation_count=len(obligation_set),
        protected_obligation_count=len(protected),
        action_count=len(action_set),
        gold_scope_count=len(gold_scopes),
        probe_count=probe_count,
        cross_obligation_witness_count=cross_count,
        repair_preservation_conflict_count=conflict_count,
        variants_with_cross_obligation_witness=len(variants_with_cross),
        variants_with_repair_preservation_conflict=len(variants_with_conflict),
        minimum_gold_action_count=min(gold_action_counts, default=0),
        replay_bound=replay_bound,
    )
