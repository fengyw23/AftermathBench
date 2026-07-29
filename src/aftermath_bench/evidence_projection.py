from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from typing import Any, Iterable, Mapping


@dataclass(frozen=True)
class ProjectionWitness:
    evidence_group: str
    left_variant: str
    right_variant: str
    left_scope: str
    right_scope: str
    removed_fact_keys: tuple[str, ...]
    retained_projection: tuple[tuple[str, Any], ...]


def _projection(
    facts: Mapping[str, Any],
    *,
    removed: frozenset[str],
) -> tuple[tuple[str, Any], ...]:
    return tuple(
        sorted(
            (str(key), value)
            for key, value in facts.items()
            if str(key) not in removed
        )
    )


def find_projection_witnesses(
    *,
    variant_facts: Mapping[str, Mapping[str, Any]],
    variant_scopes: Mapping[str, str],
    evidence_fact_groups: Mapping[str, Iterable[str]],
) -> dict[str, ProjectionWitness | None]:
    """Find matched pairs proving a fact group is decision-relevant.

    A witness pair has different required recovery scopes but becomes
    indistinguishable after every fact supplied by the selected evidence group
    is projected away. The function does not infer semantics from group names;
    builders must map each group to replay-derived fact keys.
    """

    variants = tuple(sorted(variant_facts))
    if set(variants) != set(variant_scopes):
        raise ValueError("variant facts and scopes must cover the same variants")
    results: dict[str, ProjectionWitness | None] = {}
    for group, raw_keys in evidence_fact_groups.items():
        removed = frozenset(map(str, raw_keys))
        if not removed:
            raise ValueError(f"evidence group has no fact keys: {group}")
        witness = None
        for left, right in combinations(variants, 2):
            left_scope = str(variant_scopes[left])
            right_scope = str(variant_scopes[right])
            if left_scope == right_scope:
                continue
            left_projection = _projection(variant_facts[left], removed=removed)
            right_projection = _projection(variant_facts[right], removed=removed)
            if left_projection != right_projection:
                continue
            if not any(
                variant_facts[left].get(key) != variant_facts[right].get(key)
                for key in removed
            ):
                continue
            witness = ProjectionWitness(
                evidence_group=str(group),
                left_variant=left,
                right_variant=right,
                left_scope=left_scope,
                right_scope=right_scope,
                removed_fact_keys=tuple(sorted(removed)),
                retained_projection=left_projection,
            )
            break
        results[str(group)] = witness
    return results


def projection_admission_report(
    *,
    variant_facts: Mapping[str, Mapping[str, Any]],
    variant_scopes: Mapping[str, str],
    evidence_fact_groups: Mapping[str, Iterable[str]],
) -> dict[str, Any]:
    witnesses = find_projection_witnesses(
        variant_facts=variant_facts,
        variant_scopes=variant_scopes,
        evidence_fact_groups=evidence_fact_groups,
    )
    serialised = {
        group: (
            {
                "left_variant": witness.left_variant,
                "right_variant": witness.right_variant,
                "left_scope": witness.left_scope,
                "right_scope": witness.right_scope,
                "removed_fact_keys": list(witness.removed_fact_keys),
                "retained_projection": [list(item) for item in witness.retained_projection],
            }
            if witness
            else None
        )
        for group, witness in witnesses.items()
    }
    witnessed = sum(witness is not None for witness in witnesses.values())
    return {
        "schema_version": "1.0",
        "evidence_group_count": len(witnesses),
        "projection_witness_count": witnessed,
        "all_declared_groups_have_witnesses": witnessed == len(witnesses),
        "witnesses": serialised,
    }
